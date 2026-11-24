from PIL import Image
import unittest
import tempfile
from pathlib import Path
from datetime import date
from unittest.mock import patch
from openpyxl import Workbook, load_workbook
import receiving_service as rs

class ReceivingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.day=date(2026,11,6)
    def report(self):
        _,path=rs.paths(self.base,self.day)
        w=Workbook();s=w.active;s.title='Invoice'
        s.append(['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Tên chuẩn hệ thống','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Thành tiền','Ghi chú'])
        s.append(['Cá','001','Cá','kg',10,7,50000,'=F2*G2',''])
        s.append(['Cá','','','kg',2,0,50000,'=F3*G3',''])
        w.save(path);w.close();Image.new('RGB',(20,20),'white').save(path.parent/'Invoice.jpg');return path
    def test_import_duplicate_and_collision(self):
        a=self.base/'a';b=self.base/'b';a.mkdir();b.mkdir()
        Image.new('RGB',(12,12),'white').save(a/'x.jpg');Image.new('RGB',(12,12),'black').save(b/'x.jpg')
        original=(a/'x.jpg').read_bytes()
        first=rs.import_images(self.base,self.day,[a/'x.jpg'])
        self.assertEqual(len(first),1)
        archived=first[0].read_bytes()
        with self.assertRaisesRegex(ValueError,'Tên ảnh trùng'):
            rs.import_images(self.base,self.day,[b/'x.jpg'])
        self.assertEqual(first[0].read_bytes(),archived)
        self.assertEqual(rs.import_images(self.base,self.day,[a/'x.jpg']),[])
        self.assertEqual((a/'x.jpg').read_bytes(),original)
    def test_edit_zero_preserve_formula_and_duplicate_rows(self):
        p=self.report();rs.edit_row(p,rs.digest(p),'Invoice',2,{'Thực nhận':'0','Ghi chú':'=unsafe'}, {'001':('Cá','kg')})
        w=load_workbook(p);s=w.active
        self.assertEqual(s['F2'].value,0);self.assertEqual(s['H2'].value,'=F2*G2')
        self.assertEqual(s['I2'].data_type,'s');self.assertEqual(s.max_row,3);w.close()
        self.assertTrue(list((self.base/'.autowatcher-backups').rglob('*.xlsx')))
    def test_stale_edit_refused(self):
        p=self.report();old=rs.digest(p)
        w=load_workbook(p);w.active['F2']=5;w.save(p);w.close()
        with self.assertRaises(ValueError):rs.edit_row(p,old,'Invoice',2,{'Thực nhận':'0'}, {})
    def test_unknown_code_and_invalid_number_do_not_write(self):
        p=self.report();before=p.read_bytes()
        for change in [{'Mã vật tư':'missing'},{'Thực nhận':'-1'},{'Đơn giá':'NaN'},{'Thực nhận':'1,200'}]:
            with self.assertRaises(ValueError):rs.edit_row(p,rs.digest(p),'Invoice',2,change,{'001':('Cá','kg')})
            self.assertEqual(before,p.read_bytes())
    def fake_export(self,report,catalog,excel,rules,output,template):
        w=Workbook();w.active['A1']='export';w.save(output);w.close()
    def test_publish_same_source_preserves_edits_and_changed_source_blocks(self):
        p=self.report();dest=self.base/'accounting';template=self.base/'template.xlsx'
        with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('multi_delivery_export.export_multiple',side_effect=self.fake_export):
            target=rs.close_day(self.base,self.day,dest,template)
            self.assertEqual(target,dest/'Thang 11'/'Ngay 06')
            out=target/'Phieu giao hang 6-11-2026.xlsx'
            w=load_workbook(out);w.active['A1']='user edit';w.save(out);w.close()
            modified=out.read_bytes()
            rs.close_day(self.base,self.day,dest,template);self.assertEqual(out.read_bytes(),modified)
            w=load_workbook(p);w.active['F2']=4;w.save(p);w.close()
            with self.assertRaises(ValueError):rs.close_day(self.base,self.day,dest,template)
            self.assertEqual(out.read_bytes(),modified)
    def test_publish_second_file_failure_rolls_back_first(self):
        p=self.report();dest=self.base/'accounting'
        import AutoWatcher as aw
        original_copy=aw.atomic_copy_file
        def fail_second(source,target):
            if Path(target).name.startswith('Phieu giao hang'):raise PermissionError('locked')
            return original_copy(source,target)
        with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('multi_delivery_export.export_multiple',side_effect=self.fake_export),patch('AutoWatcher.atomic_copy_file',side_effect=fail_second):
            with self.assertRaises(PermissionError):rs.close_day(self.base,self.day,dest,self.base/'template')
        self.assertFalse((dest/'Thang 11'/'Ngay 06'/p.name).exists())
        self.assertFalse((rs.paths(self.base,self.day)[0]/'published.json').exists())

if __name__=='__main__':unittest.main()
