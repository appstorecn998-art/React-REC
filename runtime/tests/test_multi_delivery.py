from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from datetime import date
from openpyxl import load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import multi_delivery as multi


def rows():
    return [['Cá','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','','NCC','','','','',1,1,10,10,'2026-10-28','','','']]


class MultiDeliveryTests(unittest.TestCase):
    def test_each_image_is_saved_immediately_with_its_own_receipt_date_and_resume_keeps_edits(self):
        with tempfile.TemporaryDirectory(prefix='nhieu phieu ') as tmp:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            (folder/'one.jpg').write_bytes(b'one');(folder/'two.jpg').write_bytes(b'two')
            args=SimpleNamespace(input=folder,output=root,excel=Path('fixture'),rules=Path('fixture'),timeout=5)
            report=root/'TongHopNhieuPhieuGiaoHang.xlsx'
            def read(path,*unused):
                if path[0]['path']=='two.jpg': self.assertTrue(report.is_file(),'First invoice must be saved before reading second')
                return rows(), [dict(source_image=path[0]["path"],source_stt="1")]
            with patch.object(multi.aw,'load_catalog_data',return_value=({},{})),patch.object(multi.aw,'read_rules',return_value={}),patch.object(multi,'load_warehouse_directory',return_value={}),patch.object(multi.aw,'wait_ready'),patch.object(multi,'enrich_rows',side_effect=lambda rows,*a,**kw:rows),patch.object(multi,'invoice_groups',side_effect=lambda *a:iter([[dict(path='one.jpg',digest=multi.hashlib.sha256(b'one').hexdigest(),document=dict(items=[dict(source_stt='1')]))],[dict(path='two.jpg',digest=multi.hashlib.sha256(b'two').hexdigest(),document=dict(items=[dict(source_stt='1')]))]] if not report.exists() else [])),patch.object(multi,'read_invoice',side_effect=read) as reader,patch('builtins.input',side_effect=['29/10/2026','30/10/2026']):
                self.assertEqual(multi.run(args,'unused'),0);self.assertEqual(reader.call_count,2)
                workbook=load_workbook(report)
                self.assertEqual(len(workbook.sheetnames),2)
                for sheet,received in zip(workbook,['29/10/2026','30/10/2026']):
                    self.assertEqual(sheet['Q2'].value,'2026-10-28')
                    self.assertEqual(sheet['W1'].value,'Ngày nhận hàng xác nhận')
                    self.assertEqual(sheet['W2'].value,received)
                    self.assertIsNone(sheet['R2'].value)
                workbook.active['G2']='Sửa tay';workbook.save(report);workbook.close()
                # Exact same image under a new name is also skipped.
                (folder/'duplicate.jpg').write_bytes(b'one')
                reader.reset_mock()
                with patch('builtins.input',side_effect=AssertionError('Already saved')):
                    self.assertEqual(multi.run(args,'unused'),0)
                reader.assert_not_called()
                workbook=load_workbook(report);self.assertEqual(workbook.active['G2'].value,'Sửa tay');workbook.close()

    def test_invalid_date_retries_and_quit_does_not_choose_a_default(self):
        with patch('builtins.input',side_effect=['31/02/2026','29/10/2026']):
            self.assertEqual(multi.ask_receipt_date(Path('one.jpg')),date(2026,10,29))
        with patch('builtins.input',return_value='Q'):
            self.assertIsNone(multi.ask_receipt_date(Path('one.jpg')))

    def test_save_locked_retry_reuses_existing_rows(self):
        with patch.object(multi.aw,'write_result',side_effect=[PermissionError('locked'),None]) as writer,patch('builtins.input',return_value=''):
            self.assertTrue(multi.save_one(Path('report.xlsx'),Path('image.jpg'),rows()))
            self.assertEqual(writer.call_count,2)
        with patch.object(multi.aw,'write_result',side_effect=PermissionError('locked')),patch('builtins.input',return_value='q'):
            self.assertFalse(multi.save_one(Path('report.xlsx'),Path('image.jpg'),rows()))

    def test_output_lock_prevents_two_writers_and_is_reusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.xlsx'
            with multi.output_lock(report):
                with self.assertRaises(ValueError):
                    with multi.output_lock(report):pass
            with multi.output_lock(report):pass

    def test_pr_image_is_rejected_before_matching_or_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'PR.jpg';image.write_bytes(b'fixture')
            args=SimpleNamespace(output=root,timeout=5)
            with patch.object(multi.aw,'extract_batch_document',return_value={'path':str(image),'document':dict(document_type='pr',reference_id='',supplier_name='',items=[dict(item_name='Cá',english_name='',vietnamese_name='',catalog_code='',quantity='1',received_quantity='1',unit='kg',unit_price='10',line_amount='10',specification='',group_id='')])}),patch.object(multi.aw,'resolve_batch_items') as match:
                with self.assertRaisesRegex(ValueError,'không được nhận diện'):
                    multi.read_delivery(image,args,'unused',{}, {},{},multi.hashlib.sha256(b'fixture').hexdigest())
                match.assert_not_called()

    def test_cached_result_avoids_another_ocr_or_matching_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'one.jpg';image.write_bytes(b'fixture')
            args=SimpleNamespace(output=root,timeout=5)
            document=dict(document_type='delivery',reference_id='',supplier_name='NCC',delivery_date='2026-10-28',items=[dict(item_name='Cá',english_name='',vietnamese_name='',catalog_code='',specification='',group_id='',quantity='1',received_quantity='1',unit='kg',unit_price='10',line_amount='10')])
            resolved=dict(extracted=dict(supplier_name='NCC',items=[dict(invoice_name='Cá',group_id='')]),items=[dict(invoice_name='Cá',catalog_code='',confidence=0,needs_review=True,note='',line_id='DE1:1')])
            digest=multi.hashlib.sha256(b'fixture').hexdigest()
            with patch.object(multi.aw,'extract_batch_document',return_value={'path':str(image),'document':document}) as ocr,patch.object(multi.aw,'resolve_batch_items',return_value=(resolved,[])) as match:
                first=multi.read_delivery(image,args,'unused',{}, {},{'suppliers':[]},digest)
                second=multi.read_delivery(image,args,'unused',{}, {},{'suppliers':[]},digest)
                self.assertEqual(first,second);self.assertEqual(ocr.call_count,2);self.assertEqual(match.call_count,1)

if __name__=='__main__':unittest.main(verbosity=2)
