import sys
from pathlib import Path
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
import unittest
from receiving_pr import compare

class MatchTests(unittest.TestCase):
    def test_knorr_same_size_brand_and_product_autofills_without_global_threshold_drop(self):
        pr=self.pr('Bột thịt heo Knorr 1,8kg/bịch',english_name='Knorr pork meat powder 1.8kg/pack')
        value=self.value('Hạt Nêm Heo Knorr 1.8kg','11710105')
        value['Tên chuẩn hệ thống']='Seasoning Knorr Pork Powder Bag 1.8kg/Hat Nem Heo'
        self.assertEqual(compare([pr],[(2,value)])[0]['row'],2)
        other=dict(value,**{'Tên hàng trên phiếu (Ảnh)':'Hạt Nêm Heo Knorr 2kg','Tên chuẩn hệ thống':'Seasoning Knorr Pork Powder Bag 2kg'})
        self.assertIsNone(compare([pr],[(2,other)])[0]['row'])
        self.assertIsNone(compare([pr],[(2,value),(3,value)])[0]['row'])
    def test_pack_count_contradiction_blocks_auto_match(self):
        pr=self.pr('Knorr pork powder 1.8kg x 2 packs')
        value=self.value('Knorr pork powder 1.8kg x 3 packs')
        self.assertIsNone(compare([pr],[(2,value)])[0]['row'])
    def value(self,name,code=''):
        return {'Tên hàng trên phiếu (Ảnh)':name,'Mã vật tư':code,'Đơn vị tính':'kg','Thực nhận':1,'Số lượng':1,'Đơn giá':10}
    def pr(self,name,**kw):return dict(item_name=name,unit='kg',quantity='2',unit_price='10',**kw)
    def test_bilingual_and_extra_pack_size_are_matched_locally(self):
        result=compare([self.pr('Nho khô 1kg',english_name='Raisins 1kg')],[(2,self.value('Raisins/Nho khô'))])
        self.assertEqual(result[0]['row'],2)
        result=compare([self.pr('Tiêu đen hạt')],[(2,self.value('Tiêu Đen Hạt 1KG'))])
        self.assertEqual(result[0]['row'],2)
    def test_conflicting_size_or_mass_volume_is_only_suggestion(self):
        r=compare([self.pr('Muối ớt xanh 260ml')],[(2,self.value('Muối ớt xanh 260g'))])[0]
        self.assertIsNone(r['row']);self.assertEqual(r['suggested_row'],2)
        r=compare([self.pr('Hạt nêm Knorr 1kg')],[(2,self.value('Hạt nêm Knorr 2kg'))])[0]
        self.assertIsNone(r['row'])
    def test_duplicate_rows_and_competing_prs_do_not_auto_assign(self):
        r=compare([self.pr('Nho khô')],[(2,self.value('Nho khô 1kg')),(3,self.value('Nho khô 1kg'))])
        self.assertIsNone(r[0]['row'])
        r=compare([self.pr('Nho khô'),self.pr('Nho khô')],[(2,self.value('Nho khô 1kg'))])
        self.assertIsNone(r[0]['row']);self.assertIsNone(r[1]['row'])
    def test_manual_and_not_delivered_choices_are_preserved(self):
        rows=[(2,self.value('Nho khô')),(3,self.value('Tiêu hạt'))]
        r=compare([self.pr('Nho khô')],rows,{0:None});self.assertIsNone(r[0]['row']);self.assertIn('đã xác định',r[0]['status'])
        r=compare([self.pr('Nho khô')],rows,{0:3});self.assertEqual(r[0]['row'],3)
    def test_same_price_quantity_and_different_codes_are_not_evidence(self):
        r=compare([self.pr('Nếp Bắc',catalog_code='001')],[(2,self.value('Nếp cái hoa vàng','002'))])[0]
        self.assertIsNone(r['row']);self.assertIsNone(r['suggested_row'])

if __name__=='__main__':unittest.main()
