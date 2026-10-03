#!/usr/bin/env python3
"""Check FLK return-code cells against independent Poppler word positions."""
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
NS = '{http://www.w3.org/1999/xhtml}'
FIRST_RETURN_PAGE = {'1.05': 81, '1.1': 127, '1.2': 149}


def audit(version):
    data = json.loads((ROOT / f'flk-returns-{version}.json').read_text(encoding='utf8'))
    pdf = ROOT / 'sources' / data['source']['file']
    first = FIRST_RETURN_PAGE[version]
    last = max(entry['pdf_page'] for entry in data['returns'])
    xml = subprocess.check_output(['pdftotext', '-f', str(first), '-l', str(last),
                                   '-bbox-layout', str(pdf), '-'])
    pages = list(ET.fromstring(xml).iter(NS + 'page'))
    if len(pages) != last - first + 1:
        raise ValueError(f'{version}: Poppler page count mismatch')
    words = [[(word.text, *(float(word.attrib[k]) for k in
                ('xMin', 'yMin', 'xMax', 'yMax')))
              for word in page.iter(NS + 'word')] for page in pages]
    for entry in data['returns']:
        left, top, right, bottom = entry['code_cell_bbox']
        if not any(text == str(entry['code']) and x0 >= left - 1 and x1 <= right + 1
                   and y0 >= top - 1 and y1 <= bottom + 1
                   for text, x0, y0, x1, y1 in words[entry['pdf_page'] - first]):
            raise ValueError(f'{version}: code {entry["code"]} not printed at '
                             f'p.{entry["pdf_page"]} table {entry["table"]} '
                             f'row {entry["physical_row_index"]}')

    # Inventory every printed three-digit value in the ERROR-code column,
    # including excluded request/transport rows. Poppler provides the words;
    # pdfplumber only locates the table grid/caption (and is not a text oracle).
    printed = Counter()
    active_table = None
    with pdfplumber.open(pdf) as source:
        for page_number in range(first, last + 1):
            page = source.pages[page_number - 1]
            captions = sorted((match['top'], int(re.search(r'\d+', match['text']).group()))
                              for match in page.search(r'Таблица\s+\d+\s*[–—-]'))
            for table in page.find_tables():
                for top, number in captions:
                    if top <= table.bbox[1] + 3:
                        active_table = number
                if active_table not in range(32, 40):
                    continue
                for text, x0, y0, x1, y1 in words[page_number - first]:
                    x = (x0 + x1) / 2 - table.bbox[0]
                    y = (y0 + y1) / 2
                    if re.fullmatch(r'\d{3}', text or '') and 164 < x < 219 \
                            and table.bbox[1] <= y <= table.bbox[3]:
                        printed[(active_table, int(text))] += 1
            if captions:
                active_table = captions[-1][1]
    expected = Counter((entry['table'], entry['code']) for entry in data['returns'])
    for table in range(32, 40):
        expected.update({(table, 400): 1, (table, 405): 3, (table, 409): 1,
                         (table, 417): 1, (table, 419): 1})
    if printed != expected:
        raise ValueError(f'{version}: Poppler/source code-column inventory differs: '
                         f'extra={printed - expected}, missing={expected - printed}')
    return len(data['returns'])


if __name__ == '__main__':
    for version in ('1.05', '1.1', '1.2'):
        print(f'{version}: {audit(version)} FLK return-code cells confirmed by Poppler')
