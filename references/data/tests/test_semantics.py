import copy
import json
from pathlib import Path
import sys
import unittest
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'sources' if (ROOT/'sources').is_dir() else ROOT.parent
sys.path.insert(0,str(ROOT/'scripts'))
from verify_semantics import audit
from formalize_data import parse_source,formalize

class SemanticExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets={v:json.loads((ROOT/f'ffd-{v}.json').read_text()) for v in ['1.05','1.1','1.2']}
        cls.validator=Draft202012Validator(json.loads((ROOT/'schema.json').read_text()))

    def test_all_contextual_source_rows_independently_accounted(self):
        for version,data in self.datasets.items():
            with self.subTest(version=version):
                result=audit(data,SOURCE)
                self.assertEqual(result['structural_issues'],[])
                self.assertEqual(result['numbered_row_sequence_missing'],0)
                self.assertEqual(result['field_records'],result['source_numbered_row_fragments'])
                self.assertFalse(data['readiness']['production_ready'])

    def test_document_discriminator_has_no_tlv_tag(self):
        for data in self.datasets.values():
            for doc in data['documents']:
                code=next(f for f in doc['fields'] if f['source_name']=='code')
                self.assertEqual(code['field_kind'],'document_discriminator')
                self.assertEqual(code['tag_numbers'],[])
                self.assertEqual(code['tag_path'],[])

    def test_no_rule_is_executable_or_implicitly_approved(self):
        for data in self.datasets.values():
            for rule in data['rules']:
                self.assertEqual(rule['semantic_review']['status'],'pending')
                if rule['kind']=='logical_source_rule':
                    self.assertFalse(rule['formalization']['executable'])
                    self.assertIsNotNone(rule['code'])
            self.assertEqual(data['formalization_summary']['semantically_approved_logical_rules'],0)

    def test_source_ordinal_conflict_does_not_reparent_root_container_to_leaf(self):
        fields=self.datasets['1.2']['documents'][4]['fields']
        root=next(f for f in fields if f['source_ordinal']=='38.25.1')
        self.assertEqual(root['tag_path'],[1084]);self.assertIsNone(root['parent_field_id'])
        self.assertTrue(root['printed_hierarchy_conflict'])
        child=next(f for f in fields if f['source_ordinal']=='38.25.2')
        self.assertEqual(child['tag_path'],[1084,1085])
        self.assertEqual(child['parent_field_id'],root['id'])

    def test_mutated_tag_and_discriminator_detected(self):
        data=copy.deepcopy(self.datasets['1.1'])
        data['documents'][0]['fields'][0]['tag_numbers']=[1]
        field=next(f for f in data['documents'][2]['fields'] if f['field_kind']=='tlv')
        field['tag_numbers']=[65535]
        kinds={u['kind'] for u in audit(data,SOURCE)['structural_issues']}
        self.assertIn('tag_transcription',kinds)
        self.assertIn('document_code_mistaken_for_tag',kinds)

    def test_deleted_field_detected_even_if_raw_ledger_survives(self):
        data=copy.deepcopy(self.datasets['1.05'])
        data['documents'][2]['fields'].pop()
        self.assertIn('ledger_field_missing',{u['kind'] for u in audit(data,SOURCE)['structural_issues']})

    def test_schema_rejects_discriminator_tags_and_wrong_tag_number_type(self):
        for property,value in [('tag_numbers',[1]),('tag_path',[1]),('tag_numbers','1')]:
            data=copy.deepcopy(self.datasets['1.1'])
            data['documents'][0]['fields'][0][property]=value
            self.assertTrue(list(self.validator.iter_errors(data)))

    def test_schema_rejects_empty_semantic_catalogs_and_ready_claim(self):
        for key,value in [('tags',[]),('documents',[]),('rules',[])]:
            data=dict(self.datasets['1.05']);data[key]=value
            self.assertTrue(list(self.validator.iter_errors(data)))
        data=dict(self.datasets['1.05']);data['readiness']=dict(data['readiness'],production_ready=True)
        self.assertTrue(list(self.validator.iter_errors(data)))

    def test_grammar_failure_retains_source_and_is_not_pass(self):
        text='SUM items.amount(1023) > 0'
        result=parse_source(text)
        self.assertEqual(result['status'],'unsupported');self.assertIsNone(result['ast'])
        self.assertEqual(result['semantic_status'],'pending')
        self.assertEqual(parse_source('EXIST userInn(1018) AND length(userInn) = 12')['status'],'parsed')

    def test_formalization_is_idempotent(self):
        data=copy.deepcopy(self.datasets['1.05'])
        self.assertEqual(formalize(data),self.datasets['1.05'])
        first=copy.deepcopy(data)
        self.assertEqual(formalize(data),first)
        for version in ['1.1','1.2']:
            self.assertEqual(formalize(copy.deepcopy(self.datasets[version])),self.datasets[version])

if __name__=='__main__':unittest.main()
