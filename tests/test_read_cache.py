from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from openpyxl import Workbook
import server,receipt_actions as a
from receipt_workflow import review_token
class ReadCacheTests(unittest.TestCase):
 def test_cached_rows_are_private_and_changed_workbook_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'r.xlsx';b=Workbook();s=b.active;s.title='Receipt';s.append(['Tên hàng trên phiếu (Ảnh)','Thực nhận']);s.append(['A',1]);b.save(p);b.close();version=a.digest(p)
   a._report_rows.cache_clear()
   with patch.object(a,'snapshot',wraps=a.snapshot) as read:
    x=a.get_rows(p,'Receipt',version);x['Receipt'][0][1]['Thực nhận']=99
    self.assertEqual(a.get_rows(p,'Receipt',version)['Receipt'][0][1]['Thực nhận'],1);self.assertEqual(read.call_count,1)
   p.write_bytes(p.read_bytes()+b'changed')
   with self.assertRaises(ValueError):a.get_rows(p,'Receipt',version)
 def test_token_reuses_supplied_images(self):
  images=[]
  with patch('receipt_workflow.source_identity',return_value=[]) as identity:
   review_token(Path('x.xlsx'),'Receipt',[],images)
  self.assertIs(identity.call_args.args[3],images)
if __name__=='__main__':unittest.main()

