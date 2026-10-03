#!/usr/bin/env python3
"""Reconstruct contextual fields and logical-control rows from original PDF grids.

Source text/geometry remains authoritative. Syntax parsing is not semantic approval.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT/'sources' if (ROOT/'sources').is_dir() else ROOT.parent
DOCUMENTS = [
    ('registration', 'Отчет о регистрации', [1]),
    ('registration_change', 'Отчет об изменении параметров регистрации', [11]),
    ('shift_open', 'Отчет об открытии смены', [2]),
    ('current_state', 'Отчет о текущем состоянии расчетов', [21]),
    ('receipt', 'Кассовый чек / БСО', [3, 4]),
    ('correction_receipt', 'Кассовый чек коррекции / БСО коррекции', [31, 41]),
    ('shift_close', 'Отчет о закрытии смены', [5]),
    ('fn_close', 'Отчет о закрытии фискального накопителя', [6]),
]
SPECS = [('1.05', 'FFD_1.05_OFD-FNS_v9.8.pdf'),
         ('1.1', 'FFD_1.1_OFD-FNS_v3.8.pdf'),
         ('1.2', 'FFD_1.2_OFD-FNS_v2.15.pdf')]
HEADER_WORDS = ('Наименование', 'Номер', 'Допусти', 'Обяза', 'Описание проверки',
                'Категор', 'гория', 'срабатыва', 'пользователю', 'Проверка', 'Кате-')

def compact(value):
    return re.sub(r'\s+', '', value or '')

def prose(value):
    return re.sub(r'\s+', ' ', value or '').strip()

def clusters(values, tolerance=14):
    groups = []
    for value in sorted(set(values)):
        if groups and value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups

def logical_grid(table, logical_kind='format', previous_centers=None):
    """Map FLK cell geometry to six column centers, preserving split headers."""
    raw = table.extract()
    if logical_kind == 'logic':
        if raw and len(raw[0])==6:
            centers={}
            for column in range(6):
                box=next((row.cells[column] for row in table.rows if row.cells[column] is not None),None)
                if box is not None:centers[column]=(box[0]+box[2])/2
            return [(i+1,[v or '' for v in row],row) for i,row in enumerate(raw)], centers
        centers = dict(previous_centers or {})
        labels = {0: ('Кате-', 'Катего', 'Категор'), 2: ('Условие',),
                  3: ('Проверка',), 4: ('Значение и', 'Сообщение'), 5: ('Описание проверки',)}
        for ri, row in enumerate(raw[:8]):
            for ci, value in enumerate(row):
                if not value:
                    continue
                cell = table.rows[ri].cells[ci]
                if cell is None:
                    continue
                midpoint = (cell[0]+cell[2])/2
                for target, prefixes in labels.items():
                    if value.strip() in prefixes:
                        centers[target] = midpoint
                if re.fullmatch(r'\d{3}', compact(value)):
                    centers[1] = midpoint
                elif compact(value) in ('Код', 'КодФЛК', 'КодошибкиФЛК'):
                    centers.setdefault(1, midpoint)
        if len(centers) == 6:
            result = []
            for ri, row in enumerate(raw):
                output = ['']*6
                for ci, value in enumerate(row):
                    if not value:
                        continue
                    cell = table.rows[ri].cells[ci]
                    if cell is None:
                        continue
                    midpoint = (cell[0]+cell[2])/2
                    target = min(centers, key=lambda i: abs(centers[i]-midpoint))
                    output[target] += ('\n' if output[target] else '') + value
                result.append((ri+1, output, row))
            return result, centers
        if raw and len(raw[0]) == 6:
            return [(i+1, [v or '' for v in row], row) for i,row in enumerate(raw)], centers
    xs = sorted({x for cell in table.cells for x in (cell[0], cell[2])})
    groups = clusters(xs)
    mapping = {x: i for i, group in enumerate(groups) for x in group}
    raw = table.extract()
    result = []
    for index, row in enumerate(raw):
        output = [''] * (len(groups) - 1)
        for column, value in enumerate(row):
            if value is not None and column < len(xs)-1:
                target = mapping[xs[column]]
                if target < len(output) and value:
                    output[target] += ('\n' if output[target] else '') + value
        result.append((index + 1, output, row))
    return result, groups

def is_header(cells):
    if re.fullmatch(r'\d+(?:\.\d+)*\.?', compact(cells[0])):
        return False
    if len(cells)==6 and re.fullmatch(r'\d{3}',compact(cells[1])):
        return False
    parts={'№','№п/п','№пп','п/п','пп','Номер','тега','Наименование','Наимено-',
           'ние','ние тега','Наименова-','вание','реквизита','ние реквизита','Обяза-',
           'Обязатель-','тельность','Обяза-тельность','тель-','ность','Тип','Допустимые',
           'Допустимый','Допусти-','Допусти-мый','мые','мый','значения','размер','Код','ФЛК',
           'Кате-','Катего','Категор','гория','рия','ия','КодФЛК','К\nФ','од','ЛК',
           'Условие','срабаты-','срабатывания','срабатыва-','вания','ния','Проверка',
           'Значение и','сообщение','Сообщение','Описание проверки','пользователю',
           'р тега','Допусти-мые','Обяза-тель-'}
    parts.update({'Номе','Номер тега','Наименование тега','Наимено-вание','Допустимы',
                  'й размер','Допустимые значения','Допус-','тимый','Категори','Катег','ория',
                  'я','а','ошибки','ошиб','оши','бки','ки','ания','срабатыв','Код ошибки',
                  'Код ошибки ФЛК','Сообщение пользователю','Условие срабатывания',
                  'е значения','Услови','е','срабат','срабатывани','с','ывания','рабатыван'})
    tokens=sorted({re.sub(r'[-\s]','',x) for x in parts},key=len,reverse=True)
    def header_cell(value):
        value=re.sub(r'[-\s]','',value)
        while value:
            token=next((t for t in tokens if value.startswith(t)),None)
            if token is None:return False
            value=value[len(token):]
        return True
    return all(header_cell(c) for c in cells if c)

def tag_numbers(raw, ordinal, field_name):
    if field_name == 'code':
        # `code` is a document discriminator, not a fiscal TLV tag.
        return [], 'document_discriminator'
    candidates = re.findall(r'(?<!\d)\d{4}(?!\d)', raw)
    if len(candidates) == 1:
        return [int(candidates[0])], 'tlv'
    # FFD1.2 prints 130 9 / 132 0 etc; FFD1.1 additionally leaks a
    # duplicate row ordinal into the tag-number column. Strip that only when
    # the exact ordinal is established, never truncate a real tag.
    clean = compact(raw)
    if clean.isdigit() and len(clean) == 4:
        return [int(clean)], 'tlv'
    if not clean or clean == compact(ordinal):
        return [], 'non_tlv_source_field'
    return [], 'unresolved'

def decimal_literal(value):
    return format(Decimal(value.replace(',', '.')), 'f')

def domain(raw):
    clean = compact(raw)
    if not clean:
        return None
    if re.fullmatch(r'\{\d+(?:,\d+)*\}', clean):
        return {'op': 'in', 'values': [str(int(x)) for x in clean[1:-1].split(',')],
                'unit': 'source_numeric_value'}
    match = re.fullmatch(r'([\[(])(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)([])])', clean)
    if match:
        return {'op': 'range', 'minimum': decimal_literal(match[2]),
                'maximum': decimal_literal(match[3]), 'minimum_inclusive': match[1]=='[',
                'maximum_inclusive': match[4]==']', 'unit':'source_numeric_value'}
    if clean.casefold() in ('непустой', 'непустое', 'непустая'):
        return {'op': 'not_empty'}
    return None

def byte_length(raw):
    clean = compact(raw).replace('*','')
    if not clean:
        return None
    if clean.isdigit():
        return {'op':'byte_length', 'minimum':int(clean),'maximum':int(clean)}
    match = re.fullmatch(r'\[(\d+),(\d+)\]', clean)
    if match:
        return {'op':'byte_length', 'minimum':int(match[1]),'maximum':int(match[2])}
    if re.fullmatch(r'\d+или\d+',clean):
        return {'op':'byte_length_in','values':[int(x) for x in re.findall(r'\d+',clean)]}
    return None

def cardinality(raw, size):
    clean = compact(raw).casefold()
    repeated = '*' in size or clean in ('1...n', '1…n', '1..n')
    if clean in ('0','1'):
        return {'minimum':int(clean),'maximum':None if repeated else 1,
                'repeat_evidence':'array_asterisk_note' if '*' in size else 'singleton_default_pending_repeat_review',
                'status':'source_literal' if repeated else 'minimum_source_literal_maximum_requires_policy_review'}
    if clean in ('1...n','1…n','1..n'):
        return {'minimum':1,'maximum':None,'repeat_evidence':'source_obligation','status':'source_literal'}
    if clean in ('x','х'):
        return {'status':'not_applicable','minimum':None,'maximum':None}
    return {'status':'conditional_requires_formalization','minimum':None,'maximum':None,
            'raw_condition':raw}

def reference(version, page, table, fragment_index, row_index, bbox, ordinal=None):
    return {'ffd_version':version,'page':page,'table_number':table,
            'fragment_index':fragment_index,'physical_row_index':row_index,
            'bbox':bbox,'source_ordinal':ordinal}

def raw_append(field, cells, ref):
    for key, value in zip(('ordinal','tag_number','name','description','obligation','type','allowed_values','byte_length','flk_codes'),cells):
        if value:
            existing=field['raw'][key]
            field['raw'][key]=existing+('\n' if existing else '')+value
    field['source_refs'].append(ref)

def normalize(version, data, pdf_path):
    documents = []
    for index, (identifier,name,codes) in enumerate(DOCUMENTS):
        documents.append({'id':identifier,'name':name,'document_codes':codes,
                          'format_table':14+index*2,'logic_table':15+index*2,
                          'incoming_flk_exempt':index<2,
                          'exemption_source':{'page':11,'section':'4'} if index<2 else None,
                          'fields':[], 'logical_rule_ids':[]})
    docs_by_table = {doc['format_table']:doc for doc in documents}
    docs_by_table.update({doc['logic_table']:doc for doc in documents})
    rules=[]; ledger=[]; unresolved=[]; notes=[]
    active_table=None; last_fields={}; last_rules={}; categories={}; codes={}; logic_centers={}
    with pdfplumber.open(pdf_path) as pdf:
        for page_number,page in enumerate(pdf.pages,1):
            if page_number < 24:
                continue
            captions=page.search(r'Таблица\s+(\d+)\s*[–—-]') or []
            captions=sorted([(m['top'],int(re.search(r'\d+',m['text'])[0])) for m in captions])
            # Once table 30 (output errors) begins, incoming-format/logic inventory is complete.
            if active_table is not None and active_table>=30:
                break
            for fragment_index,table in enumerate(page.find_tables() or [],1):
                for top,number in captions:
                    if top<=table.bbox[1]+3:
                        active_table=number
                if active_table not in docs_by_table or table.bbox[2]-table.bbox[0]<400:
                    continue
                doc=docs_by_table[active_table]
                grid,xgroups=logical_grid(table, 'format' if active_table%2==0 else 'logic', logic_centers.get(active_table))
                if active_table%2 and isinstance(xgroups,dict) and len(xgroups)==6:
                    logic_centers[active_table]=xgroups
                expected=(8,9) if active_table%2==0 else (6,)
                if not grid or len(grid[0][1]) not in expected:
                    unresolved.append({'kind':'table_geometry','reason':'Unexpected logical column count',
                                       'actual':len(grid[0][1]) if grid else 0,
                                       'source_ref':reference(version,page_number,active_table,fragment_index,0,list(table.bbox))})
                    continue
                source_grid=[row[2] for row in grid]
                for physical_row,cells,raw_cells in grid:
                    ref=reference(version,page_number,active_table,fragment_index,physical_row,list(table.bbox))
                    row_record={'table_number':active_table,'source_ref':ref,'raw_cells':raw_cells,
                                'logical_cells':cells,'classification':None}
                    ledger.append(row_record)
                    if is_header(cells) or not any(cells):
                        row_record['classification']='header_or_empty'; continue
                    if active_table%2==0:
                        ordinal=compact(cells[0]).rstrip('.')
                        if not re.fullmatch(r'\d+(?:\.\d+)*',ordinal):
                            if not cells[0] and active_table in last_fields:
                                raw_append(last_fields[active_table], cells+([''] if len(cells)==8 else []),ref)
                                row_record.update(classification='field_continuation',record_id=last_fields[active_table]['id'])
                            else:
                                row_record['classification']='unclassified'
                                unresolved.append({'kind':'unclassified_field_row','reason':'Cannot associate source row',
                                                   'source_ref':ref,'cells':cells})
                            continue
                        field={'id':f'{version}:{doc["id"]}:field:{ordinal}',
                               'source_ordinal':ordinal,'source_refs':[dict(ref,source_ordinal=ordinal)],
                               'raw':dict(zip(('ordinal','tag_number','name','description','obligation','type','allowed_values','byte_length','flk_codes'),cells+([''] if len(cells)==8 else [])))}
                        prior=last_fields.get(active_table)
                        if prior and prior['source_ordinal']==ordinal:
                            raw_append(prior,cells+([''] if len(cells)==8 else []),ref)
                            row_record.update(classification='field_continuation',record_id=prior['id']);continue
                        doc['fields'].append(field);last_fields[active_table]=field
                        row_record.update(classification='field',record_id=field['id'])
                    else:
                        # FFD 1.1 p.43, table 19: pdfplumber puts the leading 5 of
                        # code 536 into the adjacent INN condition. Preserve the
                        # extracted raw_cells; correct only the interpreted cells.
                        if (version=='1.1' and active_table==19 and page_number==43
                                and physical_row==9 and compact(cells[1])=='36'
                                and cells[2].endswith('\n5= 10')):
                            cells[1]='536'
                            cells[2]=cells[2][:-len('\n5= 10')]+'\n= 10'
                            ref['source_transcription_correction']={
                                'reason':'PDF code-column glyph crossed extraction cell boundary',
                                'evidence':'Original PDF p.43 table 19; Poppler bbox and rendered page',
                                'original_code_cell':'36', 'original_condition_tail':'5= 10'}
                        category,code,condition,check,message,description=cells
                        # A merged source code cell can contain several codes vertically
                        # (FFD1.05 table29: 502/503/536). Read the original code column
                        # at this row's own y interval, not the merged cell's full height.
                        centers=logic_centers.get(active_table)
                        if centers and len(centers)==6:
                            source_row=table.rows[physical_row-1]
                            content_boxes=[];check_boxes=[]
                            for ci,value in enumerate(raw_cells):
                                box=source_row.cells[ci]
                                if value and box is not None:
                                    mid=(box[0]+box[2])/2
                                    role=min(centers,key=lambda k:abs(centers[k]-mid))
                                    if role>=2:content_boxes.append(box)
                                    if role==3:check_boxes.append(box)
                            if content_boxes:
                                if check_boxes:
                                    top=min(b[1] for b in check_boxes)
                                    bottom=max(b[3] for b in check_boxes)
                                else:
                                    top=max(b[1] for b in content_boxes)
                                    bottom=min(b[3] for b in content_boxes)
                                if check_boxes and bottom>top:
                                    for source_index,source_values in enumerate(source_grid):
                                        for column,value in enumerate(source_values):
                                            box=table.rows[source_index].cells[column]
                                            if not value or box is None:continue
                                            role=min(centers,key=lambda k:abs(centers[k]-(box[0]+box[2])/2))
                                            if role==2 and box[1]<=top+1 and box[3]>=bottom-1:
                                                condition=value
                                                ref['condition_cell_origin']={'physical_row_index':source_index+1,'bbox':list(box)}
                                                # Separate the two INN conditions printed inside
                                                # a single source cell, aligned with distinct checks.
                                                if value.count('EXIST')>=2 and value.count('length')>=2:
                                                    condition=page.crop((box[0],top,box[2],bottom)).extract_text() or ''
                                                    ref['condition_cell_origin']['method']='check_y_interval_crop'
                                                else:
                                                    ref['condition_cell_origin']['method']='source_cell_span'
                                                cells[2]=condition
                                                ref['row_y_interval']=[top,bottom]
                                                break
                                        else:continue
                                        break
                                left=(centers[0]+centers[1])/2
                                right=(centers[1]+centers[2])/2
                                if bottom>top:
                                    cropped=page.crop((left,top,right,bottom)).extract_text() or ''
                                    found=re.findall(r'(?<!\d)\d{3}(?!\d)',cropped)
                                    if len(set(found))==1:
                                        code=found[0];cells[1]=code
                        if category: categories[active_table]=category
                        if re.fullmatch(r'\d{3}',compact(code)):
                            codes[active_table]=int(compact(code))
                        if not any((condition,check,message,description)):
                            row_record['classification']='non_rule_fragment';continue
                        prior=last_rules.get(active_table)
                        # Geometry may split one description into several physical rows.
                        # Never append a complete new condition to the preceding rule merely
                        # because it is on a new page (INN length10 and length12 are distinct).
                        same_code=prior is not None and codes.get(active_table)==prior['code']
                        continuation=(same_code and not condition and not check)
                        continuation=continuation or (same_code and check and not condition and not prior['raw']['check'])
                        if continuation:
                            for key,value in zip(('category','code','condition','check','message','description'),cells):
                                if value and key not in ('category','code'):
                                    prior['raw'][key]+=('\n' if prior['raw'][key] else '')+value
                            prior['source_refs'].append(ref)
                            row_record.update(classification='rule_continuation',record_id=prior['id']);continue
                        index=len(doc['logical_rule_ids'])+1
                        identifier=f'{version}:{doc["id"]}:logic:{index}'
                        rule={'id':identifier,'document':doc['id'],'kind':'logical_source_rule',
                              'code':codes.get(active_table),'category_raw':categories.get(active_table,''),
                              'scope':'PPFD_LOGICAL_TABLE_REQUIRES_INCOMING_APPLICABILITY_REVIEW',
                              'incoming_flk_exempt_document':doc['incoming_flk_exempt'],
                              'raw':dict(zip(('category','code','condition','check','message','description'),cells)),
                              'source_refs':[ref],'formalization':{'status':'not_formalized','ast':None},
                              'semantic_review':{'status':'pending','reason':'Requires source condition/check/description agreement and input-vs-PPFD scope review'}}
                        rules.append(rule);doc['logical_rule_ids'].append(identifier);last_rules[active_table]=rule
                        row_record.update(classification='logical_rule',record_id=identifier)
            # Captions on a page WITHOUT a detected table still advance the state.
            # FFD1.1 table25 title occupies page83, but its first grid starts page84.
            if captions:
                active_table=captions[-1][1]
            # Outside-table text remains verbatim in pages. Keep a separate note ledger too.
            text=page.extract_text() or ''
            if any(key in text for key in ('Примечание','Примечания','* –','* -')) and active_table in docs_by_table:
                notes.append({'page':page_number,'near_table':active_table,'text':text,
                              'status':'full_page_note_context_preserved_requires_rule_association'})
            if any(number>=30 for _,number in captions):
                break
    tag_index=defaultdict(list)
    for doc in documents:
        by_ordinal={field['source_ordinal']:field for field in doc['fields']}
        by_name={}
        for field in doc['fields']:
            raw=field['raw']; field['source_name']=compact(raw['name'])
            field['type']=compact(raw['type']);field['name']=prose(raw['description'])
            nums,kind=tag_numbers(raw['tag_number'],field['source_ordinal'],field['source_name'])
            field['tag_numbers']=nums;field['field_kind']=kind
            field['allowed_values_ast']=domain(raw['allowed_values'])
            field['byte_length_ast']=byte_length(raw['byte_length'])
            field['cardinality']=cardinality(raw['obligation'],raw['byte_length'])
            field['flk_code_references']=[int(x) for x in re.findall(r'(?<!\d)\d{3}(?!\d)',raw['flk_codes'])]
            field['parent_field_id']=None;field['tag_path']=[]
            if kind=='unresolved':
                unresolved.append({'kind':'tag_number','reason':'Ambiguous/missing tag number',
                                   'field_id':field['id'],'source_ref':field['source_refs'][0],
                                   'raw_value':raw['tag_number']})
            by_name[field['source_name']]=field
        for field in doc['fields']:
            ordinal=field['source_ordinal'];parent=None
            if '.' in field['source_name']:
                prefix=field['source_name'].rsplit('.',1)[0]
                parent=by_name.get(prefix)
                evidence='explicit_dotted_name_and_STLV_parent_row'
                if parent is None and '.' in ordinal:
                    parent=by_ordinal.get(ordinal.rsplit('.',1)[0])
                    evidence='printed_ordinal_fallback_requires_name_review'
            else:
                evidence='root_source_name'
            ordinal_parent=by_ordinal.get(ordinal.rsplit('.',1)[0]) if '.' in ordinal else None
            field['printed_hierarchy_conflict']=(ordinal_parent is not None and
                                                (parent is None or parent['id']!=ordinal_parent['id']))
            if field['printed_hierarchy_conflict']:
                field['hierarchy_note']='Source ordinal hierarchy disagrees with named STLV path; exact source ordinal retained, named container row selected.'
            if parent and parent['type']!='STLV':
                unresolved.append({'kind':'parent_type','reason':'Printed/name parent is not STLV',
                                   'field_id':field['id'],'parent_id':parent['id'],
                                   'source_ref':field['source_refs'][0]})
                parent=None
            if '.' in field['source_name'] and parent is None:
                unresolved.append({'kind':'parent_path','reason':'No verified parent container',
                                   'field_id':field['id'],'source_ref':field['source_refs'][0]})
            field['parent_field_id']=parent['id'] if parent else None
            field['parent_evidence']=evidence
            field['semantic_review_status']='structurally_reconstructed_not_manually_approved'
        by_id={field['id']:field for field in doc['fields']}
        def path_for(field, seen=None):
            seen=set() if seen is None else seen
            if field['id'] in seen:raise ValueError('Parent cycle '+field['id'])
            seen.add(field['id'])
            parent=by_id.get(field['parent_field_id'])
            return (path_for(parent,seen) if parent else [])+field['tag_numbers']
        for field in doc['fields']:
            field['tag_path']=path_for(field) if field['field_kind']=='tlv' else []
            for number in field['tag_numbers'] if field['field_kind']=='tlv' else []:
                tag_index[number].append({'document':doc['id'],'field_id':field['id'],
                                         'tag_path':field['tag_path'],'type':field['type'],
                                         'source_refs':field['source_refs']})
            if not doc['incoming_flk_exempt'] and field['field_kind']=='tlv':
                rules.append({'id':field['id']+':format','document':doc['id'],'kind':'field_format',
                              'scope':'KKT_TO_OFD_FORMAT','source_refs':field['source_refs']+[{'page':11,'section':'4'}],
                              'field_id':field['id'],'tag_path':field['tag_path'],
                              'applicability':{'op':'container_present','tag_path':field['tag_path'][:-1]},
                              'constraints':{'requiredness':deepcopy(field['cardinality']),
                                             'type':field['type'],'allowed_values':field['allowed_values_ast'],
                                             'byte_length':field['byte_length_ast']},
                              'codes':{'missing_required':420,'wrong_type_required':421,'wrong_type_optional':321,
                                       'invalid_value_required':422,'invalid_value_optional':322,'repeat':424,'unexpected_tag':423},
                              'formalization':{'status':'structural_constraints_partially_formalized','ast':None},
                              'semantic_review':{'status':'pending','reason':'Byte/value interpretation and cardinality maximum require context review'}})
    data['documents']=documents;data['rules']=rules
    data['tags']=[{'tag':number,'occurrences':items} for number,items in sorted(tag_index.items())]
    data['source_refs']=[row['source_ref'] for row in ledger]
    data['row_ledger']=ledger;data['notes']=notes;data['unresolved']=unresolved
    data['general_requirements']=[{'section':str(n),'source_pages':ps,
                                  'text':'\n'.join(data['pages'][i-1]['text'] for i in ps)}
                                 for n,ps in [(1,[6,7]),(2,[8]),(3,[9,10]),(4,[11,12])]]
    data['revision_statements']=[{'page':p['page_number'],'text':p['text']}
                                 for p in data['pages'] if 'Актуальность документа' in p['text'] and p['page_number']<10]
    source_names={'1.05':'ffd105_v978_05052026.pdf','1.1':'ffd11_v38_05052026.pdf','1.2':'ffd12_215_051052026.pdf'}
    data['source']['url']='https://kkt-online.nalog.ru/html/sites/www.kkt-online.nalog.ru/materials/'+source_names[version]
    data['source']['official_portal_url']='https://kkt-online.nalog.ru/materials/'
    data['extraction_status']='structured_extraction_pending_semantic_review'
    data['readiness']={'production_ready':False,'reason':'Logical rule scope/formula review incomplete; syntactic AST is not normative approval'}
    return data

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset-dir',type=Path,default=ROOT)
    args=parser.parse_args()
    for version,filename in SPECS:
        path=args.dataset_dir/f'ffd-{version}.json'
        data=json.loads(path.read_text())
        normalized=normalize(version,data,SOURCE_ROOT/filename)
        path.write_text(json.dumps(normalized,ensure_ascii=False,indent=2)+'\n')
        print(version,'unique tags',len(normalized['tags']),'fields',sum(len(d['fields']) for d in normalized['documents']),
              'logical rules',sum(r['kind']=='logical_source_rule' for r in normalized['rules']),
              'issues',len(normalized['unresolved']))
if __name__=='__main__': main()
