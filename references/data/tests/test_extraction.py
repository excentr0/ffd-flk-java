import json, subprocess, sys, tempfile, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
PY=Path(sys.executable)
class ExtractionTests(unittest.TestCase):
 def test_rebuild_and_source_audit(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)
   subprocess.run([str(PY),str(ROOT/'scripts/extract.py'),'--output-dir',str(out)],check=True)
   subprocess.run([str(PY),str(ROOT/'scripts/verify.py'),'--dataset-dir',str(out)],check=True)
   subprocess.run([str(PY),str(ROOT/'scripts/normalize.py'),'--dataset-dir',str(out)],check=True)
   subprocess.run([str(PY),str(ROOT/'scripts/formalize_data.py'),'--dataset-dir',str(out)],check=True)
   subprocess.run([str(PY),str(ROOT/'scripts/verify_semantics.py'),'--dataset-dir',str(out)],check=True,capture_output=True)
   validator=Draft202012Validator(json.loads((ROOT/'schema.json').read_text()))
   for v in ['1.05','1.1','1.2']:
    rebuilt=json.loads((out/f'ffd-{v}.json').read_text())
    validator.validate(rebuilt)
    current=json.loads((ROOT/f'ffd-{v}.json').read_text())
    self.assertEqual(rebuilt['documents'],current['documents'])
    self.assertEqual(rebuilt['rules'],current['rules'])
    self.assertEqual(rebuilt['tags'],current['tags'])
 def test_shift_open_code_536_not_stolen_from_inn_condition(self):
  data=json.loads((ROOT/'ffd-1.1.json').read_text())
  rule=next(r for r in data['rules'] if r['id']=='1.1:shift_open:logic:3')
  self.assertEqual(rule['code'],536)
  self.assertEqual(rule['raw']['code'],'536')
  self.assertTrue(rule['raw']['condition'].endswith('= 10'))
  self.assertNotIn('5= 10',rule['raw']['condition'])
  self.assertIn('source_transcription_correction',rule['source_refs'][0])
  raw=next(row for row in data['row_ledger'] if row.get('record_id')==rule['id'])
  self.assertIn('36',raw['raw_cells'])
  self.assertTrue(any('5= 10' in cell for cell in raw['raw_cells'] if cell))
  next_rule=next(r for r in data['rules'] if r['id']=='1.1:shift_open:logic:4')
  self.assertEqual(next_rule['code'],536)
 def test_poppler_caption_inventory(self):
  result=subprocess.run([str(PY),str(ROOT/'scripts/source_coverage.py')],check=True,capture_output=True,text=True)
  inventory=json.loads(result.stdout)
  self.assertEqual(inventory['missing_captions'],[])
  self.assertEqual(inventory['row_coverage'],'not audited; caption inventory only')
 def test_schema_validates_datasets(self):
  schema=json.loads((ROOT/'schema.json').read_text())
  validator=Draft202012Validator(schema)
  for v in ['1.05','1.1','1.2']:
   with self.subTest(version=v):
    dataset=json.loads((ROOT/f'ffd-{v}.json').read_text())
    self.assertEqual(list(validator.iter_errors(dataset)),[])
 def test_all_pdf_pages_preserved(self):
  for v,n in [('1.05',151),('1.1',195),('1.2',222)]:
   d=json.loads((ROOT/f'ffd-{v}.json').read_text())
   self.assertEqual(len(d['pages']),n)
   self.assertEqual([p['page_number'] for p in d['pages']],list(range(1,n+1)))
   self.assertTrue(all(p['text'] for p in d['pages']))
if __name__=='__main__': unittest.main()
