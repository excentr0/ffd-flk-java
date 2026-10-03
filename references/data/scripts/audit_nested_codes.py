#!/usr/bin/env python3
"""Cross-check nested format-table tag/code cells with independent Poppler words.

Only source transcription is tested. Named hierarchy, logical-rule cell joins,
applicability and normative meaning are NOT verified by this script.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = {'1.05': (80, (80, 125)), '1.1': (105, (105, 145)),
           '1.2': (110, (110, 165))}


def ordinal(text):
    return re.sub(r'[^0-9.]', '', text or '').strip('.')


def pdf_words(pdf, page):
    output = subprocess.run(
        ['pdftotext', '-f', str(page), '-l', str(page), '-bbox-layout', str(pdf), '-'],
        capture_output=True, check=True).stdout
    root = ET.fromstring(output)
    return [(float(w.attrib['xMin']), float(w.attrib['yMin']), ''.join(w.itertext()))
            for w in root.iter() if w.tag.endswith('word')]


def audit(version):
    data = json.loads((ROOT / f'ffd-{version}.json').read_text(encoding='utf8'))
    pdf = ROOT / 'sources' / data['source']['file']
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != data['source']['sha256']:
        raise ValueError(f'PDF hash differs from dataset: {pdf}')
    fields = [(doc['id'], field) for doc in data['documents'] for field in doc['fields']
              if len(field.get('tag_path', [])) > 1]
    pages = {field['source_refs'][0]['page'] for _, field in fields}
    words = {page: pdf_words(pdf, page) for page in sorted(pages)}
    anchor_x, (tag_left, tag_right) = COLUMNS[version]
    results = []
    for doc, field in fields:
        page = field['source_refs'][0]['page']
        ws = words[page]
        source_ordinal = ordinal(field['source_ordinal'])
        anchors = [(x, y, word) for x, y, word in ws
                   if x < anchor_x and ordinal(word) == source_ordinal]
        record = {'id': field['id'], 'document': doc, 'page': page,
                  'ordinal': source_ordinal}
        if len(anchors) != 1:
            record.update(status='anchor_ambiguous', anchors=anchors)
            results.append(record)
            continue
        y = anchors[0][1]
        ordinal_y = sorted({v for x, v, word in ws if x < anchor_x
                            and re.fullmatch(r'\d+(?:\.\d+)*\.?', word)})
        next_y = next((v for v in ordinal_y if v > y + 1), y + 45)
        previous_y = next((v for v in reversed(ordinal_y) if v < y - 1), y - 45)
        lo, hi = (previous_y + y) / 2, (next_y + y) / 2
        tag = [word for x, v, word in ws if tag_left < x < tag_right
               and lo <= v < hi and re.fullmatch(r'\d{4}', word)]
        code = [word.rstrip(',') for x, v, word in ws if x > 520
                and lo <= v < hi and re.fullmatch(r'\d{3},?', word)]
        expected_tag = re.findall(r'(?<!\d)\d{4}(?!\d)',
                                  re.sub(r'\s+', '', field['raw']['tag_number']))
        expected_code = re.findall(r'(?<!\d)\d{3}(?!\d)', field['raw']['flk_codes'])
        record.update(status=('match' if tag == expected_tag
                              and sorted(code) == sorted(expected_code) else 'mismatch'),
                      tag_pdf=tag, tag_json=expected_tag, code_pdf=code,
                      code_json=expected_code, row_y=[round(lo, 1), round(hi, 1)])
        results.append(record)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, choices=COLUMNS)
    parser.add_argument('--output', type=Path, help='write per-row evidence to JSON')
    args = parser.parse_args()
    results = audit(args.version)
    counts = Counter(row['status'] for row in results)
    print(json.dumps({'version': args.version, 'records': len(results),
                      'statuses': dict(counts)}, ensure_ascii=False))
    for row in results:
        if row['status'] != 'match':
            print(json.dumps(row, ensure_ascii=False))
    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf8')
    return 1 if counts.get('mismatch') or counts.get('anchor_ambiguous') else 0


if __name__ == '__main__':
    raise SystemExit(main())
