import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
import receiving_pr_library as lib
import receiving_ledger as ledger


class LibraryTests(unittest.TestCase):
    def test_same_pr_survives_next_day_and_metadata_does_not_merge_same_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'pr.png';Image.new('RGB',(100,100),'white').save(image)
            items=[dict(item_name='Bia',unit='lon',quantity='10',pr_reference_id='123',pr_supplier_name='NCC A',pr_document_date='2026-10-05')]
            key=lib.register(root/'library',[image],items)
            record=lib.load(root/'library')[key];copies=lib.images_for(record)
            image.unlink()
            self.assertEqual(lib.identity(copies),key)
            lib.update_metadata(root/'library',key,number='123',supplier='NCC A',date='05/10/2026',department='Bếp')
            self.assertIn('05/10/2026',lib.title(lib.load(root/'library')[key]))
            lib.register(root/'library',copies,items)
            self.assertEqual(lib.load(root/'library')[key]['date'],'05/10/2026')
            image=root/'second.png';Image.new('RGB',(100,100),'black').save(image)
            other=lib.register(root/'library',[image],items)
            self.assertNotEqual(key,other);self.assertEqual(len(lib.load(root/'library')),2)
            copies[0].write_bytes(b'changed')
            with self.assertRaises(ValueError):lib.images_for(record)

    def test_two_partial_receipts_become_complete_without_counting_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);images=[];items=[]
            image=root/'pr.png';Image.new('RGB',(100,100),'white').save(image)
            items=[dict(item_name=f'Hang {i}',unit='cai',quantity='1') for i in range(15)]
            key=lib.register(root/'library',[image],items);lines=ledger.order_lines(items)
            path=root/'ledger.sqlite'
            payload=lambda n:dict(day='2026-10-06',allocations={str(i):str(int(i<n)) for i in range(15)})
            ledger.save_receipt(path,key,'PR 123',lines,'day1',payload(10))
            totals,_=ledger.summary(path);card=lib.cards(root/'library',totals)[0]
            self.assertEqual(card['received'],10);self.assertIn('Còn thiếu 5',card['status'])
            second=dict(day='2026-10-07',allocations={str(i):str(int(i>=10)) for i in range(15)})
            ledger.save_receipt(path,key,'PR 123',lines,'day2',second)
            totals,_=ledger.summary(path);card=lib.cards(root/'library',totals)[0]
            self.assertTrue(card['complete']);self.assertEqual(card['received'],15)
            ledger.save_receipt(path,key,'PR 123',lines,'day2',second,1)
            self.assertEqual(lib.cards(root/'library',ledger.summary(path)[0])[0]['received'],15)
            totals[0]['remaining']=None
            self.assertFalse(lib.cards(root/'library',totals)[0]['complete'])

    def test_invalid_registry_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'index.json').write_text('{broken',encoding='utf-8')
            with self.assertRaises(ValueError):lib.update_metadata(root,'missing',number='123')
            self.assertEqual((root/'index.json').read_text(encoding='utf-8'),'{broken')
