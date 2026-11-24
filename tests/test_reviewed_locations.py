import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from row_locations import reviewed_regions
class ReviewedLocationsTests(unittest.TestCase):
 def test_exact_image_and_row_identity_required(self):
  keys=['demo-page-1','demo-page-2']
  data=[dict(imageKey=key,sourceRow=index,name=f'Hàng mẫu {index}',code=str(index),
    x=.05,y=.2,width=.9,height=.1) for index,key in enumerate(keys,2)]
  rows=[dict(sourceRow=r['sourceRow'],**{'Tên hàng trên phiếu (Ảnh)':r['name'],'Mã vật tư':r['code']}) for r in data]
  with TemporaryDirectory() as folder:
   directory=Path(folder)
   (directory/'reviewed_row_locations.json').write_text(json.dumps({'regions':data}),encoding='utf-8')
   with patch('row_locations.__file__',str(directory/'row_locations.py')):
    self.assertEqual(len(reviewed_regions(rows,keys)),2)
    self.assertFalse(reviewed_regions(rows,['changed-image']))
    self.assertEqual(reviewed_regions(rows,list(reversed(keys)))[0]['page'],1)
    rows[0]['Tên hàng trên phiếu (Ảnh)']='changed'
    self.assertEqual(len(reviewed_regions(rows,keys)),1)
if __name__=='__main__':unittest.main()
