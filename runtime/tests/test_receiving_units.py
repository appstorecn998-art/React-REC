import sys
from pathlib import Path
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
import unittest
from decimal import Decimal
from receiving_units import conversion,factor_for,approved_conversion
from receiving_pr import compare
from receiving_ledger import allocations

class UnitTests(unittest.TestCase):
    def test_fraction_one_twentieth_converts_packs_to_box(self):
        pr={'item_name':'Gia vị hộp 20 gói','unit':'Hộp','quantity':'1','unit_price':'350000'}
        value={'Tên hàng trên phiếu (Ảnh)':'Gia vị hộp 20 gói','Đơn vị tính':'Gói','Số lượng':20,'Thực nhận':20,'Đơn giá':17500}
        c={0:conversion(2,pr,value,'1/20','Quy cách đã kiểm')}
        r=compare([pr],[(2,value)],{0:2},c)[0]
        self.assertEqual(r['received'],1);self.assertEqual(r['delivery_price'],350000);self.assertEqual(r['remaining'],0)
        self.assertEqual(allocations([pr],[(2,value)],{0:2},c),{'0':'1'})
        self.assertEqual(conversion(2,pr,value,'0,05','Đã kiểm')['factor'],'0.05')
        with self.assertRaises(ValueError):conversion(2,pr,value,'1/0','Đã kiểm')
    def setUp(self):
        self.pr={'item_name':'Sữa mẫu','unit':'hộp','quantity':'24','unit_price':'10000'}
        self.value={'Tên hàng trên phiếu (Ảnh)':'Sữa mẫu','Đơn vị tính':'thùng','Số lượng':1,'Thực nhận':1,'Đơn giá':240000,'Mã vật tư':'001'}
    def test_example_converts_quantity_and_unit_price_and_ledger(self):
        c={0:conversion(2,self.pr,self.value,'24','Ví dụ trong test, không phải quy tắc thật')}
        r=compare([self.pr],[(2,self.value)],{0:2},c)[0]
        self.assertEqual(r['received'],24);self.assertEqual(r['delivery_price'],10000);self.assertEqual(r['remaining'],0)
        self.assertEqual(r['original_received'],1);self.assertEqual(r['original_price'],240000)
        self.assertEqual(allocations([self.pr],[(2,self.value)],{0:2},c),{'0':'24'})
        self.assertEqual(self.value['Đơn vị tính'],'thùng');self.assertEqual(self.value['Đơn giá'],240000)
    def test_zero_unknown_scope_and_invalid_factors(self):
        c={0:conversion(2,self.pr,self.value,'24','Đã kiểm')}
        changed=dict(self.value,**{'Mã vật tư':'002'})
        self.assertIsNone(factor_for(c,0,2,self.pr,changed)[0])
        for value in ['0','-1','NaN','Infinity','abc']:
            with self.assertRaises(ValueError):conversion(2,self.pr,self.value,value,'Đã kiểm')
        zero=dict(self.value,**{'Thực nhận':0})
        self.assertEqual(compare([self.pr],[(2,zero)],{0:2},c)[0]['received'],0)
        unknown=dict(self.value,**{'Thực nhận':None})
        self.assertIsNone(compare([self.pr],[(2,unknown)],{0:2},c)[0]['received'])
        with self.assertRaises(ValueError):allocations([self.pr],[(2,self.value)],{0:2})
    def test_oil_approved_rule_is_exact_supplier_product_and_units(self):
        pr={'item_name':'Dầu ăn cái Lân 25kg','unit':'can'}
        value={'Tên hàng trên phiếu (Ảnh)':'CÁI LÂN CAN 25KG','Mã vật tư':'11710025','Đơn vị tính':'Gallon'}
        rule={'supplier_name':'Hoàng Kha','pr_item_name':pr['item_name'],'delivery_item_name':value['Tên hàng trên phiếu (Ảnh)'],'catalog_code':'11710025','pr_unit':'can','delivery_unit':'Gallon','factor':'1','basis':'Người dùng xác nhận'}
        self.assertIsNotNone(approved_conversion({'unit_conversions':[rule]},'Hoàng Kha',2,pr,value))
        self.assertIsNone(approved_conversion({'unit_conversions':[rule]},'NCC khác',2,pr,value))
        self.assertIsNone(approved_conversion({'unit_conversions':[rule]},'Hoàng Kha',2,dict(pr,item_name='Dầu ăn khác'),value))
        self.assertIsNone(approved_conversion({'unit_conversions':[rule]},'Hoàng Kha',2,pr,dict(value,**{'Mã vật tư':'002'})))

if __name__=='__main__':unittest.main()
