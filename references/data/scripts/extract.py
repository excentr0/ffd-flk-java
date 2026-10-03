#!/usr/bin/env python3
"""Loss-preserving PDF page/table extraction for FFD protocol sources."""
import argparse, hashlib, json
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT/'sources' if (ROOT/'sources').is_dir() else ROOT.parent
SPECS = [
 ('1.05','FFD_1.05_OFD-FNS_v9.8.pdf','9.8'),
 ('1.1','FFD_1.1_OFD-FNS_v3.8.pdf','3.8'),
 ('1.2','FFD_1.2_OFD-FNS_v2.15.pdf','2.15')]

def extract(version, filename, protocol):
 p = SOURCES / filename
 pages=[]
 with pdfplumber.open(p) as pdf:
  for n,page in enumerate(pdf.pages,1):
   tabs=[]
   for i,table in enumerate(page.find_tables() or [],1):
    tabs.append({'table_index':i,'bbox':list(table.bbox),'raw_cells':table.extract()})
   pages.append({'page_number':n,'text':page.extract_text(layout=True) or '', 'tables':tabs})
 data={'ffd_version':version,'protocol_document_version':protocol,
       'source':{'file':filename,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()},
       'target':'KKT_TO_OFD','extraction_status':'raw_source_preservation_only',
       'pages':pages,'tags':[],'documents':[],'rules':[],'unresolved':[
        {'reason':'Semantic tag, document, and FLK row classification has not been reviewed; raw extraction is not formalization.'}],
       'source_refs':[]}
 return data

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output-dir',type=Path,default=ROOT)
 args=parser.parse_args()
 args.output_dir.mkdir(parents=True,exist_ok=True)
 for v,f,p in SPECS:
  dest=args.output_dir/f'ffd-{v}.json'; dest.write_text(json.dumps(extract(v,f,p),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  print(dest)
if __name__=='__main__': main()
