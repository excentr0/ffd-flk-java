import collections
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {
    '1.05': {32: 12, 33: 12, 34: 11, 35: 10, 36: 47, 37: 47, 38: 11, 39: 11},
    '1.1': {32: 12, 33: 12, 34: 11, 35: 10, 36: 54, 37: 54, 38: 11, 39: 11},
    '1.2': {32: 12, 33: 12, 34: 11, 35: 10, 36: 53, 37: 41, 38: 11, 39: 11},
}


class FlkReturnTests(unittest.TestCase):
    def test_catalog_context_and_scope(self):
        for version, counts in COUNTS.items():
            with self.subTest(version=version):
                data = json.loads((ROOT / f'flk-returns-{version}.json').read_text())
                entries = data['returns']
                self.assertEqual(dict(collections.Counter(e['table'] for e in entries)), counts)
                self.assertFalse({e['code'] for e in entries} & {400, 405, 409, 417, 419})
                self.assertEqual(data['scope'], 'PPFD_RETURN_CODE_TRANSCRIPTION_NOT_INCOMING_FLK_APPROVAL')
                self.assertEqual(data['flk_error_status']['value'], 2)
                self.assertEqual(data['flk_error_status']['codes'][-1], 533 if version == '1.2' else 511)
                self.assertTrue(any(e['table'] == 32 and e['code'] == 420
                                    and e['columns']['http_response'] == '400'
                                    and '<имя' in e['columns']['tag'] for e in entries))
                self.assertTrue(any(e['table'] == 36 and e['code'] == 536
                                    and e['columns']['http_response'] == '200'
                                    and e['columns']['tag'] == 'userInn' for e in entries))
                self.assertTrue(all(e['columns']['error_code'].strip() == str(e['code']) for e in entries))
                self.assertTrue(all(e['raw_cells'] and e['code_cell_bbox'] for e in entries))

    def test_rebuild_and_independent_poppler_codes(self):
        subprocess.run([sys.executable, str(ROOT / 'scripts/extract_flk_returns.py'), '--check'], check=True)
        subprocess.run([sys.executable, str(ROOT / 'scripts/audit_flk_returns.py')], check=True)


if __name__ == '__main__':
    unittest.main()
