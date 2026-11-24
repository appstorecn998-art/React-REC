import sys,unittest,tempfile,json
from pathlib import Path
from datetime import date
from unittest.mock import patch
here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app),str(app/'tests')]
from receiving_daily_report import journal_item
from receiving_export_distribution import distribute,destinations
import receiving_service as rs
class ExportFixTests(unittest.TestCase):
 def test_unknown_code_name_same_delivery(self):
  self.assertEqual(journal_item({'Mã vật tư':'CHUA CO MA','Tên chuẩn hệ thống':'Không xác định được mã phù hợp','Tên hàng trên phiếu (Ảnh)':'Bánh da lợn ổ'}),('','Banh da lon o'))
  self.assertEqual(journal_item({'Tên tiếng Anh trên phiếu':'Cake','Tên tiếng Việt trên phiếu':'Bánh ổ'}),('','Cake/Banh o'))
  self.assertEqual(journal_item({'Mã vật tư':'001','Tên chuẩn hệ thống':'Cá'}),('001','Ca'))
 def fixture(self,root):
  day=date(2026,11,13);report=root/f'TongHopPhieuNgay_{day:%d-%m-%Y}.xlsx';report.write_bytes(b'source')
  invoice=root/'Phieu giao hang 13-11-2026.xlsx';invoice.write_bytes(b'invoice')
  photo=root/'Phiếu giao hàng/a.jpg';photo.parent.mkdir();photo.write_bytes(b'photo')
  rs.atomic_json(root/'.receiving/published.json',{str(root.resolve()):{'image_files':['Phiếu giao hàng/a.jpg'],'files':{'Phiếu giao hàng/a.jpg':rs.digest(photo)}}})
  return day,report
 def test_preserve_entire_manager_and_refresh_zip(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);day,report=self.fixture(root);desk=root/'desktop';manager,archive=destinations(day,desk);manager.parent.mkdir(parents=True);manager.write_bytes(b'user edits all sheets')
   with patch('receiving_daily_report.build') as build:
    distribute(root,day,desk);self.assertFalse(build.called)
    report.write_bytes(b'updated source');distribute(root,day,desk)
   self.assertEqual(manager.read_bytes(),b'user edits all sheets');self.assertTrue(archive.exists())
 def test_new_manager_built_only_at_manager_destination(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);day,_=self.fixture(root)
   def build(report,out,day):Path(out).write_bytes(b'new workbook')
   with patch('receiving_daily_report.build',side_effect=build):distribute(root,day,root/'desktop')
   self.assertFalse(list(root.glob('Cong viec*.xlsx')))
   self.assertEqual(destinations(day,root/'desktop')[0].read_bytes(),b'new workbook')
from test_receiving_service import ReceivingTests
class DayFolderTests(ReceivingTests):
 def test_legacy_daily_is_preserved_outside_day_listing(self):
  report=self.report();dest=self.base/'accounting';target=dest/'Thang 11'/'Ngay 06';target.mkdir(parents=True)
  old=target/'Cong viec hang ngay 6-11-2026.xlsx';old.write_bytes(b'manual edits')
  with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('multi_delivery_export.export_multiple',side_effect=self.fake_export):
   rs.close_day(self.base,self.day,dest,self.base/'template')
  self.assertFalse(old.exists());self.assertEqual(next((target/'.receiving/legacy-daily').rglob('*.xlsx')).read_bytes(),b'manual edits')
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(ExportFixTests)
 suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(DayFolderTests))
 result=unittest.TextTestRunner().run(suite);sys.exit(not result.wasSuccessful())
