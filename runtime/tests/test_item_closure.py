import sys,tempfile,unittest,sqlite3
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path[:0]=[str(here),'C:/Users/Fenn/Desktop/REC_Software/App']
import receiving_ledger as l
from receiving_item_closure import set_items,line_key
class Tests(unittest.TestCase):
 def test_stop_reopen_and_other_lines_unchanged(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'ledger.sqlite';lines=[dict(index=i,name='Item '+str(i),ordered='10',unit='kg',price='1',code='',specification='') for i in range(3)]
   l.save_receipt(p,'PR','PR',lines,'r',dict(allocations={'0':'7','1':'8','2':'9'},day='2026-11-13',sheet='A'))
   set_items(p,'PR',[0,1],'Bếp báo ngừng',expected={str(i):line_key(lines[i]) for i in [0,1]})
   rows,h=l.summary(p);self.assertEqual([r['remaining'] for r in rows],['0','0','1']);self.assertEqual(rows[0]['received'],'7');self.assertEqual(rows[0]['physical_remaining'],'3');self.assertTrue(rows[0]['item_stopped'])
   invalid,_=l.summary(p,lambda _:False);self.assertIsNone(invalid[0]['remaining'])
   from receiving_sheets import plan,HEADERS,fingerprint
   remote=[[],[],[],HEADERS+['REC_ID'],[1,'13/11/2026','NCC','PR','Item 0','Kg',10,7,3,'Còn thiếu','Giữ ghi chú','REC-'+fingerprint(['PR',0])[:32]]]
   changes=plan('Kitchen',remote,rows,[dict(order_id='PR',active=True,valid=True,day='2026-11-13')],{'PR':'NCC'})['changes']
   self.assertTrue(any(c.get('delete') and c['name']=='Item 0' for c in changes))
   set_items(p,'PR',[0],'Bếp yêu cầu giao tiếp',True);rows,_=l.summary(p);self.assertEqual(rows[0]['remaining'],'3');self.assertFalse(rows[0]['item_stopped']);self.assertTrue(rows[1]['item_stopped'])
   with self.assertRaises(ValueError):set_items(p,'PR',[2],'')
   with self.assertRaises(ValueError):set_items(p,'PR',[2],'old',expected={'2':'bad'})
   with l.database(p) as conn:self.assertEqual(conn.execute("SELECT count(*) FROM audit WHERE receipt_id LIKE 'item:%'").fetchone()[0],3)
if __name__=='__main__':unittest.main(verbosity=2)
