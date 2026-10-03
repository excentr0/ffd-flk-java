#!/usr/bin/env python3
"""Transcribe FLK-related OFD return codes without approving incoming checks."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
NON_FLK_RETURN_CODES = {400, 405, 409, 417, 419}  # Request/transport/quarantine, not FLK.
DOCUMENTS = ('registration', 'registration_change', 'shift_open', 'current_state',
             'receipt', 'correction_receipt', 'shift_close', 'fn_close')
COLUMNS = ('stage', 'processing_type', 'http_response', 'error_code', 'tag',
           'message', 'description')
# Point offsets from the left edge of the seven-column return tables (32–39).
CENTERS = (28, 85, 138, 189, 250, 324, 425)


def cells_by_column(table, row, values):
    columns = {name: '' for name in COLUMNS}
    boxes = {}
    for value, box in zip(values, row.cells):
        if not value or box is None:
            continue
        x = (box[0] + box[2]) / 2 - table.bbox[0]
        column = COLUMNS[min(range(len(CENTERS)), key=lambda i: abs(CENTERS[i] - x))]
        columns[column] += ('\n' if columns[column] else '') + value
        boxes[column] = list(box)
    return columns, boxes


def generate(version, dataset_dir):
    dataset = json.loads((dataset_dir / f'ffd-{version}.json').read_text(encoding='utf8'))
    pdf_path = ROOT / 'sources' / dataset['source']['file']
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != dataset['source']['sha256']:
        raise ValueError(f'{version}: source PDF hash differs from dataset')
    known = {rule['code'] for rule in dataset['rules'] if rule['kind'] == 'logical_source_rule'}
    known.update(code for rule in dataset['rules'] if rule['kind'] == 'field_format'
                 for code in rule['codes'].values() if isinstance(code, int))
    active_table = None
    entries = []
    status = None
    seen_codes = Counter()
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            # Captions can occur after the last grid on a page. Compare vertical positions.
            captions = sorted((match['top'], int(re.search(r'\d+', match['text']).group()))
                              for match in page.search(r'Таблица\s+\d+\s*[–—-]'))
            for fragment_index, table in enumerate(page.find_tables(), 1):
                for top, number in captions:
                    if top <= table.bbox[1] + 3:
                        active_table = number
                if 32 <= (active_table or 0) <= 39:
                    for row_index, (values, row) in enumerate(zip(table.extract(), table.rows), 1):
                        columns, boxes = cells_by_column(table, row, values)
                        raw_code = re.sub(r'\s+', '', columns['error_code'])
                        if not re.fullmatch(r'\d{3}', raw_code):
                            continue  # Header, deduplication, or continuation; not an error code.
                        code = int(raw_code)
                        seen_codes[code] += 1
                        if code in NON_FLK_RETURN_CODES:
                            continue
                        if code not in known:
                            raise ValueError(f'{version}: unclassified return code {code}, '
                                             f'PDF p.{page_number} table {active_table}; review source')
                        entries.append({
                            'document': DOCUMENTS[active_table - 32],
                            'table': active_table, 'pdf_page': page_number,
                            'fragment_index': fragment_index, 'physical_row_index': row_index,
                            'row_bbox': list(row.bbox), 'code_cell_bbox': boxes['error_code'],
                            'code': code, 'columns': columns,
                            # A blank column may be visually merged with another row; do not
                            # invent its value or silently carry it across a page/table boundary.
                            'raw_cells': values,
                        })
                elif active_table == 41:
                    for row_index, values in enumerate(table.extract(), 1):
                        parts = [v for v in values if v]
                        if parts and parts[0].strip() == '2' and 'Ошибки ФЛК' in (parts[1] if len(parts) > 1 else ''):
                            if status is not None:
                                raise ValueError(f'{version}: duplicate FLK errorStatus=2')
                            codes = [int(v) for v in re.findall(r'\d{3}', parts[1])]
                            if not codes or any(code not in known for code in codes):
                                raise ValueError(f'{version}: unexpected FLK errorStatus=2 code list')
                            status = {'field': 'errorStatus', 'value': 2, 'codes': codes,
                                      'description': parts[1], 'actions': parts[2] if len(parts) > 2 else '',
                                      'table': 41, 'pdf_page': page_number,
                                      'fragment_index': fragment_index, 'physical_row_index': row_index}
            if captions:
                active_table = captions[-1][1]
    if status is None or set(range(32, 40)) != {entry['table'] for entry in entries}:
        raise ValueError(f'{version}: missing FLK return table or errorStatus=2')
    if set(seen_codes) - known != NON_FLK_RETURN_CODES:
        raise ValueError(f'{version}: non-FLK source code inventory changed: '
                         f'{set(seen_codes) - known}')
    return {'ffd_version': version, 'source': dataset['source'],
            'scope': 'PPFD_RETURN_CODE_TRANSCRIPTION_NOT_INCOMING_FLK_APPROVAL',
            'selection': 'Error-code column in tables 32–39; exclude source-verified '
                         'non-FLK return codes 400, 405, 409, 417, 419; preserve every '
                         'FLK-code cell occurrence and its raw row without deduplication.',
            'excluded_non_flk_codes': sorted(NON_FLK_RETURN_CODES),
            'returns': entries, 'flk_error_status': status}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-dir', type=Path, default=ROOT)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for version in ('1.05', '1.1', '1.2'):
        result = generate(version, args.dataset_dir)
        output = args.output_dir / f'flk-returns-{version}.json'
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.check:
            if not output.is_file() or output.read_text(encoding='utf8') != text:
                raise ValueError(f'{output}: generated FLK return codes differ from source')
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding='utf8')
        print(f'{version}: {len(result["returns"])} FLK return-code cells; '
              f'errorStatus=2 lists {len(result["flk_error_status"]["codes"])} codes')


if __name__ == '__main__':
    main()
