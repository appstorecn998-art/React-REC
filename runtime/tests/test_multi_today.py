"""Kiểm chế độ hôm nay bằng workbook tạm, không gọi OCR/API thật."""
from contextlib import ExitStack, closing
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import multi_delivery as multi


def document(path):
    return dict(path=str(path),document=dict(
        document_type='delivery',reference_id=path.stem,supplier_name='NCC test',
        delivery_date='2026-10-28',has_total=True,
        items=[dict(item_name='Cá',english_name='',vietnamese_name='',catalog_code='',
                    quantity='1',received_quantity='1',unit='kg',unit_price='10',
                    line_amount='10',specification='',group_id='',source_stt='1')]))


def read_invoice(entries,*unused):
    rows=[['Cá','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','','NCC test',
           '','','','',1,1,10,10,'2026-10-28','','','']]
    return rows,[dict(source_image=Path(entries[0]['path']).name,source_stt='1')]


class TodayDeliveryTests(unittest.TestCase):
    def test_today_saves_all_invoices_without_date_prompt_and_resumes_per_day(self):
        with tempfile.TemporaryDirectory(prefix='Auto ngay hom nay ') as tmp,ExitStack() as stack:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            (folder/'one.jpg').write_bytes(b'one')
            (folder/'two.jpg').write_bytes(b'two')
            legacy=root/'TongHopNhieuPhieuGiaoHang.xlsx'
            legacy.write_bytes(b'Existing manual report must be left alone')
            args=SimpleNamespace(input=folder,output=root,excel=root/'fixture',
                                 rules=root/'fixture',timeout=5,receipt_date=date(2026,11,5))
            stack.enter_context(patch.object(multi.aw,'load_catalog_data',return_value=({},{})))
            stack.enter_context(patch.object(multi.aw,'read_rules',return_value={}))
            stack.enter_context(patch.object(multi,'load_warehouse_directory',return_value={}))
            stack.enter_context(patch.object(multi.aw,'wait_ready'))
            stack.enter_context(patch.object(multi,'enrich_rows',side_effect=lambda rows,*a,**kw:rows))
            extractor=stack.enter_context(patch.object(multi.aw,'extract_batch_document',side_effect=lambda path,*a:document(path)))
            reader=stack.enter_context(patch.object(multi,'read_invoice',side_effect=read_invoice))
            stack.enter_context(patch('builtins.input',side_effect=AssertionError('Must not ask for a date')))
            stack.enter_context(patch('socket.socket.connect',side_effect=AssertionError('No network in offline test')))
            self.assertEqual(multi.run(args,'unused'),0)
            report=root/'TongHopPhieuNgay_05-11-2026.xlsx'
            with closing(load_workbook(report)) as workbook:
                self.assertEqual(len(workbook.sheetnames),2)
                for sheet in workbook:
                    self.assertEqual(sheet['W2'].value,'05/11/2026')
                    self.assertEqual(sheet['Q2'].value,'2026-10-28')
                    self.assertEqual(sheet['X2'].value,sheet.title+'.jpg')
                workbook.active['G2']='Đã rà và sửa tay'
                workbook.save(report)
            saved_bytes=report.read_bytes()
            (folder/'duplicate.jpg').write_bytes(b'one')
            extractor.reset_mock();reader.reset_mock()
            self.assertEqual(multi.run(args,'unused'),0)
            extractor.assert_not_called();reader.assert_not_called()
            self.assertEqual(report.read_bytes(),saved_bytes)
            args.receipt_date=date(2026,11,6)
            self.assertEqual(multi.run(args,'unused'),0)
            with closing(load_workbook(root/'TongHopPhieuNgay_06-11-2026.xlsx')) as workbook:
                self.assertEqual(len(workbook.sheetnames),2)
                self.assertTrue(all(sheet['W2'].value=='06/11/2026' for sheet in workbook))
            self.assertEqual(report.read_bytes(),saved_bytes)
            self.assertEqual(legacy.read_bytes(),b'Existing manual report must be left alone')

    def test_main_reads_machine_day_on_each_launch_and_keeps_it_fixed_in_session(self):
        dates=[datetime(2026,11,5,23,59),datetime(2026,11,6),
               datetime(2026,12,31),datetime(2027,1,1)]
        with tempfile.TemporaryDirectory(prefix='Auto CLI date ') as tmp:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            (folder/'one.jpg').write_bytes(b'fixture')
            for now in dates:
                with self.subTest(now=now),patch.object(multi,'BASE_DIR',root), \
                     patch.object(multi.aw,'datetime') as clock, \
                     patch.dict(os.environ,{'GEMINI_API_KEY':'offline-test'}), \
                     patch.object(sys,'argv',['multi_delivery.py','--today','--input',str(folder),'--output',str(root)]), \
                     patch.object(multi,'run',return_value=0) as runner:
                    clock.now.side_effect=[now,datetime(2030,1,1)]
                    self.assertEqual(multi.main(),0)
                    args=runner.call_args.args[0]
                    self.assertEqual(args.receipt_date,now.date())
                    self.assertEqual(multi.report_path(args).name,'TongHopPhieuNgay_'+now.strftime('%d-%m-%Y')+'.xlsx')
                    self.assertEqual(clock.now.call_count,1)

    def test_today_batch_runs_from_another_folder_and_manual_batch_stays_available(self):
        source=Path(__file__).resolve().parents[1]
        today_batch=next(source.glob('*Doc_nhieu_phieu_ngay_hom_nay.bat'))
        self.assertTrue((source/'03_Doc_nhieu_phieu_ngay_khac_nhau.bat').is_file())
        self.assertFalse((source/'03_Doc_nhieu_phieu.bat').exists())
        with tempfile.TemporaryDirectory(prefix='Auto BAT ngay hom nay ') as tmp:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            # Empty input exits before reading key/catalog or contacting AI.
            result=subprocess.run(
                [os.environ.get('COMSPEC','cmd.exe'),'/d','/c','call',
                 str(today_batch),
                 '--input',str(folder),'--output',str(root)],
                cwd=root,input=b'\r\n',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
            output=result.stdout.decode('utf-8',errors='replace')
            self.assertEqual(result.returncode,0,output)
            self.assertIn('Ngày nhận tự động: '+datetime.now().strftime('%d/%m/%Y'),output)
            self.assertIn('TongHopPhieuNgay_'+datetime.now().strftime('%d-%m-%Y')+'.xlsx',output)
            self.assertIn('Chưa có ảnh',output)
            self.assertEqual(list(root.glob('*.xlsx')),[])


if __name__=='__main__':unittest.main(verbosity=2)
