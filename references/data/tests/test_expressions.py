import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from expressions import parse_expression

class ParseExpressionTests(unittest.TestCase):
    def test_real_ffd_105_existence_condition_page_28(self):
        r=parse_expression('offlineMode(1002) = 0')
        self.assertEqual(r['status'],'parsed')
        self.assertEqual(r['ast']['left']['path'],[{'name':'offlineMode','tag':1002}])
    def test_real_ffd_105_check_page_28(self):
        r=parse_expression('EXIST userInn(1018) AND length(userInn) = 10')
        self.assertEqual(r['status'],'parsed')
        self.assertEqual(r['ast']['op'],'and')
    def test_not_exist(self): self.assertEqual(parse_expression('NOT EXIST ofdName(1046)')['ast']['negated'],True)
    def test_multiplication_precedence(self):
        ast=parse_expression('a(1020) + b(1031) * 2 = c(1081)')['ast']['left']
        self.assertEqual(ast['op'],'+')
        self.assertEqual(ast['right']['op'],'*')
    def test_invalid_tag_annotations(self):
        for source in ('EXIST a(foo)','EXIST a(70000)','EXIST a(1.5)'):
            self.assertEqual(parse_expression(source)['status'],'unsupported')
    def test_tag_path_preserves_container_segments(self):
        ast=parse_expression('EXIST item(1059).amount(1023)')['ast']
        self.assertEqual([p['tag'] for p in ast['path']],[1059,1023])
    def test_literal_in_and_exact_number(self):
        r=parse_expression("mode(1) IN ('A', 'B')")
        self.assertEqual(r['status'],'parsed')
        self.assertEqual(r['ast']['set'][0]['value'],'A')
        self.assertEqual(parse_expression('amount(1) = 0.10')['ast']['right']['value'],'0.10')
    def test_reject_leftover_and_malformed(self):
        for s in ('EXIST field(1) rubbish','field(1) =','field(1) IN (other(2))','sum(item(1)) > 0',''):
            with self.subTest(s=s): self.assertEqual(parse_expression(s)['status'],'unsupported')

if __name__=='__main__': unittest.main()
