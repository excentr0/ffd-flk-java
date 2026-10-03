#!/usr/bin/env python3
"""Independent basic PDF/page extraction integrity check; not semantic audit."""
import argparse, hashlib, json, sys
from pathlib import Path
import pdfplumber
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'sources' if (ROOT/'sources').is_dir() else ROOT.parent

def verify(file):
 d=json.loads(file.read_text(encoding='utf8')); src=SOURCE/d['source']['file']; issues=[]
 if hashlib.sha256(src.read_bytes()).hexdigest()!=d['source']['sha256']: issues.append('source hash mismatch')
 with pdfplumber.open(src) as pdf:
  if len(pdf.pages)!=len(d['pages']): issues.append(f'page count {len(d["pages"])} != PDF {len(pdf.pages)}')
  for i,(pdfpage,record) in enumerate(zip(pdf.pages,d['pages']),1):
   if record['page_number']!=i: issues.append(f'page index mismatch at {i}')
   # Every non-empty extracted source page must have been represented; extraction is
   # compared by re-running the same independent library against the original PDF.
   if record['text']!=(pdfpage.extract_text(layout=True) or ''): issues.append(f'page text mismatch {i}')
   actual=pdfpage.find_tables() or []
   expected=[t['raw_cells'] for t in record['tables']]
   actual_cells=[table.extract() for table in actual]
   if expected!=actual_cells: issues.append(f'table cells mismatch {i}')
   if [t['bbox'] for t in record['tables']] != [list(table.bbox) for table in actual]:
    issues.append(f'table bbox mismatch {i}')
 result={'dataset':file.name,'pages':len(d['pages']),'tables':sum(len(p['tables']) for p in d['pages']),
         'source_sha256':d['source']['sha256'],'semantic_coverage':'NOT_AUDITED','issues':issues}
 print(json.dumps(result,ensure_ascii=False))
 return not issues
if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--dataset-dir',type=Path,default=ROOT)
 args=parser.parse_args()
 files=[args.dataset_dir/f'ffd-{v}.json' for v in ['1.05','1.1','1.2']]
 sys.exit(0 if all(verify(f) for f in files) else 1)
