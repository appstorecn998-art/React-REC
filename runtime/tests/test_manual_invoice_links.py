import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import AutoWatcher as aw
import multi_delivery as multi
import manual_invoice_links as links
from test_delivery_pages import document
from types import SimpleNamespace


def row(name,amount=10,received='15/10/2026'):
    result=['Cá','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','Ghi chú sửa tay','NCC','','','','',1,0,amount,amount,'2026-10-15','','','','','']
    return result+[received,name,'','1',hashlib.sha256(name.encode()).hexdigest()]


def save(report,name,**kw):
    rows=[row(name,**kw)]
    multi.save_one(report,multi.image_key(hashlib.sha256(name.encode()).hexdigest()),rows,sheet_title=Path(name).stem)
    return rows


class ManualInvoiceLinksTests(unittest.TestCase):
    def test_parse_date_phrase_multiple_names_and_invalid_input(self):
        day,refs=links.parse_receipt_input('15/10 thuộc phiếu giao hàng trong ảnh IMG_4098.JPG, IMG_4099.JPG')
        self.assertEqual(day,date(aw.datetime.now().year,10,15))
        self.assertEqual(refs,['IMG_4098.JPG','IMG_4099.JPG'])
        self.assertEqual(links.parse_receipt_input('15/10/2026 thuoc phieu giao hang trong anh IMG_4098.JPG')[1],['IMG_4098.JPG'])
        for text in ['31/02 thuộc phiếu giao hàng trong ảnh IMG_4098.JPG','15/10 thuộc phiếu giao hàng trong ảnh xxx.exe','15/10 thuộc phiếu giao hàng trong ảnh ../a.jpg']:
            with self.assertRaises(ValueError):links.parse_receipt_input(text)

    def test_append_two_more_pages_keeps_user_edits_total_hashes_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'TongHopNhieuPhieuGiaoHang.xlsx'
            save(report,'IMG_4098.JPG')
            wb=aw.load_workbook(report);wb.active['N2']=0;wb.active['G2']='Đã rà';wb.active['A2']='=không chạy';wb.active['A2'].data_type='s';wb.save(report);wb.close()
            for name in ('IMG_4099.JPG','IMG_4100.JPG'):
                rows=[row(name)]
                self.assertTrue(multi.save_one(report,multi.image_key(hashlib.sha256(name.encode()).hexdigest()),rows,sheet_title=Path(name).stem,link_images=['IMG_4098.JPG']))
            wb=aw.load_workbook(report);self.assertEqual(wb.sheetnames,['IMG_4098+IMG_4099+IMG_4100'])
            sheet=wb.active
            self.assertEqual(sheet.max_row,4);self.assertEqual(sheet['N2'].value,0);self.assertEqual(sheet['G2'].value,'Đã rà')
            self.assertEqual(sheet['A2'].data_type,'s')
            self.assertIn('P2:P4',sheet['Y2'].value)
            self.assertEqual([sheet.cell(r,24).value for r in (2,3,4)],['IMG_4098.JPG','IMG_4099.JPG','IMG_4100.JPG'])
            self.assertEqual(links.sheet_images(sheet),['IMG_4098.JPG','IMG_4099.JPG','IMG_4100.JPG']);wb.close()
            self.assertEqual(len(multi.saved_image_digests(report)),3)
            self.assertEqual(len([r for batch in aw.reviewed_delivery_rows(report,{},date_header='Ngày nhận hàng xác nhận') for r in batch]),3)
            before=report.read_bytes()
            self.assertEqual(links.merge_saved_invoices(report,['IMG_4098.JPG','IMG_4100.JPG']),'IMG_4098+IMG_4099+IMG_4100')
            self.assertEqual(report.read_bytes(),before)

    def test_existing_separate_sheets_merge_preserves_other_sheets_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'TongHopNhieuPhieuGiaoHang.xlsx'
            for n in ['IMG_4098.JPG','IMG_4099.JPG','OTHER.JPG']:save(report,n)
            before=report.read_bytes()
            title=links.merge_saved_invoices(report,['IMG_4099.JPG','IMG_4098.JPG'])
            wb=aw.load_workbook(report);self.assertEqual(title,'IMG_4098+IMG_4099');self.assertEqual(wb['OTHER']['G2'].value,'Ghi chú sửa tay');self.assertEqual(len(wb.sheetnames),2);wb.close()
            backups=list(report.parent.glob('.autowatcher-backups/manual-group-*/*.xlsx'))
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),before)

    def test_wrong_name_date_or_locked_final_write_leaves_report_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'TongHopNhieuPhieuGiaoHang.xlsx'
            save(report,'IMG_4098.JPG');before=report.read_bytes()
            with self.assertRaisesRegex(ValueError,'chưa được lưu'):links.check_references(report,['missing.jpg'],date(2026,10,15))
            with self.assertRaisesRegex(ValueError,'Ngày nhận khác'):links.check_references(report,['IMG_4098.JPG'],date(2026,10,16))
            replace=links.os.replace
            def locked(src,dst):
                if Path(dst)==report:raise PermissionError('locked')
                replace(src,dst)
            with patch.object(links.os,'replace',side_effect=locked):
                with self.assertRaises(PermissionError):links.save_linked_invoice(report,Path('new'),[row('IMG_4099.JPG')],['IMG_4098.JPG'],multi.EXTRA_HEADERS,'IMG_4099')
            self.assertEqual(report.read_bytes(),before)

    def test_sheet_limit_compacts_names_and_keeps_full_image_list(self):
        names=[f'IMG_{n}.JPG' for n in range(4098,4105)]
        self.assertLessEqual(len(links.group_title(names)),31)
        self.assertEqual(links.group_title(names[:4]),'IMG_4098+4099+4100+4101')

    def test_multiple_references_merge_saved_pages_plus_current_without_dropping_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'TongHopNhieuPhieuGiaoHang.xlsx'
            save(report,'PAGE_A.JPG');save(report,'PAGE_B.JPG')
            multi.save_one(report,Path('keyC'),[row('PAGE_C.JPG')],sheet_title='PAGE_C',link_images=['PAGE_A.JPG','PAGE_B.JPG'])
            wb=aw.load_workbook(report)
            self.assertEqual(wb.sheetnames,['PAGE_A+PAGE_B+PAGE_C']);self.assertEqual(wb.active.max_row,4)
            self.assertEqual([wb.active.cell(r,7).value for r in (2,3,4)],['Ghi chú sửa tay']*3)
            wb.close()

    def test_bad_reference_reprompts_and_never_changes_saved_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'TongHopNhieuPhieuGiaoHang.xlsx';save(report,'PAGE_A.JPG')
            before=report.read_bytes()
            with patch('builtins.input',side_effect=['15/10 thuộc phiếu giao hàng trong ảnh missing.jpg','15/10 thuộc phiếu giao hàng trong ảnh PAGE_A.JPG']):
                received,refs=multi.ask_receipt_date(Path('PAGE_B.JPG'),report=report,with_links=True)
            self.assertEqual(refs,['PAGE_A.JPG']);self.assertEqual(received,date(2026,10,15));self.assertEqual(report.read_bytes(),before)

    def test_run_manual_link_overrides_separate_ai_pages_and_resume_uses_saved_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            for n in ('IMG_4098.JPG','IMG_4099.JPG'):(folder/n).write_bytes(n.encode())
            args=SimpleNamespace(input=folder,output=root,excel=Path('fixture'),rules=Path('fixture'),timeout=5)
            def extract(path,*args):
                doc=document(1,2,has_total=True)
                doc['reference_id']=path.stem
                return dict(path=str(path),document=doc)
            with patch.object(aw,'load_catalog_data',return_value=({},{})),patch.object(aw,'read_rules',return_value={'suppliers':[]}),patch.object(multi,'load_warehouse_directory',return_value={}),patch.object(aw,'wait_ready'),patch.object(aw,'extract_batch_document',side_effect=extract) as ocr,patch.object(multi,'enrich_rows',side_effect=lambda rows,*a,**k:rows),patch('builtins.input',side_effect=['15/10','15/10 thuộc phiếu giao hàng trong ảnh IMG_4098.JPG']):
                self.assertEqual(multi.run(args,'unused'),0)
                wb=aw.load_workbook(root/'TongHopNhieuPhieuGiaoHang.xlsx');self.assertEqual(wb.sheetnames,['IMG_4098+IMG_4099']);self.assertEqual(wb.active.max_row,5);wb.close()
                ocr.reset_mock()
                self.assertEqual(multi.run(args,'unused'),0)
                ocr.assert_not_called()


if __name__=='__main__':unittest.main()
