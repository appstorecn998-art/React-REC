import unittest
import copy
import AutoWatcher as aw
from receipt_rules import apply_receipt_rules
class QuantityFormatTests(unittest.TestCase):
 def test_alternatives_and_missing_evidence(self):
  for raw,price,amount,expected in [('4,000','30.000,000','120.000','4'),('1,500','55.000,000','82.500','1.5'),('1,000','2','2000','1000'),('1,000','','1000','1,000'),('1,000','20','35','1,000'),('1,000','0','0','1,000')]:
   with self.subTest(raw=raw,price=price,amount=amount):
    i=dict(quantity=raw,unit_price=price,line_amount=amount);aw.resolve_quantity_separator(i);self.assertEqual(i['quantity'],expected)
  self.assertIsNone(aw.parse_simple_quantity('1,000'))
 def test_marks_and_idempotence(self):
  for mark,received,want in [('check','','4'),('unmarked','','4'),('written','3.5','3.5'),('cross_without_number','','0'),('unclear','','')]:
   i=dict(quantity='4,000',unit_price='30.000,000',line_amount='120.000',receipt_mark=mark,received_quantity=received)
   aw.resolve_quantity_separator(i);apply_receipt_rules(i,aw.parse_simple_quantity);first=copy.deepcopy(i)
   aw.resolve_quantity_separator(i);apply_receipt_rules(i,aw.parse_simple_quantity);self.assertEqual(i,first)
   self.assertEqual(aw.parse_simple_quantity(i['received_quantity']),aw.parse_simple_quantity(want))
