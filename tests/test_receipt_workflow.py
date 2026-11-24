import sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date
from openpyxl import Workbook,load_workbook

stage=Path(__file__).resolve().parents[1]
original=Path(r'C:/Users/Fenn/Desktop/React REC')
sys.path[:0]=[str(stage),str(stage/'runtime'),str(original),str(original/'runtime')]
from local_runtime import activate
activate()
sys.path.insert(0,str(stage/'runtime'))
import receipt_workflow as workflow
from receiving_service import snapshot,digest,atomic_json,sheet_signature

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.store=self.root/'receipts';self.folder=self.store/'Thang 11/Ngay 20';self.folder.mkdir(parents=True)
  self.report=self.folder/'TongHopPhieuNgay_20-11-2026.xlsx';self.profile=self.root/'profile';self.profile.mkdir()
  book=Workbook();sheet=book.active;sheet.title='invoice'
  sheet.append(['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Thực nhận','Đơn giá','Bộ phận','Mã kho','Nhà cung cấp','Ảnh nguồn'])
  sheet.append(['Rau','001','Kg',0,1000,'KC','1103','NCC','a.jpg']);book.save(self.report);book.close()
  self.photo=self.folder/'a.jpg';self.photo.write_bytes(b'photo')
  self.version=snapshot(self.report)[0]
  self.images=patch.object(workflow,'day_images',return_value=[self.photo]);self.images.start()
  self.source=patch.object(workflow,'source_digest',side_effect=digest);self.source.start()
 def tearDown(self):self.source.stop();self.images.stop();self.temp.cleanup()
 def payload(self,**extra):return dict(day='2026-11-20',sheet='invoice',version=self.version,sourceToken=workflow.review_token(self.report,'invoice',snapshot(self.report)[1][0][1]),expectedReviewed=False,reviewed=True,**extra)
 def test_review_persists_and_stale_version_rejected(self):
  workflow.review(self.report,self.payload());self.assertTrue(workflow.reviewed(self.report,snapshot(self.report)[1])['invoice'])
  with self.assertRaises(ValueError):workflow.review(self.report,self.payload())
  p=self.payload();p['version']='old'
  with self.assertRaises(ValueError):workflow.review(self.report,p)
  p=self.payload();p.update(reviewed=False,expectedReviewed=True);workflow.review(self.report,p)
  self.assertFalse(workflow.reviewed(self.report,snapshot(self.report)[1])['invoice'])
  self.assertTrue(list((self.folder/'.receiving/review-backups').glob('*.json')))
 def test_missing_department_or_source_blocks_review(self):
  with patch('rec_department_guard.require_departments',side_effect=ValueError('Chưa chọn bộ phận')):
   with self.assertRaises(ValueError):workflow.review(self.report,self.payload())
  self.photo.unlink()
  with self.assertRaises(OSError):workflow.review(self.report,self.payload())
 def test_replaced_photo_invalidates_review(self):
  workflow.review(self.report,self.payload())
  self.photo.write_bytes(b'replaced image')
  self.assertFalse(workflow.reviewed(self.report,snapshot(self.report)[1])['invoice'])
 def test_source_replaced_before_confirmation_rejected(self):
  payload=self.payload();self.photo.write_bytes(b'replaced before confirm')
  with self.assertRaisesRegex(ValueError,'Ảnh nguồn đã đổi'):workflow.review(self.report,payload)
  self.assertFalse((self.folder/'.receiving/reviewed.json').exists())
 def test_remove_receipt_keeps_originals_and_backup(self):
  from receipt_actions import receipt_action
  from receiving_service import day_images
  from PIL import Image
  Image.new('RGB',(10,10)).save(self.photo)
  other=self.folder/'b.jpg'
  Image.new('RGB',(10,10),'white').save(other)
  book=load_workbook(self.report)
  book['invoice'].cell(2,10,'a.jpg; b.jpg')
  book['invoice'].cell(1,10,'Các ảnh cùng phiếu')
  book.save(self.report);book.close()
  self.version=snapshot(self.report)[0]
  self.images.stop()
  self.images=patch.object(workflow,'day_images',wraps=day_images);self.images.start()
  payload=self.payload(action='remove_receipt')
  with self.assertRaisesRegex(ValueError,'Ảnh nguồn đã thay đổi'):
   receipt_action(self.profile,self.report,dict(payload,sourceToken='old'),store=self.store)
  receipt_action(self.profile,self.report,payload,store=self.store)
  self.assertFalse(any(rows for _,rows in snapshot(self.report)[1]))
  self.assertEqual(day_images(self.folder),[])
  self.assertTrue(self.photo.is_file() and other.is_file())
  backups=list((self.folder/'.autowatcher-backups').glob('remove-receipt-*/'+self.report.name))
  self.assertEqual([digest(path) for path in backups],[self.version])

 def test_remove_receipt_without_linked_images(self):
  from receipt_actions import receipt_action
  payload=dict(day='2026-11-20',sheet='invoice',version=self.version,
               action='remove_receipt',sourceToken=None,withoutImages=True)
  with self.assertRaisesRegex(ValueError,'Ảnh nguồn đã thay đổi'):
   receipt_action(self.profile,self.report,payload,store=self.store)
  self.photo.unlink()
  with self.assertRaisesRegex(ValueError,'Ảnh nguồn đã thay đổi'):
   receipt_action(self.profile,self.report,dict(payload,withoutImages=False),store=self.store)
  receipt_action(self.profile,self.report,payload,store=self.store)
  self.assertFalse(any(rows for _,rows in snapshot(self.report)[1]))
  backups=list((self.folder/'.autowatcher-backups').glob('remove-receipt-*/'+self.report.name))
  self.assertEqual([digest(path) for path in backups],[self.version])

 def test_remove_receipt_blocks_shared_image_and_active_ledger(self):
  import sqlite3
  from receipt_actions import receipt_action
  book=load_workbook(self.report)
  book.copy_worksheet(book['invoice']).title='another'
  book.save(self.report);book.close()
  self.version=snapshot(self.report)[0]
  with self.assertRaisesRegex(ValueError,'dùng chung'):
   receipt_action(self.profile,self.report,self.payload(action='remove_receipt'),store=self.store)
  self.assertEqual(digest(self.report),self.version)
  book=load_workbook(self.report)
  book.remove(book['another']);book.save(self.report);book.close()
  self.version=snapshot(self.report)[0]
  ledger=self.store/'.receiving/receiving-ledger.sqlite'
  ledger.parent.mkdir()
  conn=sqlite3.connect(ledger)
  try:
   conn.execute('CREATE TABLE receipts (payload TEXT, active INTEGER)')
   conn.execute('INSERT INTO receipts VALUES (?, 1)',(json.dumps({'sheet':'invoice','day':'2026-11-20'}),))
   conn.commit()
  finally:conn.close()
  with self.assertRaisesRegex(ValueError,'đã ghi sổ'):
   receipt_action(self.profile,self.report,self.payload(action='remove_receipt'),store=self.store)
  self.assertEqual(digest(self.report),self.version)
 def test_first_official_export_preserves_unowned_invoice(self):
  from receiving_service import close_day
  invoice=self.folder/'Phieu giao hang 20-11-2026.xlsx';invoice.write_bytes(b'manual invoice')
  with self.assertRaises(ValueError):close_day(self.profile,date(2026,11,20),self.store,report_override=self.report,strict_existing=True)
  self.assertEqual(invoice.read_bytes(),b'manual invoice')
 def test_token_includes_reviews_images_and_source(self):
  with patch('receiving_provisional_export.pending',return_value=[('invoice','chưa kiểm')]),patch('receiving_export_pr_notes.collect',return_value=[]):
   first=workflow.preview(self.store,self.report)
   workflow.review(self.report,self.payload());second=workflow.preview(self.store,self.report)
   self.assertNotEqual(first['token'],second['token'])
   self.photo.write_bytes(b'changed');self.assertNotEqual(second['token'],workflow.preview(self.store,self.report)['token'])
 def test_export_requires_consent_and_stable_preview(self):
  state=dict(token='token',version=self.version,blockers=[],provisional=True)
  with patch.object(workflow,'preview',return_value=state),patch('receiving_provisional_export.export') as exporter:
   p=dict(day='2026-11-20',previewToken='token',version=self.version)
   with self.assertRaises(ValueError):workflow.export(self.store,self.profile,self.report,p)
   p['provisionalConsent']=True;p['previewToken']='stale'
   with self.assertRaises(ValueError):workflow.export(self.store,self.profile,self.report,p)
   exporter.assert_not_called()
 def test_download_rejects_escape_and_changed_file(self):
  path=self.root/'outside.xlsx';path.write_bytes(b'file')
  manifest=self.folder/'.receiving/web-export.json'
  atomic_json(manifest,dict(files=[dict(path=str(path),sha256=digest(path))]))
  with self.assertRaises(ValueError):workflow.download(self.store,self.report,0)
  inside=self.folder/'test.xlsx';inside.write_bytes(b'file');atomic_json(manifest,dict(files=[dict(path=str(inside),sha256=digest(inside))]))
  self.assertEqual(workflow.download(self.store,self.report,0),inside)
  inside.write_bytes(b'changed')
  with self.assertRaises(ValueError):workflow.download(self.store,self.report,0)
 def test_real_temporary_export_three_outputs_no_approval_write(self):
  from receiving_export_distribution import destinations
  from receiving_provisional_export import export
  before=digest(self.report)
  def fake_export(source,catalog,catalog_file,rules,output,template):
   b=Workbook();b.active['A1']='Rau';b.active['B1']=0;b.save(output);b.close()
  def images(report,stage):
   p=Path(stage)/'Phiếu giao hàng/a.jpg';p.parent.mkdir();p.write_bytes(b'photo');return ['Phiếu giao hàng/a.jpg']
  def daily(report,output,day):
   b=Workbook();b.active['A1']='Nhật ký';b.save(output);b.close()
  desk=self.root/'exports'
  with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('multi_delivery_export.export_multiple',side_effect=fake_export),patch('receiving_daily_report.stage_images',side_effect=images),patch('receiving_daily_report.build',side_effect=daily),patch('AutoWatcher.delivery_template_path',side_effect=FileNotFoundError):
   output=export(self.profile,date(2026,11,20),self.store,self.report,desktop=desk)
  invoice=output/'Phieu giao hang 20-11-2026 - BẢN TẠM.xlsx';manager,archive=destinations(date(2026,11,20),desk,True)
  self.assertTrue(all(p.is_file() for p in [invoice,manager,archive]));self.assertEqual(before,digest(self.report))
  self.assertFalse((self.folder/'.receiving/reviewed.json').exists())
  b=load_workbook(invoice);self.assertEqual(b.active['B1'].value,0);self.assertIn('BẢN TẠM',b.active.oddHeader.center.text);b.close()
  import zipfile
  with zipfile.ZipFile(archive) as z:self.assertIn('Phiếu giao hàng/a.jpg',z.namelist());self.assertIsNone(z.testzip())
 def test_export_revalidates_after_staging_before_publication(self):
  from receiving_provisional_export import export
  def fake_export(source,catalog,catalog_file,rules,output,template):
   b=Workbook();b.save(output);b.close()
  def validate():
   validate.calls+=1
   if validate.calls==2:raise ValueError('Nguồn vừa đổi')
  validate.calls=0
  with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('multi_delivery_export.export_multiple',side_effect=fake_export),patch('receiving_daily_report.stage_images',return_value=[]),patch('AutoWatcher.delivery_template_path',side_effect=FileNotFoundError):
   with self.assertRaisesRegex(ValueError,'Nguồn vừa đổi'):export(self.profile,date(2026,11,20),self.store,self.report,desktop=self.root/'exports',validate=validate)
  self.assertFalse((self.folder/'Phieu giao hang 20-11-2026 - BẢN TẠM.xlsx').exists())

if __name__=='__main__':unittest.main()
