#!/usr/bin/env python3
"""Independent Poppler caption inventory for the 8 format/paired FLK tables per FFD."""
import json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES=(ROOT/'sources' if (ROOT/'sources').is_dir() else ROOT.parent)/'extracted-sources'
TEXTS={
 '1.05':'FFD_1.05_OFD-FNS_v9.8.txt',
 '1.1':'FFD_1.1_OFD-FNS_v3.8.txt',
 '1.2':'FFD_1.2_OFD-FNS_v2.15.txt'}
EXPECTED={'format':[14,16,18,20,22,24,26,28], 'flk':[15,17,19,21,23,25,27,29]}
def main():
 missing=[]; out={}
 for version,name in TEXTS.items():
  pages=(SOURCES/name).read_text(encoding='utf8').split('\f')
  inv={}
  for kind,numbers in EXPECTED.items():
   inv[kind]={}
   for number in numbers:
    rx=re.compile(rf'(?im)^\s*Таблица\s+{number}\s*[–-]')
    locations=[i for i,page in enumerate(pages,1) if rx.search(page)]
    inv[kind][str(number)]=locations
    # Revision-history pages may repeat references to a table number. The earliest
    # caption occurrence is the source table candidate; later occurrences are retained
    # as candidates, not silently counted as additional tables.
    if not locations: missing.append({'version':version,'kind':kind,'table':number,'pages':locations})
  out[version]=inv
 result={'source':'Poppler pdftotext -layout text','tablesExpectedPerVersion':{'format':8,'flk':8},'inventory':out,'missing_captions':missing,'caption_candidates_include_revision_history_references':True,'row_coverage':'not audited; caption inventory only'}
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 1 if missing else 0
if __name__=='__main__':
 raise SystemExit(main())
