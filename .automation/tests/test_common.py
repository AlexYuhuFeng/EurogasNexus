import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import classify_output,parse_reset_epoch
class T(unittest.TestCase):
    def test_limit(self):self.assertEqual(classify_output("You've hit your usage limit. Try again at Sep 20th, 2026 7:11 PM.",1),'allowance')
    def test_success(self):self.assertEqual(classify_output('ok',0),'success')
    def test_date(self):self.assertIsNotNone(parse_reset_epoch('try again at Sep 20th, 2026 7:11 PM.'))
    def test_date_without_year(self):self.assertIsNotNone(parse_reset_epoch('try again at Sep 20th 7:11 PM'))
    def test_time_only(self):self.assertIsNotNone(parse_reset_epoch('try again at 7:11 PM'))
    def test_unknown_reset(self):self.assertIsNone(parse_reset_epoch('usage limit reached; wait for reset'))
if __name__=='__main__':unittest.main()
