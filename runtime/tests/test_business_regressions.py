import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';here=Path(__file__).resolve().parent;sys.path[:0]=[str(here),'C:/Users/Fenn/Desktop/REC_Software/App','C:/Users/Fenn/Desktop/REC_Software/App/tests']
from receiving_sheets import plan,HEADERS,fingerprint
from receiving_pr_number_identity import check_batch_document
class AuditTests(unittest.TestCase):
 def row(self,oid='good'):return dict(order_id=oid,index=0,title='PR1',name='Hàng',unit='kg',ordered='2',received='1',remaining='1',reason='')
 def record(self,oid='good',day='12/11/2026'):return dict(active=True,valid=True,order_id=oid,day='2026-11-10',source_rows=[[2,{'Ngày nhận hàng xác nhận':day}]],allocation_rows={'0':2},sheet='A')
 def test_unrelated_missing_date_does_not_block(self):
  p=plan("'KC'",[[],[],[],HEADERS],[self.row()],[self.record(),self.record('other','')],{'good':'NCC'});self.assertEqual(len(p['changes']),1);self.assertEqual(p['changes'][0]['values'][1],'12/11/2026')
 def test_missing_date_preserves_existing_numbers_and_notes(self):
  old=[1,'10/11/2026','NCC','PR1','Hàng','Kg',2,1,1,'Còn thiếu','Hẹn ngày mai','REC-'+fingerprint(['good',0])[:32]]
  p=plan("'KC'",[[],[],[],HEADERS+['REC_ID'],old],[self.row()],[self.record(day='')],{'good':'NCC'});self.assertEqual(p['skipped'],1);new=p['changes'][0]['values'];self.assertEqual([i for i in range(12) if new[i]!=old[i]],[9]);self.assertIn('Thiếu/sai',new[9])
 def test_same_pr_two_images_one_batch_blocked(self):
  with patch('receiving_pr_library.load',return_value={'image2':dict(number='07',date='2026-11-06')}):
   with self.assertRaisesRegex(ValueError,'Hai bộ ảnh'):check_batch_document(None,'image2','other-id',{('07','2026-11-06'):'first-id'})
 def test_same_pr_same_identity_receiving_multiple_allowed(self):
  with patch('receiving_pr_library.load',return_value={'image':dict(number='07',date='2026-11-06')}):self.assertEqual(check_batch_document(None,'image','id',{('07','2026-11-06'):'id'}),('07','2026-11-06'))
 def test_new_date_is_separate_pr(self):
  with patch('receiving_pr_library.load',return_value={'image':dict(number='07',date='2026-11-12')}):self.assertEqual(check_batch_document(None,'image','id2',{('07','2026-11-06'):'id'}),('07','2026-11-12'))
 def test_partial_sync_does_not_clear_pending_outbox(self):
  from PySide6.QtWidgets import QApplication
  from receiving_qt import ReceivingWindow
  import rec_auto_sheets
  app=QApplication.instance() or QApplication([])
  with tempfile.TemporaryDirectory() as td:
   jobs=[]
   with patch.object(ReceivingWindow,'_start_worker',lambda self,job:jobs.append(job)):
    w=ReceivingWindow(root=Path(td),auto_load=False);w.destination=Path(td)
    with patch('receiving_ledger.pending_sync',return_value=['pending']),patch('receiving_ledger.sync_result') as record:
     rec_auto_sheets.start(w);jobs[-1].signals.result.emit({'changed':2,'skipped':1})
     self.assertTrue(record.call_args.args[2]);self.assertIn('chưa xác nhận',w.sheets_last_status)
    w.close()
if __name__=='__main__':unittest.main()
