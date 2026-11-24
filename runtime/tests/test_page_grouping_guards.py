import sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
here=Path(__file__).resolve().parent;sys.path[:0]=[str(here),'C:/Users/Fenn/Desktop/REC_Software/App','C:/Users/Fenn/Desktop/REC_Software/App/tests']
from delivery_pages import continues_invoice
from receiving_pr_auto import register_pages
from test_delivery_pages import document
class GroupingTests(unittest.TestCase):
 def pair(self,**right):return dict(document=document(1,20,has_total=False)),dict(document=document(21,30,**right))
 def test_pr_never_merged_into_delivery(self):
  a,b=self.pair();b['document']['document_type']='pr';self.assertFalse(continues_invoice(a,b))
 def test_missing_buyer_not_a_merge_reason(self):
  a,b=self.pair();a['document'].update(reference_id='',supplier_name='');b['document'].update(reference_id='',supplier_name='');self.assertFalse(continues_invoice(a,b))
 def test_exact_stt_and_supplier_without_number(self):
  a,b=self.pair();a['document']['reference_id']='';b['document']['reference_id']='';self.assertFalse(continues_invoice(a,b));b['document']['items'][0]['source_stt']='24';self.assertFalse(continues_invoice(a,b))
 def test_final_total_prevents_merge_even_with_page_numbers(self):
  a,b=self.pair(page_number='2');a['document'].update(has_total=True,page_number='1');self.assertFalse(continues_invoice(a,b))
 def test_page_gap_and_different_pr_reference_stop(self):
  a,b=self.pair(page_number='3');a['document']['page_number']='1';self.assertFalse(continues_invoice(a,b));a['document'].update(page_number='',pr_reference_id='1');b['document'].update(page_number='',pr_reference_id='2');self.assertFalse(continues_invoice(a,b))
 def test_pr_missing_page_numbers_groups_exact_sequence(self):
  pages=[]
  for first,last in [(1,20),(21,30)]:
   d=document(first,last);d.update(document_type='pr',document_date='2026-11-12',department_name='KC',page_number='',has_total=first==21);pages.append((Path(str(first)+'.jpg'),d))
  with patch('receiving_pr_auto.library.register',return_value='full') as save:
   self.assertEqual(register_pages('unused',pages),['full']);self.assertEqual(len(save.call_args.args[1]),2);self.assertEqual(len(save.call_args.args[2]),30)
 def test_pr_two_first_pages_remain_separate(self):
  d=document(1,3);d.update(document_type='pr',document_date='2026-11-12',department_name='KC',page_number='1')
  with patch('receiving_pr_auto.library.register',return_value='single') as save:register_pages('unused',[(Path('a.jpg'),d),(Path('b.jpg'),d)]);self.assertEqual(save.call_count,2)
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(GroupingTests)
 for n in ['test_delivery_pages','test_pr_auto','test_manual_invoice_links']:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(n))
 r=unittest.TextTestRunner(verbosity=1).run(suite);sys.exit(not r.wasSuccessful())
