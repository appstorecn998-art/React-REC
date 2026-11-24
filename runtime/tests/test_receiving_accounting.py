from PIL import Image
import unittest
import tempfile
from pathlib import Path
from datetime import datetime,date
from unittest.mock import patch
from openpyxl import Workbook,load_workbook
import receiving_service as rs

class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.day=date(datetime.now().year,11,5)
    def test_existing_legacy_and_images_no_auto_fallback(self):
        directory=rs.day_directory(self.root,self.day);directory.mkdir(parents=True)
        legacy=directory/'TongHopNhieuPhieuGiaoHang.xlsx';legacy.touch()
        (directory/'Phiếu giao hàng').mkdir();Image.new('RGB',(12,12),'white').save(directory/'Phiếu giao hàng'/'x.JPG')
        folder,report=rs.paths(self.root/'Auto',self.day,self.root/'Thang 11')
        self.assertEqual(report,legacy);self.assertEqual(len(rs.day_images(directory)),1)
        added=rs.import_images(self.root/'Auto',self.day,[directory/'Phiếu giao hàng'/'x.JPG'],self.root)
        self.assertEqual(len(added),1)
        self.assertTrue(added[0].is_file())
        self.assertEqual(rs.import_images(self.root/'Auto',self.day,[directory/'Phiếu giao hàng'/'x.JPG'],self.root),[])
        self.assertTrue((directory/'Phiếu giao hàng'/'x.JPG').is_file())
        self.assertFalse((self.root/'Auto').exists())
    def test_year_and_month_isolation(self):
        old=date(datetime.now().year-1,11,5)
        self.assertEqual(rs.day_directory(self.root,old),self.root/str(old.year)/'Thang 11'/'Ngay 05')
        self.assertEqual(rs.day_directory(self.root,date(self.day.year,12,1)),self.root/'Thang 12'/'Ngay 01')
    def test_ambiguous_report_refused(self):
        directory=rs.day_directory(self.root,self.day);directory.mkdir(parents=True)
        (directory/'TongHopNhieuPhieuGiaoHang.xlsx').touch();(directory/f'TongHopPhieuNgay_{self.day:%d-%m-%Y}.xlsx').touch()
        with self.assertRaises(ValueError):rs.find_day_report(directory,self.day)
    def test_standard_amount_and_zero_display(self):
        data=[(2,{'Thực nhận':0,'Số lượng':10,'Đơn giá':50,'Thành tiền':'=IF(COUNT(N2,O2)=2,N2*O2,"CHƯA RÕ")','Thành tiền trên phiếu':'=IF(COUNT(M2,O2)=2,M2*O2,"CHƯA RÕ")'})]
        values=rs.display_rows(data)[0][1]
        self.assertEqual(values['Thành tiền'],0);self.assertEqual(values['Thành tiền trên phiếu'],500)
        self.assertTrue(data[0][1]['Thành tiền'].startswith('='))
    def test_canonical_export_keeps_report_and_backs_up_existing_output(self):
        directory=rs.day_directory(self.root,self.day);directory.mkdir(parents=True)
        report=directory/'TongHopNhieuPhieuGiaoHang.xlsx';book=Workbook();book.active['A1']='source';book.save(report);book.close()
        output=directory/f'Phieu giao hang {self.day.day}-{self.day.month}-{self.day.year}.xlsx'
        output.write_bytes(b'old export');before=report.read_bytes()
        def export(source,catalog,excel,rules,target,template):
            book=Workbook();book.active['A1']='export';book.save(target);book.close()
        with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('multi_delivery_export.export_multiple',side_effect=export):
            result=rs.close_day(self.root/'Auto',self.day,self.root,template=self.root/'template',report_override=report)
        self.assertEqual(result,directory);self.assertEqual(before,report.read_bytes())
        self.assertTrue(list((directory/'.receiving'/'publish-backups').rglob(output.name)))
        self.assertFalse((self.root/'Auto'/report.name).exists())

if __name__=='__main__':unittest.main()
