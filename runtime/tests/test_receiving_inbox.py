from PIL import Image
import sys,tempfile,unittest
from pathlib import Path
from datetime import date
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
from receiving_inbox import Inbox

class InboxTests(unittest.TestCase):
    def test_two_purchase_orders_with_one_pr_stay_out_of_delivery_report(self):
        import os
        from unittest.mock import patch
        import AutoWatcher as aw
        import multi_delivery
        import receiving_app
        from receiving_pr_library import load, title

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            from openpyxl import Workbook
            catalog = Workbook()
            catalog.active.title = 'DanhMucGoc'
            catalog.active.append(['Mã vật tư', 'Tên vật tư', 'Đvt'])
            catalog.active.append(['11120002', 'Gà', 'kg'])
            suppliers = catalog.create_sheet('DanhMucNCC')
            suppliers.append(['Mã nhà cung cấp', 'Tên nhà cung cấp'])
            suppliers.append(['1702130604', 'NCC chuẩn'])
            catalog.save(root/'DanhMuc.xlsm')
            catalog.close()
            first, second = root/'first.jpg', root/'second.jpg'
            Image.new('RGB',(10,10),'black').save(first)
            Image.new('RGB',(10,10),'white').save(second)
            numbers={first:'PO11/26.018',second:'PO11/26.016'}
            def extract(image,*_):
                item={field:'' for field in ('english_name','vietnamese_name','catalog_code','line_amount','specification','group_id')}
                item.update(item_name='Gà',quantity='3',unit='kg',unit_price='90000',received_quantity='3')
                document=dict(document_type='delivery',reference_id=numbers[image],pr_reference_id='PR1126.008',
                              document_date='2026-11-20',supplier_name='NCC',supplier_code='1702130604',
                              department_name='Caya Restaurant',items=[item])
                return {'document':aw.validate_batch_document(document)}

            destination=root/'receipts'
            with patch.object(receiving_app,'BASE',root), patch.object(sys,'argv',['app','--worker','2026-11-23',str(destination)]), patch.dict(os.environ,{'GEMINI_API_KEY':'offline-test'},clear=True), patch('builtins.input'), patch('receiving_service.day_images',return_value=[first,second]), patch.object(aw,'load_catalog_data',return_value=({},{})), patch.object(aw,'extract_batch_document',side_effect=extract), patch.object(multi_delivery,'report_path'), patch.object(multi_delivery,'run') as delivery:
                self.assertEqual(receiving_app.worker(),0)
                delivery.assert_not_called()
            orders=load(destination/'.receiving'/'pr-library')
            self.assertEqual({order['number'] for order in orders.values()},set(numbers.values()))
            for order in orders.values():
                self.assertEqual(order['related_pr_number'],'PR1126.008')
                self.assertEqual(order['supplier'], 'NCC chuẩn')
                self.assertEqual(order['items'][0]['received_quantity'],'')
                self.assertTrue(title(order).startswith(order['number']))
            with patch.object(receiving_app,'BASE',root), patch.object(sys,'argv',['app','--worker','2026-11-24',str(destination)]), patch.dict(os.environ,{'GEMINI_API_KEY':'offline-test'},clear=True), patch('builtins.input'), patch('receiving_service.day_images',return_value=[first,second]), patch.object(aw,'load_catalog_data',return_value=({},{})), patch.object(aw,'extract_batch_document') as ocr, patch.object(multi_delivery,'report_path'), patch.object(multi_delivery,'run') as delivery:
                self.assertEqual(receiving_app.worker(),0)
                ocr.assert_not_called()
                delivery.assert_not_called()

    def test_auto_worker_keeps_pr_out_of_delivery_table(self):
        import os
        from unittest.mock import patch
        import receiving_app, multi_delivery, AutoWatcher
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'photos';source.mkdir()
            (source/'delivery.jpg').write_bytes(b'delivery')
            (source/'pr.jpg').write_bytes(b'pr')
            types_seen=[]
            def extract(image,*args):
                return {'path':str(image),'document':{'document_type':'pr' if image.name=='pr.jpg' else 'delivery'}}
            def run(args,key):
                types_seen.extend(p.name for p in args.input.iterdir())
                return 0
            with patch.object(receiving_app,'BASE',root),patch.object(sys,'argv',['app','--worker','2026-11-07',str(root/'out'),'--auto']),patch.dict(os.environ,{'GEMINI_API_KEY':'offline-test'}),patch('builtins.input'),patch('receiving_service.day_images',return_value=list(source.iterdir())),patch.object(AutoWatcher,'load_catalog_data',return_value=([],[])),patch.object(AutoWatcher,'extract_batch_document',side_effect=extract),patch.object(AutoWatcher,'validate_batch_document'),patch.object(multi_delivery,'saved_image_digests',return_value=set()),patch.object(multi_delivery,'run',side_effect=run),patch.object(multi_delivery,'report_path'):
                self.assertEqual(receiving_app.worker(),0)
            self.assertEqual(types_seen,['delivery.jpg'])
            self.assertTrue(list((root/'out').rglob('pr-documents/*.json')))

    def test_wait_for_complete_batch_deduplicate_and_persist_across_days(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'incoming';source.mkdir()
            a=source/'a.jpg';Image.new('RGB',(12,12),'white').save(a)
            inbox=Inbox(root/'state.json')
            self.assertEqual(inbox.scan(source),[])
            b=source/'b.jpg';Image.new('RGB',(12,12),'black').save(b)
            self.assertEqual(inbox.scan(source),[])
            self.assertEqual(len(inbox.prepare(source,root,date(2026,11,7),root/'reports')),2)
            inbox.finish()
            a.rename(source/'renamed.jpg')
            inbox=Inbox(root/'state.json');inbox.scan(source)
            self.assertEqual(inbox.prepare(source,root,date(2026,11,8),root/'reports'),[])

    def test_failed_batch_retries_and_changed_file_waits_again(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'incoming';source.mkdir()
            a=source/'a.jpg';Image.new('RGB',(12,12),'white').save(a)
            inbox=Inbox(root/'state.json');inbox.scan(source)
            self.assertEqual(len(inbox.prepare(source,root,date(2026,11,7),root/'reports')),1)
            # No finish on processing error: retry even when import already exists.
            self.assertEqual(len(inbox.prepare(source,root,date(2026,11,7),root/'reports')),1)
            Image.new('RGB',(12,12),'black').save(a)
            self.assertEqual(inbox.scan(source),[])
            self.assertEqual(len(inbox.scan(source)),1)
            self.assertFalse(inbox.path.exists())

    def test_duplicate_content_and_missing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inbox=Inbox(root/'state.json')
            with self.assertRaises(ValueError):inbox.scan(root/'missing')
            (root/'a.jpg').write_bytes(b'same');(root/'b.jpg').write_bytes(b'same')
            inbox.scan(root);self.assertEqual(len(inbox.scan(root)),1)

if __name__=='__main__':unittest.main()
