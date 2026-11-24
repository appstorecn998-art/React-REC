import sys,json,types,tempfile,unittest,copy
from pathlib import Path
from decimal import Decimal
here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app)]
from PIL import Image
import rec_pr_review as review
import receiving_pr_library as library
import receiving_ledger as ledger
from receiving_service import sheet_signature,digest
from receiving_image_archive import archive_image,source_digest,image_name
from receiving_document_identity import receipt_identity,page_ids

class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.original=self.root/'pr.jpg';Image.new('RGB',(400,400),'white').save(self.original)
  self.archive,_=archive_image(self.original,self.root/'archive')
  self.receipt=self.root/'receipt.jpg';Image.new('RGB',(400,400),'blue').save(self.receipt)
  self.receipt_archive,_=archive_image(self.receipt,self.root/'receipt-archive')
  self.items=[dict(item_name='Cam',quantity='10',unit='kg',unit_price='100',pr_reference_id='PR1')]
  self.key=library.register(self.root/'library',[self.archive],self.items)
  self.prs=library.images_for(library.load(self.root/'library')[self.key])
  self.rows=[(2,{'Tên hàng trên phiếu (Ảnh)':'Cam','Nhà cung cấp':'NCC','Mã vật tư':'001','Đơn vị tính':'kg','Số lượng':10,'Thực nhận':10,'Đơn giá':100,'Thành tiền':1000,'Ảnh nguồn':'receipt.jpg'})]
  self.w=types.SimpleNamespace(current_sheet='A',data_by_sheet={'A':self.rows},images=[self.receipt_archive],receipt_references=lambda:self.prs,pr_library_directory=lambda:self.root/'library',ledger_path=lambda:self.root/'ledger.sqlite')
  self.path=self.root/'comparison.json'
  self.saved=dict(version=1,signature=sheet_signature('A',self.rows),images={image_name(p):source_digest(p) for p in self.prs},pr_items=self.items,links={'0':2},conversions={},results=[dict(pr_index=0,row=2,alerts=[],status='Đủ',ordered='10',received='10')])
  self.write();review.confirm(self.w,self.path,self.saved['results'],review.sources(self.w))
 def write(self):self.path.write_text(json.dumps(self.saved,ensure_ascii=False,default=str),encoding='utf-8')
 def test_reopen_read_is_stable_and_does_not_write(self):
  before=review.marker_path(self.path).read_bytes()
  for _ in range(5):self.assertEqual(review.state(self.w,self.path),'done')
  self.assertEqual(before,review.marker_path(self.path).read_bytes())
 def test_display_and_recomputed_totals_do_not_reset_review(self):
  self.saved['results'][0].update(status='Changed renderer',remaining='0',previous_received='100',alerts=['previous_receipt_invalid'])
  self.write();self.assertEqual(review.state(self.w,self.path),'done')
 def test_notes_ai_status_and_file_location_do_not_reset_review(self):
  self.rows[0][1].update({'Trạng thái':'Đã xử lý','Độ khớp AI đề xuất':99,'Ghi chú':'Ghi chú mới','Đối chiếu PR':'cached result'})
  self.w.images=[self.receipt];self.prs=[self.original]
  self.assertEqual(review.state(self.w,self.path),'done')
 def test_receipt_change_has_specific_reason(self):
  self.rows[0][1]['Thực nhận']=9
  self.assertIn('Nội dung phiếu',review.inspection(self.w,self.path)['reason'])
 def test_price_change_has_specific_reason(self):
  self.rows[0][1]['Đơn giá']=101;self.assertEqual(review.state(self.w,self.path),'stale')
 def test_pr_and_links_and_approval_changes_invalidate(self):
  for field in ['pr_items','links','conversions']:
   with self.subTest(field=field):
    old=copy.deepcopy(self.saved)
    if field=='pr_items':self.saved[field][0]['quantity']='11'
    elif field=='links':self.saved[field]['0']=3
    else:self.saved[field]['0']={'factor':'2','reason':'new approval'}
    self.write();self.assertEqual(review.state(self.w,self.path),'stale')
    self.saved=old
  self.write()
 def test_library_metadata_and_other_receipts_do_not_reset(self):
  before=review.sources(self.w)
  library.update_metadata(self.root/'library',self.key,department='KC',supplier='Tên hiển thị')
  self.w.ledger_path().write_text('unrelated ledger write')
  self.assertEqual(before,review.sources(self.w));self.assertEqual(review.state(self.w,self.path),'done')
 def test_image_change_and_tamper_rejected(self):
  Image.new('RGB',(400,400),'black').save(self.original)
  self.prs=[self.original];self.assertIn('Bộ ảnh PR',review.inspection(self.w,self.path)['reason'])
 def test_tampered_library_copy_rejected(self):
  self.prs[0].write_bytes(b'tamper');self.assertEqual(review.state(self.w,self.path),'stale')
 def test_dirty_has_specific_reason(self):
  self.assertIn('chưa lưu',review.inspection(self.w,self.path,True)['reason'])
 def test_original_archive_library_share_key(self):
  self.assertNotEqual(digest(self.original),digest(self.archive))
  self.assertEqual(library.identity([self.original],self.root/'library'),self.key)
  self.assertEqual(library.identity([self.archive],self.root/'library'),self.key)
  self.assertEqual(library.identity(self.prs),self.key)
  self.assertEqual(library.register(self.root/'library',[self.original],self.items),self.key)
  self.assertEqual(len(library.load(self.root/'library')),1)
 def test_receipt_id_reuses_old_raw_id_without_duplicate(self):
  lines=ledger.order_lines(self.items);rid=ledger.fingerprint([digest(self.receipt_archive)])
  ledger.save_receipt(self.w.ledger_path(),'order','Order',lines,rid,dict(allocations={'0':'10'},source_images={str(self.receipt_archive):digest(self.receipt_archive)}))
  self.assertEqual(receipt_identity([self.receipt],self.w.ledger_path()),rid)
  self.assertEqual(receipt_identity([self.receipt_archive],self.w.ledger_path()),rid)
 def test_renamed_file_retains_library_and_receipt_id(self):
  renamed=self.root/'renamed.jpg';renamed.write_bytes(self.original.read_bytes())
  self.assertEqual(library.identity([renamed],self.root/'library'),self.key)
  lines=ledger.order_lines(self.items);rid=ledger.fingerprint([digest(self.receipt_archive)])
  ledger.save_receipt(self.w.ledger_path(),'order','Order',lines,rid,dict(allocations={'0':'10'},source_images={str(self.receipt_archive):digest(self.receipt_archive)}))
  renamed_receipt=self.root/'renamed-receipt.jpg';renamed_receipt.write_bytes(self.receipt.read_bytes())
  self.assertEqual(receipt_identity([renamed_receipt],self.w.ledger_path()),rid)
 def test_duplicate_active_receipts_block_until_audited_revoke(self):
  lines=ledger.order_lines(self.items);path=self.w.ledger_path()
  payload=lambda p:dict(allocations={'0':'10'},source_images={str(p):digest(p)},sheet='A',day='2026-11-12',signature='v1')
  ledger.save_receipt(path,'order','Order',lines,'old',payload(self.receipt))
  warning=ledger.receipt_warnings(path,'order',lines,'new',payload(self.receipt_archive))
  ledger.save_receipt(path,'order','Order',lines,'new',payload(self.receipt_archive),acknowledged=warning)
  with self.assertRaises(ValueError):receipt_identity([self.receipt_archive],path)
  ledger.revoke_receipt(path,'old',1,'Test: exact original/archive duplicate')
  self.assertEqual(receipt_identity([self.receipt_archive],path),'new')
  self.assertEqual(receipt_identity([self.receipt],path),'new')
  self.assertEqual(ledger.summary(path)[0][0]['received'],'10')
 def test_renamed_pr_keeps_saved_links_and_open_guard(self):
  from receiving_pr_image_identity import pr_images_match,same_pr_images
  renamed=self.root/'renamed.jpg';renamed.write_bytes(self.original.read_bytes())
  self.assertTrue(pr_images_match(self.saved['images'],[renamed]))
  self.assertTrue(same_pr_images(self.prs,[renamed]))
  wrong=self.root/'wrong.jpg';Image.new('RGB',(400,400),'red').save(wrong)
  self.assertFalse(pr_images_match(self.saved['images'],[wrong]))
  self.assertFalse(same_pr_images(self.prs,[wrong]))
 def test_duplicate_pages_rejected(self):
  with self.assertRaises(ValueError):page_ids([self.original,self.archive])
 def test_v1_migrates_only_exact_proof(self):
  mark={'version':1,'comparison':review.token(self.saved),'scope':'receipt','reviewed_at':'2026-11-01'}
  review.marker_path(self.path).write_text(json.dumps(mark))
  self.assertTrue(review.migrate(self.w,self.path));self.assertEqual(review.state(self.w,self.path),'done')
  migrated=json.loads(review.marker_path(self.path).read_text());self.assertEqual(migrated['version'],4);self.assertEqual(migrated['reviewed_at'],'2026-11-01')
  review.marker_path(self.path).write_text(json.dumps(dict(mark,comparison='wrong')))
  self.assertFalse(review.migrate(self.w,self.path));self.assertEqual(review.state(self.w,self.path),'stale')
 def test_legacy_snapshot_uses_frozen_old_wording(self):
  from receiving_pr import compare
  from receiving_cumulative import apply
  old=copy.deepcopy(self.saved);old['results']=apply(compare(self.items,self.rows,{0:2},{}),{},set([0]),0)
  for row in old['results']:row['status']=row['status'].replace('Nguồn lần nhận khác đã đổi; cần cập nhật phiếu. ','Lịch sử chưa xác minh; chưa kết luận thiếu/dư. ')
  old=json.loads(json.dumps(old,default=str));mark=dict(version=1,comparison=review.token(old),scope='receipt')
  self.saved['results']=compare(self.items,self.rows,{0:2},{});self.write();review.marker_path(self.path).write_text(json.dumps(mark))
  self.assertTrue(review.migrate(self.w,self.path));self.assertEqual(review.state(self.w,self.path),'done')
 def test_new_unresolved_alerts_cannot_be_confirmed(self):
  bad=copy.deepcopy(self.saved['results']);bad[0]['alerts']=['price']
  with self.assertRaises(ValueError):review.confirm(self.w,self.path,bad,review.sources(self.w))

if __name__=='__main__':unittest.main(verbosity=2)
