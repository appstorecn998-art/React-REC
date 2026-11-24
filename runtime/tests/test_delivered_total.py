from pathlib import Path
import sys,tempfile,unittest
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
sys.path.append('C:/Users/Fenn/Desktop/Auto/tests')
from received_amounts import DELIVERED_TOTAL_HEADER,apply_delivered_total
from test_merge_saved_delivery import add_invoice
from manual_invoice_links import merge_saved_invoices

class DeliveredTotalTests(unittest.TestCase):
 def test_new_report_and_merged_report_have_single_total_for_all_rows(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.JPG')
   merge_saved_invoices(p,['A','B'])
   w=load_workbook(p);s=w.active
   headers={c.value:c.column_letter for c in s[1]}
   col=headers[DELIVERED_TOTAL_HEADER];amount=headers['Thành tiền trên phiếu']
   self.assertEqual(s[f'{col}2'].value,f'=IF(COUNT({amount}2:{amount}3)<>COUNTA(A2:A3),"CHƯA ĐỦ DỮ LIỆU",SUM({amount}2:{amount}3))')
   self.assertIsNone(s[f'{col}3'].value)
   self.assertFalse(apply_delivered_total(s));w.close()
 def test_total_only_upgrade_preserves_custom_existing_values(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG')
   w=load_workbook(p);s=w.active
   c=next(c.column for c in s[1] if c.value==DELIVERED_TOTAL_HEADER);s.delete_cols(c)
   s['Y2']='=SUM(P2:P2)';s['P2']='=N2*O2';before=[[c.value for c in r] for r in s]
   self.assertTrue(apply_delivered_total(s))
   for r,row in enumerate(before,1):
    for c,v in enumerate(row,1):self.assertEqual(s.cell(r,c).value,v)
   self.assertFalse(apply_delivered_total(s));w.close()
