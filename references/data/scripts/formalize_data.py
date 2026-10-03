#!/usr/bin/env python3
"""Attach conservative syntax ASTs; never imply semantic approval or executability."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from expressions import parse_expression
ROOT=Path(__file__).resolve().parents[1]

def join_source_lines(source):
    """Keep reserved words, quoted literals and horizontal token boundaries.
    Join only line-wrapped identifier/digit fragments; syntax remains a candidate.
    """
    splitter=re.compile(r"('[^']*'|\"[^\"]*\"|\b(?:EXIST|NOT|AND|OR|IN)\b)")
    pieces=splitter.split(source)
    output=[]
    for index,piece in enumerate(pieces):
        if index%2:
            output.append(' '+piece+' ')
        else:
            output.append(re.sub(r'(?<=[\w])[^\S\n]*\n[^\S\n]*(?=[\w])','',piece))
    return ''.join(output).strip()

def parse_source(source):
    direct=parse_expression(source)
    if direct['status']=='parsed':
        return dict(direct,normalized_source=source,transformation='none',semantic_status='pending')
    normalized=join_source_lines(source)
    candidate=parse_expression(normalized)
    return dict(candidate,normalized_source=normalized,
                transformation='join_PDF_line_wraps_preserving_keywords_and_literals',semantic_status='pending')

def formalize(data):
    unresolved=[u for u in data['unresolved'] if u.get('kind') not in
                ('logical_formalization','field_constraint_formalization','reference_only_tag','hierarchy_conflict','cardinality_policy_review')]
    for document in data['documents']:
        for field in document['fields']:
            if field.get('printed_hierarchy_conflict'):
                unresolved.append({'kind':'hierarchy_conflict','field_id':field['id'],
                                   'source_ref':field['source_refs'][0],
                                   'reason':field['hierarchy_note']})
            if field['field_kind']=='tlv' and field['cardinality']['status']=='minimum_source_literal_maximum_requires_policy_review':
                unresolved.append({'kind':'cardinality_policy_review','field_id':field['id'],
                                   'source_ref':field['source_refs'][0],
                                   'reason':'Minimum is source literal; singleton maximum is an unapproved candidate'})
            for key in ('allowed_values','byte_length','obligation'):
                raw=field['raw'][key]
                existing=field['allowed_values_ast'] if key=='allowed_values' else (
                    field['byte_length_ast'] if key=='byte_length' else field['cardinality'])
                if raw and (existing is None or (key=='obligation' and existing['status']=='conditional_requires_formalization')):
                    unresolved.append({'kind':'field_constraint_formalization','field_id':field['id'],
                                       'constraint':key,'raw_value':raw,
                                       'source_ref':field['source_refs'][0],
                                       'reason':'Source text retained; no semantically approved AST for this constraint'})
    logical=[]
    for rule in data['rules']:
        if rule['kind']=='field_format':
            rule['formalization']['ast']={'op':'field_constraints','tag_path':rule['tag_path'],
                                         'constraints':rule['constraints']}
            continue
        condition=rule['raw']['condition'];check=rule['raw']['check']
        applicability=parse_source(condition) if condition.strip() else {
            'status':'blank_source_condition','ast':None,'reason':None,
            'normalized_source':'','transformation':'none','semantic_status':'pending'}
        violation=parse_source(check)
        both=(applicability['status'] in ('parsed','blank_source_condition') and violation['status']=='parsed')
        rule['formalization']={'status':'syntax_parsed_not_semantically_approved' if both else 'unsupported_or_partial',
                              'ast':{'applicability':applicability['ast'],'violation_candidate':violation['ast']},
                              'condition':applicability,'check':violation,
                              'executable':False,
                              'reason':'Requires code/scope, units, quantifier and condition/check/description agreement review'}
        logical.append(rule)
        unresolved.append({'kind':'logical_formalization','rule_id':rule['id'],
                           'source_ref':rule['source_refs'][0],
                           'syntax_status':rule['formalization']['status'],
                           'reason':rule['formalization']['reason'],
                           'condition_parse_reason':applicability['reason'],
                           'check_parse_reason':violation['reason']})
    # A tag mentioned only in a rule is not a fabricated field definition.
    by_tag={tag['tag']:tag for tag in data['tags'] if tag['occurrences']}
    references=defaultdict(set)
    for rule in logical:
        text='\n'.join(rule['raw'].values())
        for raw in re.findall(r'\(\s*(\d(?:\s*\d){3,4})\s*\)|тег(?:а|у|ом)?\s*[«"(]?\s*(\d{4,5})',text,flags=re.IGNORECASE):
            value=int(re.sub(r'\s+','',raw[0] or raw[1]))
            if 1000<=value<=65535:references[value].add(rule['id'])
    for tag in by_tag.values():
        tag['definition_status']='defined_in_document_format_table'
        tag['rule_references']=sorted(references.pop(tag['tag'],set()))
    for value,rules in references.items():
        by_tag[value]={'tag':value,'occurrences':[],'rule_references':sorted(rules),
                      'definition_status':'reference_only_not_a_field_definition'}
        unresolved.append({'kind':'reference_only_tag','tag':value,'rule_ids':sorted(rules),
                           'reason':'Mentioned by source logical table, absent from extracted field definitions; source may contain typo'})
    data['tags']=[by_tag[n] for n in sorted(by_tag)]
    data['unresolved']=unresolved
    data['formalization_summary']={'logical_rules':len(logical),
        'condition_syntax_parsed':sum(r['formalization']['condition']['status']=='parsed' for r in logical),
        'check_syntax_parsed':sum(r['formalization']['check']['status']=='parsed' for r in logical),
        'both_syntax_parsed':sum(r['formalization']['status']=='syntax_parsed_not_semantically_approved' for r in logical),
        'semantically_approved_logical_rules':0,'executable_logical_rules':0,
        'format_constraint_records':sum(r['kind']=='field_format' for r in data['rules'])}
    return data

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset-dir',type=Path,default=ROOT)
    args=parser.parse_args()
    for version in ['1.05','1.1','1.2']:
        path=args.dataset_dir/f'ffd-{version}.json';data=formalize(json.loads(path.read_text()))
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        print(version,data['formalization_summary'],'unresolved',len(data['unresolved']))
if __name__=='__main__':main()
