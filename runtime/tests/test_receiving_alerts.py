import sys
from pathlib import Path
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
import unittest
from receiving_pr import compare
from receiving_alerts import presentation

class AlertTests(unittest.TestCase):
    def test_confirmed_box_conversion_does_not_conflict_with_pack_weight(self):
        from receiving_units import conversion
        pr={'item_name':'Gia vị bò kho hộp 20 gói','unit':'Hộp','quantity':'1','unit_price':'350000'}
        value={'Tên hàng trên phiếu (Ảnh)':'Complete seasoning bò kho 25g','Đơn vị tính':'Gói','Số lượng':20,'Thực nhận':20,'Đơn giá':17500}
        rules={0:conversion(2,pr,value,'1/20','NCC giao 1 hộp 20 gói')}
        r=compare([pr],[(2,value)],{0:2},rules)[0]
        self.assertEqual(r['alerts'],[])
        self.assertNotIn('Quy cách/dung lượng khác',r['status'])
        changed=dict(pr,item_name='Gia vị bò kho 260ml hộp 20 gói')
        rules={0:conversion(2,changed,value,'1/20','Đã kiểm đơn vị')}
        r=compare([changed],[(2,value)],{0:2},rules)[0]
        self.assertIn('specification',r['alerts'])
        value2=dict(value,**{'Tên hàng trên phiếu (Ảnh)':'Gia vị bò kho hộp 24 gói'})
        rules={0:conversion(2,pr,value2,'1/20','Đã kiểm đơn vị')}
        self.assertIn('specification',compare([pr],[(2,value2)],{0:2},rules)[0]['alerts'])
    def test_confirmation_removes_generic_reminders_but_preserves_real_alerts(self):
        from receiving_units import conversion
        pr=dict(self.item(),specification='Đóng gói theo PR')
        value=self.row(unit='Bag')
        c={0:conversion(2,pr,value,'1','NCC xác nhận 1 bag = 1 kg')}
        for qty,price,expected in [(10,100,set()),(0,100,{'short'}),(12,120,{'over','price'}),(None,None,{'unknown_quantity','unknown_price'})]:
            v=dict(value,**{'Thực nhận':qty,'Đơn giá':price})
            r=compare([pr],[(2,v)],{0:2},c)[0]
            self.assertEqual(set(r['alerts']),expected)
            self.assertNotIn('cần rà loại/quy cách',r['status'])
            self.assertNotIn('Cần rà quy cách PR trên ảnh',r['status'])
            self.assertIn('Quy đổi đã xác nhận',r['status'])
            if not expected:self.assertIn('Khớp lượng và giá',r['status'])
        v=dict(value,**{'Mã vật tư':'002'})
        r=compare([dict(pr,catalog_code='001')],[(2,v)],{0:2})[0]
        self.assertIn('code',r['alerts'])
        self.assertIn('unit',r['alerts'])
    def test_unlinked_row_has_visible_marker(self):
        r=compare([self.item()],[])[0]
        self.assertIn('CHƯA GÁN DÒNG',presentation(r)['label'])

    def item(self):return {'item_name':'Hàng mẫu','unit':'kg','quantity':'10','unit_price':'100'}
    def row(self,qty=10,price=100,unit='kg'):
        return {'Tên hàng trên phiếu (Ảnh)':'Hàng mẫu','Đơn vị tính':unit,'Số lượng':10,'Thực nhận':qty,'Đơn giá':price}
    def test_price_both_directions_and_short_over_have_distinct_markers(self):
        r=compare([self.item()],[(2,self.row(7,120))],{0:2})[0]
        self.assertEqual(set(r['alerts']),{'price','short'})
        p=presentation(r);self.assertIn('LỆCH GIÁ',p['label']);self.assertIn('THIẾU 3',p['label']);self.assertIn(7,p['cells']);self.assertIn(8,p['cells'])
        r=compare([self.item()],[(2,self.row(12,90))],{0:2})[0]
        self.assertEqual(set(r['alerts']),{'price','over'});self.assertIn('DƯ 2',presentation(r)['label'])
    def test_unconverted_units_and_unknown_numbers_are_not_false_shortages(self):
        r=compare([self.item()],[(2,self.row(1,1000,'thùng'))],{0:2})[0]
        self.assertIn('unit',r['alerts']);self.assertNotIn('short',r['alerts']);self.assertNotIn('price',r['alerts'])
        self.assertIn('CHƯA QUY ĐỔI',presentation(r)['label'])
        r=compare([self.item()],[(2,self.row(None,None))],{0:2})[0]
        self.assertNotIn('short',r['alerts']);self.assertNotIn('price',r['alerts'])
    def test_zero_explicit_not_delivered_and_fixing_values(self):
        r=compare([self.item()],[(2,self.row(0))],{0:2})[0]
        self.assertIn('THIẾU 10',presentation(r)['label'])
        r=compare([self.item()],[],{0:None})[0];self.assertIn('short',r['alerts'])
        r=compare([self.item()],[(2,self.row())],{0:2})[0]
        self.assertEqual(r['alerts'],[]);self.assertIsNone(presentation(r)['background'])

if __name__=='__main__':unittest.main()
