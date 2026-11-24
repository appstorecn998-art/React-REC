import os,sys,tempfile,unittest,json,sqlite3
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen';stage=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(stage),str(app),str(app/'tests')]
import receiving_ledger as ledger
from receiving_opening_balance import save,read
from receiving_cumulative import context
from receiving_evidence import attach,validate
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtGui import QImage,QColor
from rec_approval_evidence import EvidencePanel
APP=QApplication.instance() or QApplication([])
class OpeningTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=self.root/'ledger.sqlite';self.source=self.root/'pr.png';self.source.write_bytes(b'original PR');self.sources={str(self.source):__import__('hashlib').sha256(self.source.read_bytes()).hexdigest()};self.lines=[dict(index=0,name='A',unit='kg',ordered='5',price='100',code='001',specification='')]
 def tearDown(self):self.tmp.cleanup()
 def opening(self,quantity='3',revision=0,attachments=None):return save(self.path,'PR1','PR1',self.lines,{'0':quantity},'2026-11-03','Kitchen A','Xác nhận sổ cũ',attachments or [],revision,pr_sources=self.sources)
 def receipt(self,rid='r1',quantity='2',day='2026-11-05'):
  payload=dict(allocations={'0':quantity},day=day,sheet=rid,signature='v1');return ledger.save_receipt(self.path,'PR1','PR1',self.lines,rid,payload,acknowledged=ledger.receipt_warnings(self.path,'PR1',self.lines,rid,payload))
 def test_sum_idempotent_update_and_separate_history(self):
  self.assertEqual(self.opening(),1);self.receipt();rows,history=ledger.summary(self.path);self.assertEqual(rows[0]['received'],'5');self.assertEqual(rows[0]['remaining'],'0');self.assertEqual(rows[0]['opening_received'],'3');self.assertEqual(len(history),1)
  self.opening('3',1);self.assertEqual(ledger.summary(self.path)[0][0]['received'],'5')
  with self.assertRaises(ValueError):self.opening('1',1)
  totals,uncertain,count=context(self.path,'PR1','r1',lambda p:True);self.assertEqual(str(totals[0]),'3');self.assertFalse(uncertain)
  self.opening('0',2);self.assertEqual(ledger.summary(self.path)[0][0]['received'],'2')
 def test_duplicate_old_documents_guard_both_directions(self):
  self.opening()
  with self.assertRaisesRegex(ValueError,'trùng'):self.receipt(day='2026-11-02')
  self.assertEqual(len(ledger.summary(self.path)[1]),0)
  self.opening('0',1);self.receipt(day='2026-11-02')
  with self.assertRaisesRegex(ValueError,'trùng'):self.opening('3',2)
 def test_overreceipt_warning_and_close_items_count_opening(self):
  self.opening('5');warnings=ledger.receipt_warnings(self.path,'PR1',self.lines,'r1',dict(allocations={'0':'1'},day='2026-11-05'));self.assertTrue(warnings)
  from receiving_item_closure import set_items
  with self.assertRaisesRegex(ValueError,'đã nhận đủ'):set_items(self.path,'PR1',[0],'Kitchen xác nhận')
 def test_evidence_immutable_and_tamper_marks_opening_unknown(self):
  w=QMainWindow();w.root=self.root;w.ledger_path=lambda:self.path;p=EvidencePanel(w);image=QImage(30,40,QImage.Format_RGB32);image.fill(QColor('red'));self.assertTrue(p.add_image(image,'chat.png'));refs=p.persist();self.assertTrue(validate(refs));self.opening(attachments=refs)
  rule=attach({'reason':'a'},refs);updated=attach({'reason':'b'},[],rule);self.assertEqual(len(updated['attachment_history']),2);self.assertEqual(updated['attachment_history'][0]['attachments'],refs)
  Path(refs[0]['path']).write_bytes(b'changed');self.assertIsNone(ledger.summary(self.path)[0][0]['remaining']);totals,uncertain,count=context(self.path,'PR1','none',lambda p:True);self.assertIn(0,uncertain)
  with self.assertRaises(ValueError):p.persist()
  p.close();w.close()
 def test_confirmed_receipt_date_is_quantity_critical(self):
  import receiving_validation
  self.assertIn('Ngày nhận hàng xác nhận',receiving_validation.CRITICAL)
 def test_actual_confirmed_old_date_blocks_late_import(self):
  self.opening('2');payload=dict(allocations={'0':'1'},day='2026-11-14',sheet='late',source_rows=[(2,{'Ngày nhận hàng xác nhận':'2026-11-02'})],allocation_rows={'0':2})
  with self.assertRaisesRegex(ValueError,'trùng'):ledger.save_receipt(self.path,'PR1','PR1',self.lines,'late',payload)
 def test_pr_image_change_marks_positive_opening_unverified(self):
  self.opening('3');self.source.write_bytes(b'changed PR source');self.assertIsNone(ledger.summary(self.path)[0][0]['remaining']);totals,uncertain,count=context(self.path,'PR1','none',lambda p:True);self.assertIn(0,uncertain)
 def test_attachment_history_persists_after_multiple_empty_reapprovals(self):
  ref=dict(path='/test.png',sha256='sha');one=attach({'reason':'one'},[ref]);two=attach({'reason':'two'},[],one);three=attach({'reason':'three'},[],two);self.assertEqual(len(three['attachment_history']),2);self.assertEqual(three['attachment_history'][0]['attachments'],[ref])
 def test_invalid_values_and_stale_receipt_snapshot(self):
  for q in ['-1','NaN','inf','abc']:
   with self.assertRaises(ValueError):self.opening(q)
  empty=ledger.fingerprint([]);self.opening('2');self.receipt(quantity='1')
  with self.assertRaisesRegex(ValueError,'phiếu đã ghi thay đổi'):save(self.path,'PR1','PR1',self.lines,{'0':'1'},'2026-11-03','A','B',[],1,empty,self.sources)
if __name__=='__main__':unittest.main()
