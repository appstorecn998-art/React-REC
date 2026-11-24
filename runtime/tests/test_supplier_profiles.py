import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from openpyxl import Workbook
import warehouse_directory as wh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import supplier_rules as sr
import AutoWatcher as aw
from supplier_directory import load_supplier_directory, supplier_aliases, resolve_supplier

SOURCE = Path('C:/Users/Fenn/Desktop/Auto/DanhMuc.xlsm')

class SupplierProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.groups = aw.load_catalog_data(SOURCE)
        cls.rules = sr.read_rules(Path(sr.__file__).with_name('NhaCungCap.json'), cls.catalog, cls.groups)

    def plan(self, supplier, name, group):
        return sr.build_plans({'supplier_name':supplier,'items':[{'invoice_name':name,'group_id':group}]},self.catalog,self.groups,self.rules)[0]

    def test_food_exceptions_stay_in_their_actual_groups(self):
        for supplier,name,group in [('Thực phẩm Phú Quốc','THỊT BA CHỈ HEO','1110'),('Huyền Nam','Trứng vịt muối','1540')]:
            with self.subTest(supplier=supplier):
                p=self.plan(supplier,name,group)
                self.assertFalse(p['conflict'])
                self.assertEqual(p['group_ids'],{group})
                self.assertEqual(p['invoice_name'],name)

    def test_dry_goods_and_coffee_groups_are_hints_after_full_catalog(self):
        for supplier,name,group in [('Thành Phố Thực phẩm','Bột nổi Mauri - 1kg','1610'),('Cửu Long','Cà phê Palazzo hạt-1kg','1940')]:
            p=self.plan(supplier,name,group)
            self.assertFalse(p['conflict'])
            self.assertTrue(p['catalog'])
            self.assertEqual(set(p['catalog']),set(self.catalog))
            self.assertEqual(p['context']['suggested_group_id'],group)

    def test_conflict_is_not_forced_to_supplier_default(self):
        p=self.plan('Thực phẩm Phú Quốc','Cà phê','1940')
        self.assertFalse(p['conflict'])
        self.assertEqual(set(p['catalog']),set(self.catalog))

    def test_supplier_outside_catalog_hint_does_not_assign_a_food_code(self):
        for supplier,name in [('Đảo Ngọc','Ném túi đậu / Bean Bag Toss'),('Phú Cường','pin 3a'),('Ngọc Trai','Khí dầu mỏ hóa lỏng LPG - Bình gas 45kg')]:
            p=self.plan(supplier,name,'')
            self.assertTrue(p['supplier_known'])
            self.assertEqual(set(p['catalog']),set(self.catalog))
            self.assertEqual(p['approved_code'],'')
            self.assertEqual(p['invoice_name'],name)

    def test_mega_uses_each_line_and_flags_unknown(self):
        self.assertEqual(self.plan('Mega','Sữa Vinamilk 1L','1510')['group_ids'],{'1510'})
        self.assertEqual(self.plan('Mega','Nước tương Maggi 1.8L','1710')['group_ids'],{'1710'})
        p=self.plan('Mega','Hàng chưa rõ','')
        self.assertEqual(set(p['catalog']),set(self.catalog))
        self.assertIn('ngữ cảnh',p['note'])
        self.assertIsNone(sr.find_supplier('CHI NHÁNH CÔNG TY TNHH MM MEGA MARKET (VIỆT NAM) TẠI KIÊN GIANG',self.rules))

    def test_full_supplier_names_and_existing_rules_preserved(self):
        self.assertEqual(self.plan('Thành Phố Thực phẩm','Bột nổi Mauri - 1kg','1610')['supplier_name'],'CÔNG TY TNHH THÀNH PHỐ THỰC PHẨM')
        self.assertEqual(self.plan('Đức Tú','Thanh long ĐP','1410')['approved_code'],'11410050')
        directory=load_supplier_directory(SOURCE)
        aliases=supplier_aliases(self.rules,directory)
        long_name=sr.find_supplier('Thực phẩm Phú Quốc',self.rules)['name']
        self.assertEqual(resolve_supplier(long_name,directory,aliases)[0],'1702150914')

    def test_confirmed_coffee_and_gas_do_not_call_ai(self):
        records=[{'line_id':1,'supplier_name':'CÔNG TY CỔ PHẦN VƯỜN TRÁI CỬU LONG','invoice_name':'Cà phê Palazzo hạt-1kg','requester_name':'Nguyen Thi My Thi','pr_status':'ĐÃ GHÉP PR'},
                 {'line_id':2,'supplier_name':'CÔNG TY CỔ PHẦN DẦU KHÍ NGỌC TRAI PHÚ QUỐC','invoice_name':'Khí dầu mỏ hóa lỏng LPG - Bình gas 45kg'}]
        directory={'1202':('Kho nhà hàng Caya','FB'),'1900':('Kho nhiên liệu','ENG')}
        with tempfile.TemporaryDirectory() as tmp, patch.object(wh,'request_choices',side_effect=AssertionError('No API')):
            result=wh.classify_records(records,directory,'unused','model',5,tmp,self.rules)
        self.assertEqual(result[0][:3],('1202','Kho nhà hàng Caya','FB'))
        self.assertEqual(result[1][:3],('1900','Kho nhiên liệu','ENG'))

    def test_juice_stationery_and_gas_cylinders_not_forced_into_confirmed_warehouses(self):
        records=[{'line_id':1,'supplier_name':'Cửu Long','invoice_name':'Nước ép táo'},
                 {'line_id':2,'supplier_name':'Đảo Ngọc','invoice_name':'Giấy in A4'},
                 {'line_id':3,'supplier_name':'Ngọc Trai','invoice_name':'Vỏ bình gas 45kg'},
                 {'line_id':4,'supplier_name':'Other supplier','invoice_name':'Cà phê Palazzo'}]
        response={'items':[{'line_id':r['line_id'],'category':'unknown','note':'Cần xác nhận'} for r in records]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(wh,'request_choices',return_value=response) as request:
            result=wh.classify_records(records,{'1202':('Caya','FB'),'1900':('Nhiên liệu','ENG')},'unused','model',5,tmp,self.rules)
            self.assertEqual(request.call_count,1)
        self.assertTrue(all(not r[0] for r in result))

    def test_explicit_gas_department_fills_blank_without_editing_excel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'DanhMuc.xlsx'
            workbook=Workbook(); sheet=workbook.active; sheet.title='DanhMucKho'
            sheet.append(list(wh.WAREHOUSE_HEADERS)); sheet.append(['1900','Kho nhiên liệu',None])
            workbook.save(path); workbook.close()
            before=path.read_bytes()
            path.with_name('NhaCungCap.json').write_text(json.dumps({'warehouse_departments':{'1900':'ENG'}}),encoding='utf-8')
            self.assertEqual(wh.load_warehouse_directory(path)['1900'],('Kho nhiên liệu','ENG'))
            self.assertEqual(path.read_bytes(),before)

if __name__=='__main__': unittest.main(verbosity=2)
