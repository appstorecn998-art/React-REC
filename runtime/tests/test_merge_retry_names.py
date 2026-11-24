import ctypes
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
sys.path.append('C:/Users/Fenn/Desktop/Auto/tests')
import manual_invoice_links as links
import merge_saved_delivery as cli
import AutoWatcher as aw
from test_merge_saved_delivery import add_invoice


class RenameLock:
    def __init__(self,path):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        create=self.kernel.CreateFileW
        create.argtypes=[ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p]
        create.restype=ctypes.c_void_p
        self.handle=create(str(path),0x80000000,3,None,3,0,None)
        if self.handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle:
            self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            self.kernel.CloseHandle(self.handle);self.handle=None


class MergeRetryNamesTests(unittest.TestCase):
    def test_extensionless_names_resolve_actual_extension_and_date_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'IMG_A.JPG');add_invoice(p,'IMG_B.PNG')
            refs=cli.parse_names('img_a, IMG_B')
            self.assertEqual(refs,['img_a','IMG_B'])
            title=links.merge_saved_invoices(p,refs)
            self.assertEqual(title,'IMG_A+IMG_B')
            received,names=links.parse_receipt_input('15/10 thuộc phiếu giao hàng trong ảnh IMG_A')
            links.check_references(p,names,received)
            self.assertEqual(names,['IMG_A'])

    def test_ambiguous_stem_requires_extension_without_changing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'SAME.JPG');add_invoice(p,'SAME.PNG');add_invoice(p,'OTHER.JPG')
            before=p.read_bytes()
            with self.assertRaisesRegex(ValueError,'trùng nhiều định dạng'):links.merge_saved_invoices(p,['SAME','OTHER'])
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(links.merge_saved_invoices(p,['SAME.PNG','OTHER']),'SAME+OTHER')

    def test_real_windows_lock_retries_prepared_workbook_once_without_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.JPG')
            lock=RenameLock(p)
            def retry(error):
                self.assertIsInstance(error,PermissionError)
                lock.close();return True
            try:
                with patch.object(links,'merge_sheets',wraps=links.merge_sheets) as merge,patch.object(links,'load_workbook',wraps=links.load_workbook) as load:
                    title=links.merge_saved_invoices(p,['A','B'],retry_write=retry)
                    self.assertEqual(merge.call_count,1);self.assertEqual(load.call_count,1)
                self.assertEqual(title,'A+B')
                wb=aw.load_workbook(p);self.assertEqual(wb.active.max_row,3);wb.close()
            finally:lock.close()

    def test_user_changes_workbook_while_waiting_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.JPG')
            lock=RenameLock(p)
            def retry(error):
                lock.close()
                wb=aw.load_workbook(p);wb.active['G2']='Sửa khi đang chờ';wb.save(p);wb.close()
                return True
            try:
                with self.assertRaisesRegex(ValueError,'thay đổi'):links.merge_saved_invoices(p,['A','B'],retry_write=retry)
                wb=aw.load_workbook(p);self.assertEqual(len(wb.sheetnames),2);self.assertEqual(wb.active['G2'].value,'Sửa khi đang chờ');wb.close()
            finally:lock.close()

    def test_cancel_locked_write_keeps_original_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.JPG');before=p.read_bytes()
            lock=RenameLock(p)
            try:
                with self.assertRaises(PermissionError):links.merge_saved_invoices(p,['A','B'],retry_write=lambda error:False)
                self.assertEqual(p.read_bytes(),before);self.assertEqual(list(p.parent.glob('*.xlsx')),[p])
            finally:lock.close()

    def test_cli_retries_with_enter_without_selecting_images_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.PNG')
            lock=RenameLock(p);answers=iter(['A B','CO','','Q'])
            def answer(prompt):
                value=next(answers)
                if 'thử ghi lại' in prompt:lock.close()
                return value
            try:
                with patch('builtins.input',side_effect=answer):self.assertEqual(cli.run(p),0)
                wb=aw.load_workbook(p);self.assertEqual(wb.sheetnames,['A+B']);wb.close()
            finally:lock.close()


if __name__=='__main__':unittest.main()
