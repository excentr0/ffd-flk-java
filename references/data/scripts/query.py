#!/usr/bin/env python3
"""Bounded contextual data query. Output is source evidence, not approved rules."""
import argparse
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--version',required=True,choices=['1.05','1.1','1.2'])
    p.add_argument('--document',required=True);p.add_argument('--tag',required=True,type=int)
    p.add_argument('--path',help='Exact comma-separated numeric tag_path')
    p.add_argument('--rules-limit',type=int,default=5)
    a=p.parse_args();data=json.loads((ROOT/f'ffd-{a.version}.json').read_text())
    doc=next((d for d in data['documents'] if d['id']==a.document),None)
    if doc is None:p.error('unknown document; see documents[].id')
    path=[int(x) for x in a.path.split(',')] if a.path else None
    fields=[f for f in doc['fields'] if a.tag in f['tag_numbers'] and (path is None or f['tag_path']==path)]
    mention=re.compile(r'(?<!\d)'+str(a.tag)+r'(?!\d)')
    candidates=[r for r in data['rules'] if r['document']==doc['id'] and r['kind']=='logical_source_rule'
                and mention.search(' '.join(r['raw'].values()))]
    print(json.dumps({'version':a.version,'source':data['source'],'document':doc['id'],
                     'incoming_flk_exempt':doc['incoming_flk_exempt'],'fields':fields,
                     'candidate_source_rule_mentions':candidates[:max(a.rules_limit,0)],
                     'candidate_mentions_total':len(candidates),'production_ready':False},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
