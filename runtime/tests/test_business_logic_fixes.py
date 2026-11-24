import sys,os,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date
sys.dont_write_bytecode=True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
import receiving_monthly_prices as prices
import receiving_ledger as ledger
from receiving_opening_balance import save,read
from receiving_service import digest
from receiving_pr_number_identity import check_new_order

class BusinessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def report(self,day,price,style='new'):
  folder=self.root/'Thang 11'/f'Ngay {day:02}';folder.mkdir(parents=True)
  name={'new':f'TongHopPhieuNgay_{day:02}-11-2026.xlsx','old':f'TongHop_2026-11-{day:02}.xlsx','fixed':'TongHopNhieuPhieuGiaoHang.xlsx'}[style]
  book=Workbook();sheet=book.active;sheet.title='ONE';sheet.append(['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Thực nhận','Đơn giá','Nhà cung cấp']);sheet.append(['A','001','kg',1,price,'NCC A']);book.save(folder/name);book.close();return folder/name
 def scan(self):return prices.scan(self.root,self.root,date(2026,11,14))
 def test_legacy_and_current_dates(self):
  self.report(3,100,'old');self.report(4,120);self.report(5,110);r=self.scan();self.assertEqual(len(r['warnings']),1);self.assertEqual({e['day'] for e in r['warnings'][0]['entries']},{'2026-11-03','2026-11-04','2026-11-05'})
 def test_fixed_legacy_filename(self):
  self.report(3,100,'fixed');self.report(4,120);self.report(5,110);self.assertEqual(len(self.scan()['warnings']),1)
 def test_bad_link_preserves_prices(self):
  self.report(3,100);self.report(4,120);self.report(5,110)
  with patch('receiving_price_pr.receipt_pr_numbers',side_effect=ValueError('bad link')):r=self.scan()
  self.assertEqual(len(r['warnings']),1);self.assertFalse(r['errors']);self.assertEqual(len(r['pr_errors']),3)
  from receiving_price_pr import pr_label
  self.assertIn('Chưa đọc được PR',pr_label(r['warnings'][0]['entries'][0]))
 def test_bad_library_preserves_prices(self):
  self.report(3,100);self.report(4,120);self.report(5,110)
  with patch('receiving_pr_library.load',side_effect=ValueError('bad index')):r=self.scan()
  self.assertEqual(len(r['warnings']),1);self.assertFalse(r['errors']);self.assertTrue(r['pr_errors'])
 def test_bad_image_manifest_preserves_prices(self):
  self.report(3,100);self.report(4,120);self.report(5,110)
  with patch('receiving_service.day_images',side_effect=ValueError('bad manifest')):r=self.scan()
  self.assertEqual(len(r['warnings']),1);self.assertFalse(r['errors']);self.assertTrue(r['pr_errors'])
 def test_source_bytes_unchanged(self):
  paths=[self.report(3,100,'old'),self.report(4,120)];before=[p.read_bytes() for p in paths];self.scan();self.assertEqual(before,[p.read_bytes() for p in paths])
 def setup_orders(self):
  self.path=self.root/'ledger.sqlite';self.directory=self.root/'pr-library';self.directory.mkdir();self.image=self.root/'pr.png';self.image.write_bytes(b'PR')
  self.lines=[dict(index=0,name='A',unit='kg',ordered='5',price='100',code='001',specification='')]
  self.items=[dict(item_name='A',quantity='5',unit='kg')]
  self.records={key:dict(number='07',date='2026-11-03',supplier='NCC A',department='KC',items=self.items,images={str(self.image):digest(self.image)}) for key in ['old','new']}
  self.write_index()
  ledger.save_receipt(self.path,'old','PR07',self.lines,'r1',dict(allocations={'0':'1'},day='2026-11-05'))
 def write_index(self):(self.directory/'index.json').write_text(json.dumps(dict(version=1,orders=self.records)),encoding='utf-8')
 def test_rephoto_duplicate_blocked_but_distinct_number_allowed(self):
  self.setup_orders()
  with self.assertRaisesRegex(ValueError,'Trùng Số PR'):check_new_order(self.directory,self.path,'new','new',ledger.list_orders(self.path),self.lines)
  self.records['new']['number']='08';self.write_index();check_new_order(self.directory,self.path,'new','new',ledger.list_orders(self.path),self.lines)
 def test_individual_posting_blocks_before_confirmation_or_writes(self):
  self.setup_orders()
  os.environ['QT_QPA_PLATFORM']='offscreen'
  from PySide6.QtWidgets import QApplication
  app=QApplication.instance() or QApplication([])
  from receiving_ledger_ui import LedgerUI
  from types import SimpleNamespace
  image=self.root/'receipt.png';image.write_bytes(b'receipt');report=self.root/'report.xlsx';report.write_bytes(b'report')
  rows=[(2,{'Ảnh nguồn':image.name})]
  w=SimpleNamespace(report=report,source_hash=digest(report),data_by_sheet={'ONE':rows},current_sheet='ONE',images=[image],receipt_references=lambda:[self.image],ledger_path=lambda:self.path,pr_library_directory=lambda:self.directory)
  with patch('rec_department_guard.require_departments'),patch('receiving_pr_image_identity.same_pr_images',return_value=True),patch('receiving_pr.compare',return_value=[{'pr_index':0,'row':2}]),patch('rec_pr_review.eligible',return_value=True),patch('receiving_ledger.order_lines',return_value=self.lines),patch('receiving_ledger.allocations',return_value={'0':'1'}),patch('receiving_pr_library.identity',return_value='new'),patch('receiving_ledger.save_receipt') as save_receipt,patch('receiving_ledger_ui.QMessageBox.warning') as warning:
   LedgerUI.record_ledger(w,self.items,rows,[self.image],{0:2})
   save_receipt.assert_not_called();self.assertIn('Trùng Số PR',str(warning.call_args))
 def test_opening_duplicate_rolls_back(self):
  self.setup_orders();context=dict(index=str(self.directory/'index.json'),identity='new',items_hash=ledger.fingerprint(self.items))
  with self.assertRaisesRegex(ValueError,'Trùng Số PR'):save(self.path,'new','PR07',self.lines,{'0':'2'},'2026-11-03','A','B',[],pr_sources={str(self.image):digest(self.image)},pr_context=context)
  self.assertFalse(read(self.path,'new'));self.assertEqual([x[0] for x in ledger.list_orders(self.path)],['old'])
 def test_existing_pr_opening_allowed(self):
  self.setup_orders();context=dict(index=str(self.directory/'index.json'),identity='old',items_hash=ledger.fingerprint(self.items))
  save(self.path,'old','PR07',self.lines,{'0':'2'},'2026-11-03','A','B',[],pr_sources={str(self.image):digest(self.image)},pr_context=context)
  self.assertEqual(ledger.summary(self.path)[0][0]['received'],'3')
if __name__=='__main__':unittest.main()
