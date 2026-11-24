from pathlib import Path
import sys
import tempfile
import unittest
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
sys.path.append('C:/Users/Fenn/Desktop/Auto/tests')
from received_amounts import DELIVERED_AMOUNT_HEADER,apply_received_amounts,upgrade_received_amounts
from test_merge_saved_delivery import add_invoice
from manual_invoice_links import merge_saved_invoices

class DeliveredAmountsTests(unittest.TestCase):
 def test_new_sheet_and_merge_keep_both_formulas(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.JPG')
   merge_saved_invoices(p,['A','B'])
   w=load_workbook(p);s=w.active;c=next(c.column for c in s[1] if c.value==DELIVERED_AMOUNT_HEADER)
   self.assertEqual(s.cell(3,c).value,'=IF(COUNT(M3,O3)=2,M3*O3,"CHƯA RÕ")')
   self.assertEqual(s['P3'].value,'=IF(COUNT(N3,O3)=2,N3*O3,"CHƯA RÕ")')
   self.assertEqual(s['N3'].value,0);w.close()
 def test_upgrade_only_adds_column_preserves_existing_values_and_is_idempotent(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG')
   w=load_workbook(p);s=w.active;c=next(c.column for c in s[1] if c.value==DELIVERED_AMOUNT_HEADER)
   s.delete_cols(c);s['M2']=3;s['N2']=1;s['O2']=12.5;s['G2']='Sửa tay';w.save(p);w.close()
   self.assertEqual(upgrade_received_amounts(p),1)
   w=load_workbook(p);s=w.active;c=next(c.column for c in s[1] if c.value==DELIVERED_AMOUNT_HEADER)
   self.assertEqual(s.cell(2,c).value,'=IF(COUNT(M2,O2)=2,M2*O2,"CHƯA RÕ")')
   self.assertEqual([s[k].value for k in ['M2','N2','O2','G2']],[3,1,12.5,'Sửa tay']);w.close()
   before=p.read_bytes();self.assertEqual(upgrade_received_amounts(p),0);self.assertEqual(p.read_bytes(),before)
