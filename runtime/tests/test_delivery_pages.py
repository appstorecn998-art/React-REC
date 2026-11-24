import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import AutoWatcher as aw
import multi_delivery as multi
from delivery_pages import continues_invoice, sequence_warnings


def document(first=1,last=2,**metadata):
    return dict(document_type='delivery',reference_id='PG1',supplier_name='NCC',delivery_date='',
                **metadata,items=[dict(source_stt=str(n),item_name=f'Hàng {n}',english_name='',
                vietnamese_name='',catalog_code='',quantity='2',received_quantity='2',
                receipt_mark='unmarked',unit_price='10',line_amount='20',unit='kg',
                specification='',group_id='') for n in range(first,last+1)])


class DeliveryPagesTests(unittest.TestCase):
    def test_run_saves_three_photos_as_one_sheet_asks_date_once_and_exports_one_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            docs=[document(1,40),document(41,80),document(81,100,has_total=True),document(1,2,has_total=True)]
            for i in range(4):(folder/f'{i}.jpg').write_bytes(str(i).encode())
            args=SimpleNamespace(input=folder,output=root,excel=Path('fixture'),rules=Path('fixture'),timeout=5)
            def extract(path,*args):return dict(path=str(path),document=docs[int(path.stem)])
            with patch.object(aw,'load_catalog_data',return_value=({},{})),patch.object(aw,'read_rules',return_value={'suppliers':[]}),patch.object(multi,'load_warehouse_directory',return_value={}),patch.object(aw,'wait_ready'),patch.object(aw,'extract_batch_document',side_effect=extract) as ocr,patch.object(multi,'enrich_rows',side_effect=lambda rows,*a,**k:rows),patch('builtins.input',side_effect=['29/10/2026','30/10/2026']) as ask:
                self.assertEqual(multi.run(args,'unused'),0)
                self.assertEqual(ask.call_count,2)
                report=root/'TongHopNhieuPhieuGiaoHang.xlsx'
                wb=aw.load_workbook(report)
                self.assertEqual([s.max_row for s in wb],[101,3])
                first=wb.worksheets[0]
                self.assertEqual([first.cell(r,26).value for r in range(2,102)],[str(n) for n in range(1,101)])
                self.assertEqual({first.cell(r,23).value for r in range(2,102)},{'29/10/2026'})
                self.assertEqual(len(multi.saved_image_digests(report)),4)
                wb.close()
                rows=[row for batch in aw.reviewed_delivery_rows(report,{},date_header='Ngày nhận hàng xác nhận') for row in batch]
                self.assertEqual(len(rows),102)
                self.assertEqual(len({row['invoice_key'] for row in rows}),2)
                ocr.reset_mock()
                self.assertEqual(multi.run(args,'unused'),0)
                ocr.assert_not_called()

    def test_three_pages_hundred_items_one_invoice_and_next_starts_at_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            images=[]
            docs=[document(1,40),document(41,80),document(81,100,has_total=True),document(1,5,has_total=True)]
            for i in range(4):
                path=root/f'{i}.jpg';path.write_bytes(str(i).encode());images.append(path)
            args=SimpleNamespace(output=root)
            def extract(path,*args):return dict(path=str(path),document=docs[int(path.stem)])
            with patch.object(aw,'wait_ready'),patch.object(aw,'extract_batch_document',side_effect=extract):
                groups=list(multi.invoice_groups(images,root/'report.xlsx',args,'unused',{}))
            self.assertEqual([len(g) for g in groups],[3,1])
            self.assertEqual(sum(len(e['document']['items']) for e in groups[0]),100)
            self.assertEqual(sequence_warnings(groups[0]),[])

    def test_same_supplier_different_reference_and_reset_are_separate(self):
        a=dict(document=document());b=dict(document=document(3,4))
        b['document']['reference_id']='PG2'
        self.assertFalse(continues_invoice(a,b))
        b['document']['reference_id']='PG1';b['document']['items'][0]['source_stt']='1'
        self.assertFalse(continues_invoice(a,b))

    def test_missing_overlapping_unknown_stt_all_warn_and_keep_rows(self):
        entries=[dict(document=document(1,2)),dict(document=document(4,5)),dict(document=document(5,6))]
        warnings=' '.join(sequence_warnings(entries))
        self.assertIn('khoảng thiếu: 3',warnings)
        self.assertIn('STT lặp: 5',warnings)
        entries[2]['document']['items'][1]['source_stt']=''
        self.assertIn('không đọc được STT',' '.join(sequence_warnings(entries)))
        self.assertEqual(sum(len(e['document']['items']) for e in entries),6)

    def test_failed_next_image_does_not_save_an_unfinished_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);images=[root/'1.jpg',root/'2.jpg']
            for p in images:p.write_bytes(p.name.encode())
            with patch.object(aw,'wait_ready'),patch.object(aw,'extract_batch_document',side_effect=[dict(path=str(images[0]),document=document()),ValueError('network')]):
                gen=multi.invoice_groups(images,root/'report.xlsx',SimpleNamespace(),'unused',{})
                with self.assertRaisesRegex(ValueError,'network'):next(gen)

    def test_service_amount_preserved_without_inventing_qty_price_or_delivery_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'payment.jpg';image.write_bytes(b'payment')
            doc=document(1,1,document_kind='service_payment')
            item=doc['items'][0];item.update(item_name='PHÍ KIỂM NGHIỆM',quantity='',unit='',received_quantity='1',unit_price='',line_amount='3456000')
            entry=dict(path=str(image),document=doc,digest=hashlib.sha256(image.read_bytes()).hexdigest())
            args=SimpleNamespace(output=root,timeout=5)
            # Real resolver with empty catalog cannot invoke matching API.
            rows,items=multi.read_invoice([entry],args,'unused',{}, {},{'suppliers':[]})
            self.assertIsNone(rows[0][12]);self.assertEqual(rows[0][13],'CHƯA RÕ')
            self.assertIsNone(rows[0][14]);self.assertEqual(rows[0][15],3456000)
            self.assertEqual(rows[0][16],'')
            self.assertIn('THANH TOÁN DỊCH VỤ',rows[0][6])
            rows[0][20:22]=['','KHÔNG CÓ PR']
            rows[0].extend(['03/11/2026',image.name,'','1',entry['digest']])
            report=root/'service.xlsx'
            multi.save_one(report,multi.image_key(entry['digest']),rows)
            with self.assertRaisesRegex(ValueError,'chưa rõ số thực nhận'):
                aw.reviewed_delivery_rows(report,{},date_header='Ngày nhận hàng xác nhận')

    def test_saved_group_resumes_without_ocr_and_preserves_user_edits_after_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);images=[];entries=[]
            for n in range(2):
                image=root/f'{n}.jpg';image.write_bytes(str(n).encode());images.append(image)
                entries.append(dict(path=str(image),document=document(1+n*2,2+n*2),digest=hashlib.sha256(image.read_bytes()).hexdigest()))
            report=root/'report.xlsx'
            rows,items=multi.read_invoice(entries,SimpleNamespace(output=root,timeout=5),'unused',{}, {},{'suppliers':[]})
            for row,item in zip(rows,items):
                row[20:22]=['','KHÔNG CÓ PR']
                row.extend(['03/11/2026',item['source_image'],'',item['source_stt'],'; '.join(e['digest'] for e in entries)])
            multi.save_one(report,multi.image_key(entries[0]['digest']),rows)
            workbook=aw.load_workbook(report);workbook.active['G2']='sửa tay';workbook.save(report);workbook.close()
            images[1].rename(root/'renamed.jpg');images[1]=root/'renamed.jpg'
            with patch.object(aw,'wait_ready'),patch.object(aw,'extract_batch_document',side_effect=AssertionError('Already saved')):
                self.assertEqual(list(multi.invoice_groups(images,report,SimpleNamespace(),'unused',{})),[])
            workbook=aw.load_workbook(report);self.assertEqual(workbook.active['G2'].value,'sửa tay');workbook.close()


if __name__=='__main__':unittest.main()
