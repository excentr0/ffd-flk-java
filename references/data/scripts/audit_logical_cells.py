#!/usr/bin/env python3
"""Compare detected logical-table physical cell text to independent Poppler words.

Uses pdfplumber ONLY for cell boundaries; this does not independently discover
all tables or prove correct cross-row cell inheritance / normative semantics.
Report all mismatches for visual adjudication; never silently mark them correct.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]


def compact(value):
    return re.sub(r'\s+', '', value or '')


def words(pdf, page):
    output = subprocess.run(
        ['pdftotext', '-f', str(page), '-l', str(page), '-bbox-layout', str(pdf), '-'],
        capture_output=True, check=True).stdout
    return [(float(w.attrib['xMin']), float(w.attrib['xMax']),
             float(w.attrib['yMin']), float(w.attrib['yMax']), ''.join(w.itertext()))
            for w in ET.fromstring(output).iter() if w.tag.endswith('word')]


def audit(version):
    data = json.loads((ROOT / f'ffd-{version}.json').read_text(encoding='utf8'))
    pdf = ROOT / 'sources' / data['source']['file']
    rows = defaultdict(list)
    for item in data['row_ledger']:
        if (item['table_number'] % 2
                and item['classification'] in ('logical_rule', 'rule_continuation')):
            rows[item['source_ref']['page']].append(item)
    results = []
    with pdfplumber.open(pdf) as document:
        for page_number, items in sorted(rows.items()):
            page_words = words(pdf, page_number)
            tables = document.pages[page_number - 1].find_tables()
            for item in items:
                ref = item['source_ref']
                table = [t for t in tables if all(abs(t.bbox[i] - ref['bbox'][i]) < .1
                                                   for i in range(4))]
                index = ref['physical_row_index'] - 1
                record = {'page': page_number, 'record_id': item.get('record_id'),
                          'physical_row_index': index + 1}
                if len(table) != 1 or index >= len(table[0].rows):
                    results.append(dict(record, status='table_or_row_ambiguous'))
                    continue
                cells = table[0].rows[index].cells
                if len(cells) != len(item['raw_cells']):
                    results.append(dict(record, status='cell_count_mismatch'))
                    continue
                for column, (bbox, expected) in enumerate(zip(cells, item['raw_cells'])):
                    if not expected or bbox is None:
                        continue
                    x1, y1, x2, y2 = bbox
                    observed = ' '.join(word for x, xx, y, yy, word in page_words
                                        if x1 - .5 <= x and xx <= x2 + .5
                                        and y1 - .5 <= y and yy <= y2 + .5)
                    results.append(dict(record, column=column,
                                        status='match' if compact(observed) == compact(expected)
                                        else 'mismatch', pdf=observed, dataset=expected,
                                        cell_bbox=bbox))
    return results, len(rows), sum(map(len, rows.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, choices=['1.05', '1.1', '1.2'])
    parser.add_argument('--output', type=Path, help='write per-cell evidence to JSON')
    args = parser.parse_args()
    results, pages, physical_rows = audit(args.version)
    counts = Counter(item['status'] for item in results)
    print(json.dumps({'version': args.version, 'pages': pages,
                      'physical_rows': physical_rows, 'cells': len(results),
                      'statuses': dict(counts)}, ensure_ascii=False))
    for item in results:
        if item['status'] != 'match':
            print(json.dumps(item, ensure_ascii=False))
    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf8')
    return 1 if any(key != 'match' for key in counts) else 0


if __name__ == '__main__':
    raise SystemExit(main())
