#!/usr/bin/env python3
"""Independent Poppler-span / original raw-row ledger checks.

This proves source-row accounting, not full interpretation of formulas/merged cells.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

def key(ref):
    return ref['page'],ref['fragment_index'],ref['physical_row_index']

def audit(data, source_root):
    issues=[]
    pdf=source_root/data['source']['file']
    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=data['source']['sha256']:
        issues.append({'kind':'source_hash'})
    text=subprocess.run(['pdftotext','-layout',str(pdf),'-'],capture_output=True,text=True,check=True).stdout
    pages=text.split('\f')
    if not pages[-1].strip():pages.pop()
    if len(pages)!=len(data['pages']):issues.append({'kind':'page_count'})
    starts={}
    for number,page in enumerate(pages,1):
        if number<24:continue
        for match in re.finditer(r'(?m)^\s*Таблица\s+(\d+)\s*[–—-]',page):
            table=int(match[1])
            if 14<=table<=30:starts.setdefault(table,number)
    bbox_xml=subprocess.run(['pdftotext','-bbox-layout',str(pdf),'-'],capture_output=True,text=True,check=True).stdout
    tree=ET.fromstring(bbox_xml)
    bbox_pages=[node for node in tree.iter() if node.tag.endswith('}page') or node.tag=='page']
    source_ownership={};active=None
    for number,xml_page in enumerate(bbox_pages,1):
        if number<24:continue
        headings=[]
        for line in xml_page.iter():
            if not (line.tag.endswith('}line') or line.tag=='line'):continue
            line_text=' '.join(word.text or '' for word in line if word.tag.endswith('}word') or word.tag=='word')
            match=re.match(r'[ТT]аблица\s+(\d+)\s*[–—-]',line_text)
            if match:headings.append((float(line.attrib['yMin']),int(match[1])))
        headings.sort()
        for fragment in data['pages'][number-1]['tables']:
            for top,table_number in headings:
                if top<=fragment['bbox'][1]+3:active=table_number
            source_ownership[(number,fragment['table_index'])]=active
        if headings:active=headings[-1][1]
        if active is not None and active>=30:break
    source_field_keys=set();observed_field_keys=set();table_counts={}
    records={field['id']:field for document in data['documents'] for field in document['fields']}
    for document in data['documents']:
        table=document['format_table'];begin=starts.get(table);end=starts.get(table+1)
        if begin is None or end is None:
            issues.append({'kind':'missing_caption','table':table});continue
        expected=[]
        for number in range(begin,end+1):
            for fragment in data['pages'][number-1]['tables']:
                if fragment['bbox'][2]-fragment['bbox'][0]<400:continue
                if source_ownership.get((number,fragment['table_index']))!=table:continue
                for index,row in enumerate(fragment['raw_cells'],1):
                    if len(row) not in (8,9):continue
                    ordinal=re.sub(r'\s+','',row[0] or '').rstrip('.')
                    if not re.fullmatch(r'\d+(?:\.\d+)*',ordinal):continue
                    ref=(number,fragment['table_index'],index)
                    expected.append((ref,ordinal))
                    source_field_keys.add(ref)
        actual=[]
        for row in data['row_ledger']:
            if row['table_number']==table and row['classification'] in ('field','field_continuation'):
                ref=key(row['source_ref']);cells=row['raw_cells']
                ordinal=re.sub(r'\s+','',cells[0] or '').rstrip('.')
                if re.fullmatch(r'\d+(?:\.\d+)*',ordinal):actual.append((ref,ordinal));observed_field_keys.add(ref)
        if expected!=actual:
            issues.append({'kind':'source_field_sequence','table':table,
                           'missing':sorted(set(expected)-set(actual)),
                           'unexpected':sorted(set(actual)-set(expected))})
        table_counts[str(table)]={'source_numbered_row_fragments':len(expected),
                                 'dataset_field_records':len(document['fields']),
                                 'first_page':begin,'last_page_including_continuation':end,
                                 'last_ordinal':expected[-1][1] if expected else None}
        ids=[field['id'] for field in document['fields']]
        if len(ids)!=len(set(ids)):issues.append({'kind':'duplicate_field_id','document':document['id']})
        names={field['source_name']:field for field in document['fields']}
        for field in document['fields']:
            reference=field['source_refs'][0]
            fragment=next(t for t in data['pages'][reference['page']-1]['tables'] if t['table_index']==reference['fragment_index'])
            source_row=fragment['raw_cells'][reference['physical_row_index']-1]
            value=source_row[1] or ''
            if field['field_kind']=='tlv':
                candidates=re.findall(r'(?<!\d)\d{4}(?!\d)',value)
                if len(candidates)==1:expected_tag=int(candidates[0])
                else:
                    joined=re.sub(r'\s+','',value)
                    expected_tag=int(joined) if joined.isdigit() and len(joined)==4 else None
                if field['tag_numbers']!=[expected_tag]:
                    issues.append({'kind':'tag_transcription','field':field['id'],'source':value,'actual':field['tag_numbers']})
                if not field['tag_path'] or field['tag_path'][-1]!=expected_tag:
                    issues.append({'kind':'path_leaf','field':field['id']})
                if '.' in field['source_name']:
                    parent=names.get(field['source_name'].rsplit('.',1)[0])
                    if parent is not None and parent['type']=='STLV' and field['parent_field_id']!=parent['id']:
                        issues.append({'kind':'named_parent','field':field['id']})
                if field['parent_field_id'] is not None and field['parent_field_id'] not in records:
                    issues.append({'kind':'dangling_parent','field':field['id']})
            if field['field_kind']=='document_discriminator' and (field['tag_path'] or field['tag_numbers']):
                issues.append({'kind':'document_code_mistaken_for_tag','field':field['id']})
        if document['incoming_flk_exempt']:
            if any(r['document']==document['id'] and r['kind']=='field_format' for r in data['rules']):
                issues.append({'kind':'exemption_violation','document':document['id']})
    for row in data['row_ledger']:
        if row['classification'] in ('field','field_continuation') and row.get('record_id') not in records:
            issues.append({'kind':'ledger_field_missing','record_id':row.get('record_id')})
    classified=Counter(row['classification'] for row in data['row_ledger'])
    if set(row['table_number'] for row in data['row_ledger'])!=set(range(14,30)):
        issues.append({'kind':'missing_table_ledger'})
    if classified.get('unclassified',0):issues.append({'kind':'unclassified_rows','count':classified['unclassified']})
    # Each original physical fragment must occur once in the row ledger, even when
    # logical associations remain pending. Raw cells must not be rewritten.
    ledger_keys=[key(row['source_ref']) for row in data['row_ledger']]
    if len(ledger_keys)!=len(set(ledger_keys)):issues.append({'kind':'duplicate_source_row'})
    for row in data['row_ledger']:
        ref=row['source_ref'];page=data['pages'][ref['page']-1]
        if source_ownership.get((ref['page'],ref['fragment_index']))!=row['table_number']:
            issues.append({'kind':'source_table_ownership','source_ref':ref})
        table=next(t for t in page['tables'] if t['table_index']==ref['fragment_index'])
        if row['raw_cells']!=table['raw_cells'][ref['physical_row_index']-1]:
            issues.append({'kind':'raw_row_rewrite','source_ref':ref})
    # All normative-interpretation gaps remain blockers, independently of source
    # preservation. This is deliberately not hidden by an extraction pass.
    logical=[r for r in data['rules'] if r['kind']=='logical_source_rule']
    return {'ffd_version':data['ffd_version'],'pages':len(pages),
            'unique_defined_tags':sum(bool(t['occurrences']) for t in data['tags']),
            'reference_only_tags':sum(not t['occurrences'] for t in data['tags']),
            'field_records':len(records),'source_numbered_row_fragments':len(source_field_keys),
            'numbered_row_sequence_missing':len(source_field_keys-observed_field_keys),
            'nested_field_records':sum(f['parent_field_id'] is not None for f in records.values()),
            'printed_ordinal_name_conflicts':sum(f['printed_hierarchy_conflict'] for f in records.values()),
            'logical_source_row_records':len(logical),'physical_row_classifications':dict(classified),
            'document_tables':table_counts,'structural_issues':issues,
            'source_row_accounting_pass':not issues,
            'formalization':data.get('formalization_summary'),
            'unresolved_count':len(data['unresolved']),
            'semantic_readiness':'BLOCKED_REQUIRES_REVIEW',
            'limitations':['Rule-row continuation and merged-message/condition association require independent visual review.',
                           'Syntax ASTs and source-row accounting do not establish correct normative interpretation.']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset-dir',type=Path,default=ROOT)
    parser.add_argument('--source-root',type=Path,default=ROOT/'sources' if (ROOT/'sources').is_dir() else ROOT.parent)
    parser.add_argument('--require-ready',action='store_true')
    args=parser.parse_args();results=[]
    for version in ['1.05','1.1','1.2']:
        results.append(audit(json.loads((args.dataset_dir/f'ffd-{version}.json').read_text()),args.source_root))
    output={'status':'structured_source_accounting_checked_not_semantic_certification',
            'versions':results,'production_ready':False}
    (args.dataset_dir/'coverage.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output,ensure_ascii=False,indent=2))
    return int(any(r['structural_issues'] for r in results) or args.require_ready)
if __name__=='__main__':sys.exit(main())
