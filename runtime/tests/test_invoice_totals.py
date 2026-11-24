from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from openpyxl import Workbook,load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import AutoWatcher as aw
import multi_delivery as multi

HEADER='Tổng tiền phiếu (cộng Thành tiền)'


def make_report(path):
    workbook=Workbook();sheet=workbook.active;sheet.title='Phiếu 1'
    sheet.append(aw.HEADERS+['Người đề nghị PR','Căn cứ PR phân kho','Ngày nhận hàng xác nhận','Ảnh nguồn'])
    for amount in (100000,0,25000.5):
        row=['Hàng trùng','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','Sửa tay','NCC','','','','',1,1,10,amount,'2026-10-30','','','','','','30/10/2026','ảnh.jpg']
        sheet.append(row)
    second=workbook.copy_worksheet(sheet);second.title='Phiếu 2';second['P2']=300
    workbook.save(path);workbook.close()


class InvoiceTotalsTests(unittest.TestCase):
    def test_upgrade_adds_one_formula_per_invoice_preserves_all_old_cells_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'TongHopNhieuPhieuGiaoHang.xlsx';make_report(path)
            before=path.read_bytes();book=load_workbook(path)
            values={s.title:[[c.value for c in row] for row in s] for s in book};book.close()
            self.assertEqual(multi.upgrade_invoice_totals(path),2)
            book=load_workbook(path)
            for sheet in book:
                self.assertEqual(sheet['Y1'].value,HEADER)
                self.assertEqual(sheet['Y2'].value,'=IF(COUNT(P2:P4)<>COUNTA(A2:A4),"THIẾU THÀNH TIỀN",SUM(P2:P4))')
                self.assertEqual(sheet['Y2'].data_type,'f')
                self.assertIsNone(sheet['Y3'].value)
                for r,row in enumerate(values[sheet.title],1):
                    for c,value in enumerate(row,1):self.assertEqual(sheet.cell(r,c).value,value)
            self.assertTrue(book.calculation.fullCalcOnLoad);book.close()
            backups=list((path.parent/'.autowatcher-backups').glob('invoice-totals-*/*.xlsx'))
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),before)
            after=path.read_bytes();self.assertEqual(multi.upgrade_invoice_totals(path),0);self.assertEqual(path.read_bytes(),after)

    def test_new_sheet_total_and_ocr_formula_injection_remains_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.xlsx'
            row=['=CMD()','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','','NCC','','','','',1,1,10,10,'','','','']
            row.extend(['','','30/10/2026','a.jpg'])
            aw.write_result(report,Path('a.jpg'),[row],extra_headers=multi.EXTRA_HEADERS,invoice_total=True)
            book=load_workbook(report);sheet=book.active
            self.assertEqual(sheet['A2'].data_type,'s')
            self.assertEqual(sheet['Y2'].data_type,'f')
            self.assertIn('COUNT(P2:P2)',sheet['Y2'].value)
            book.close()

    def test_failed_write_keeps_old_workbook_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.xlsx';make_report(report);before=report.read_bytes()
            with patch.object(multi.os,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):multi.upgrade_invoice_totals(report)
            self.assertEqual(report.read_bytes(),before)
            self.assertEqual(list(report.parent.glob('*.xlsx')),[report])

if __name__=='__main__':unittest.main(verbosity=2)
