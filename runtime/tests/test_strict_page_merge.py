import sys,unittest
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path[:0]=[str(here),str(here/'tests'),'C:/Users/Fenn/Desktop/REC_Software/App','C:/Users/Fenn/Desktop/REC_Software/App/tests']
from delivery_pages import continues_invoice,ambiguous_continuation
import multi_delivery
from test_delivery_pages import document
class StrictTests(unittest.TestCase):
 def pair(self):return dict(document=document(1,20,has_total=False)),dict(document=document(21,30))
 def test_no_number_same_supplier_stt_does_not_merge(self):
  a,b=self.pair();a['document']['reference_id']='';b['document']['reference_id']='';self.assertFalse(continues_invoice(a,b));self.assertTrue(ambiguous_continuation(a,b))
 def test_no_number_consecutive_pages_does_not_merge(self):
  a,b=self.pair();a['document'].update(reference_id='',page_number='1');b['document'].update(reference_id='',page_number='2');self.assertFalse(continues_invoice(a,b))
 def test_one_missing_number_does_not_inherit(self):
  a,b=self.pair();b['document']['reference_id']='';self.assertFalse(continues_invoice(a,b))
 def test_same_number_alone_not_enough(self):
  a,b=self.pair();a['document']['items']=[];b['document']['items']=[];self.assertFalse(continues_invoice(a,b))
 def test_same_number_gap_not_merged(self):
  a,b=self.pair();b['document']['items'][0]['source_stt']='24';self.assertFalse(continues_invoice(a,b))
 def test_page_numbers_do_not_override_stt_reset(self):
  a,b=self.pair();a['document']['page_number']='1';b['document']['page_number']='2';b['document']['items'][0]['source_stt']='1';self.assertFalse(continues_invoice(a,b))
 def test_verified_number_and_sequence_merge(self):
  a,b=self.pair();self.assertTrue(continues_invoice(a,b))
 def test_verified_number_and_pages_without_stt_merge(self):
  a,b=self.pair();a['document'].update(page_number='1',items=[]);b['document'].update(page_number='2',items=[]);self.assertTrue(continues_invoice(a,b))
 def test_engine_keeps_two_suspect_invoices_separate_and_warns(self):
  import tempfile
  from types import SimpleNamespace
  from unittest.mock import patch
  import AutoWatcher as aw
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);paths=[root/'1.jpg',root/'2.jpg']
   for p in paths:p.write_bytes(p.name.encode())
   docs=[document(1,20,has_total=False),document(21,30,has_total=True)]
   for d in docs:d['reference_id']=''
   def extract(path,*args):return dict(path=str(path),document=docs[int(path.stem)-1])
   with patch.object(aw,'wait_ready'),patch.object(aw,'extract_batch_document',side_effect=extract),self.assertLogs(level='WARNING') as logs:
    groups=list(multi_delivery.invoice_groups(paths,root/'report.xlsx',SimpleNamespace(),'',{}))
   self.assertEqual([len(g) for g in groups],[1,1]);self.assertIn('Giữ riêng hai ảnh',' '.join(logs.output))

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(StrictTests)
 for n in ['test_page_grouping_guards','test_delivery_pages','test_pr_auto','test_manual_invoice_links']:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(n))
 r=unittest.TextTestRunner(verbosity=1).run(suite);sys.exit(not r.wasSuccessful())
