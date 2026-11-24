import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import warehouse_directory as wh
RULES=json.loads(Path(wh.__file__).with_name('NhaCungCap.json').read_text(encoding='utf-8'))
DIR={'1103':('Kho bếp Caya','KC'),'1203':('Kho bar Ora','FB'),'1202':('Kho nhà hàng Caya','FB')}

class DirectKitchenTests(unittest.TestCase):
 def test_explicit_ingredients_go_direct_without_requester(self):
  names=['Rau củ tươi','Thịt bò sơ chế','Tôm sú','Bột mì số 11','Gạo thơm','Nước mắm Phú Quốc','Gia vị nấu ăn','Fish sauce']
  with tempfile.TemporaryDirectory() as tmp,patch.object(wh,'request_choices',side_effect=AssertionError('No API')):
   for name in names:
    rows=[dict(line_id=1,invoice_name=name,requester_name='Nguyễn Thị Mỹ Thi',pr_status='KHÔNG CÓ PR')]
    self.assertEqual(wh.classify_records(rows,DIR,'','model',5,tmp,RULES)[0][:3],('1103','Kho bếp Caya','KC'))
 def test_semantic_category_direct_and_alcohol_unchanged(self):
  records=[dict(line_id=1,invoice_name='Cá mú'),dict(line_id=2,invoice_name='Vodka')]
  result=wh.validate_choices({'items':[dict(line_id=1,category='kitchen_ingredients',note='Thực phẩm'),dict(line_id=2,category='bar_alcohol',note='Rượu uống')]},records,DIR,RULES)
  self.assertEqual(result[0][:3],('1103','Kho bếp Caya','KC'));self.assertEqual(result[1][0],'1203')
 def test_tools_not_classified_as_food_from_keywords(self):
  records=[dict(line_id=i,invoice_name=n) for i,n in enumerate(['Máy xay thịt','Hộp đựng gia vị','Dao thái thịt','Đồ chơi hải sản'],1)]
  with tempfile.TemporaryDirectory() as tmp,patch.object(wh,'request_choices',return_value={'items':[dict(line_id=r['line_id'],category='unknown',note='Không phải thực phẩm') for r in records]}):
   self.assertTrue(all(not row[0] for row in wh.classify_records(records,DIR,'','model',5,tmp,RULES)))
 def test_directory_real_values(self):
  directory=wh.load_warehouse_directory(Path('C:/Users/Fenn/Desktop/Auto/DanhMuc.xlsm'))
  self.assertEqual(directory['1103'],('Kho bếp Caya','KC'))
