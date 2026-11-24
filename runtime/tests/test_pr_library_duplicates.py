import sys,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
here=Path(__file__).resolve().parent;sys.path[:0]=[str(here),'C:/Users/Fenn/Desktop/REC_Software/App','C:/Users/Fenn/Desktop/REC_Software/App/tests']
from receiving_pr_library_dedup import compact_cards
from receiving_pr_number_identity import scoped_document_key,check_new_order
import receiving_pr_library as lib
class DuplicateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);self.paths=[]
  for i in range(3):
   p=root/f'{i}.png';p.write_bytes(bytes([i])*20);self.paths.append(p)
 def tearDown(self):self.tmp.cleanup()
 def card(self,key,pages,posted=False,**meta):
  record=dict(number='07',date='2026-11-06',supplier='HUYỀN NAM',department='Kitchen',images={},items=[]);record.update(meta)
  return dict(key=key,record=record,count=len(pages)*10,has_ledger=posted,pages=[self.paths[i] for i in pages])
 def compact(self,cards):
  with patch('receiving_pr_library.images_for',side_effect=lambda record:next(c['pages'] for c in cards if c['record'] is record)):return compact_cards(cards)
 def test_proven_page_subsets_hidden_but_data_preserved(self):
  cards=[self.card('full',[0,1],True),self.card('page1',[0]),self.card('page2',[1])];before=copy.deepcopy(cards);out=self.compact(cards);self.assertEqual([c['key'] for c in out],['full']);self.assertEqual(len(out[0]['hidden_page_keys']),2);self.assertEqual(cards[0]['record'],before[0]['record'])
 def test_other_department_or_supplier_not_hidden(self):
  cards=[self.card('full',[0,1],True),self.card('spa',[0],department='Spa'),self.card('other',[0],supplier='NCC B')];self.assertEqual(len(self.compact(cards)),3)
 def test_posted_page_subset_retained(self):self.assertEqual(len(self.compact([self.card('full',[0,1],True),self.card('partial',[0],True)])),2)
 def test_different_photos_remain_visible_with_warning(self):
  out=self.compact([self.card('one',[0]),self.card('two',[2])]);self.assertEqual(len(out),2);self.assertTrue(all('cần đối chiếu' in c['duplicate_note'] for c in out))
 def test_missing_date_not_hidden(self):self.assertEqual(len(self.compact([self.card('full',[0,1],True),self.card('partial',[0],date='')])),2)
 def test_scoped_identity(self):
  a=dict(number='07',date='2026-11-06',supplier='HUYỀN NAM',department='Kitchen');self.assertEqual(scoped_document_key(a),scoped_document_key(dict(a,supplier='Huyền Nam',department='KC')));self.assertNotEqual(scoped_document_key(a),scoped_document_key(dict(a,department='SPA')))
 def test_different_supplier_same_number_date_allowed(self):
  records={'new':dict(number='01',date='2026-11-06',supplier='NCC A',department='KC'),'old':dict(number='01',date='2026-11-06',supplier='NCC B',department='KC')}
  with patch('receiving_pr_library.load',return_value=records),patch('receiving_ledger.resolve_order',side_effect=lambda p,k:k):check_new_order(None,None,'new','new',[('old','old',[])],[])
 def test_partial_stop_keeps_shortage_visible(self):
  r=dict(number='07',date='2026-11-06',supplier='NCC',department='KC',images={},items=[{},{}]);lines=[dict(order_id='id',remaining='1',received='0',ordered='1',reason=''),dict(order_id='id',remaining='0',received='0',ordered='1',reason='Bếp ngừng')]
  with patch('receiving_pr_library.load',return_value={'id':r}):card=lib.cards(Path(self.tmp.name),lines)[0]
  self.assertIn('Còn thiếu 1',card['status']);self.assertIn('Đã ngừng 1',card['status'])
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(DuplicateTests);suite.addTests(unittest.defaultTestLoader.loadTestsFromName('test_pr_library'));r=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not r.wasSuccessful())
