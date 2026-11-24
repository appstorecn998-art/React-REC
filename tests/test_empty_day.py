import unittest
from unittest.mock import patch
import server
class EmptyDayTests(unittest.TestCase):
 def test_future_day_is_selectable_without_creating_report(self):
  with patch.object(server,'available_days',return_value={}),patch.object(server,'department_options',return_value=([],'')):
   value=server.load('2026-11-26')
  self.assertEqual(value['dayId'],'2026-11-26')
  self.assertEqual(value['receipts'],[])
  self.assertIn('26/11/2026',value['scope'])
 def test_malformed_date_rejected(self):
  for day in ['../../bad','2026-02-30','2026-1-1']:
   with self.assertRaises(ValueError):server.load(day)
if __name__=='__main__':unittest.main()
