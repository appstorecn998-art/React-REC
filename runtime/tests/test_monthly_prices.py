import os,sys,tempfile,unittest
from pathlib import Path
from datetime import date
os.environ['QT_QPA_PLATFORM']='offscreen';stage=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(stage),str(app),str(app/'tests')]
from receiving_monthly_prices import scan
from openpyxl import Workbook
class PriceTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def report(self,day,rows):
  folder=self.root/'Thang 11'/f'Ngay {day:02d}';folder.mkdir(parents=True,exist_ok=True);path=folder/f'TongHopPhieuNgay_{day:02d}-11-2026.xlsx';book=Workbook();sheet=book.active;sheet.title=f'IMG_{day}';sheet.append(['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Thực nhận','Đơn giá','Nhà cung cấp'])
  for row in rows:sheet.append(row)
  book.save(path);book.close();return path
 def test_distinct_purchases_prices_exact_and_cross_supplier(self):
  self.report(3,[['A','001','kg',1,100,'NCC1']]);self.report(4,[['A','001','kg',2,120,'NCC2']]);result=scan(self.root,self.root,date(2026,11,14));self.assertEqual(len(result['warnings']),0);self.report(5,[['A','001','kg',1,120,'NCC1']]);self.report(6,[['A','001','kg',1,100,'NCC1']]);result=scan(self.root,self.root,date(2026,11,14));self.assertEqual(len(result['warnings']),1);self.assertEqual(result['warnings'][0]['purchases'],3);self.assertEqual(result['warnings'][0]['increase'],'20');self.assertEqual(result['warnings'][0]['prices'],['100','120'])
 def test_same_price_one_invoice_different_units_and_spec_not_merged(self):
  self.report(3,[['A','001','kg',1,100,'NCC'],['A','001','kg',2,120,'NCC']]);self.assertFalse(scan(self.root,self.root,date(2026,11,14))['warnings'])
  self.report(4,[['A','001','bịch',1,150,'NCC'],['A 2kg','001','kg',1,200,'NCC']]);self.assertFalse(scan(self.root,self.root,date(2026,11,14))['warnings'])
 def test_missing_code_requires_exact_name_zero_receipt_excluded(self):
  self.report(3,[['A','CHUA CO MA','kg',1,100,'NCC'],['B','002','kg',0,100,'NCC']]);self.report(4,[['A khác','CHUA CO MA','kg',1,150,'NCC'],['B','002','kg',1,200,'NCC']]);self.assertFalse(scan(self.root,self.root,date(2026,11,14))['warnings']);self.report(5,[['A','CHUA CO MA','kg',1,150,'NCC']]);self.report(6,[['A','CHUA CO MA','kg',1,100,'NCC']]);self.assertEqual(len(scan(self.root,self.root,date(2026,11,14))['warnings']),1)
 def test_scan_does_not_mutate_reports(self):
  paths=[self.report(3,[['A','001','kg',1,0,'NCC']]),self.report(4,[['A','001','kg',1,100,'NCC']]),self.report(5,[['A','001','kg',1,0,'NCC']])];before=[p.read_bytes() for p in paths];r=scan(self.root,self.root,date(2026,11,14));self.assertIsNone(r['warnings'][0]['increase']);self.assertEqual(before,[p.read_bytes() for p in paths]);self.assertFalse(scan(self.root,self.root,date(2026,12,1))['warnings'])
if __name__=='__main__':unittest.main()
