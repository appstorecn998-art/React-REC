from pathlib import Path
import sys
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import multi_delivery as multi
import AutoWatcher as aw
import warehouse_directory as wh

RULES=json.loads(Path(multi.__file__).with_name('NhaCungCap.json').read_text(encoding='utf-8-sig'))
DIRECTORY={'1203':('Kho bar Ora','FB'),'1103':('Kho bếp Caya','KC')}


class WrapperRegressionTests(unittest.TestCase):
    def test_real_extractor_cached_and_fresh_branches_feed_multi_reader(self):
        for cached in (False,True):
            with self.subTest(cached=cached), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);image=root/'IMG_4054.JPG';image.write_bytes(b'fixture-image')
                args=SimpleNamespace(output=root,rules=root/'rules.json',timeout=5)
                args.rules.write_text(json.dumps({'suppliers':[]}),encoding='utf-8')
                document=dict(document_type='delivery',reference_id='PG1',supplier_name='NCC',delivery_date='2026-10-30',items=[dict(item_name='Bia Tiger',english_name='',vietnamese_name='',catalog_code='',group_id='',quantity='1',received_quantity='1',unit='lon',unit_price='10',line_amount='10',specification='')])
                cache=aw.batch_document_cache_path(image,image.read_bytes(),args,{},aw.MODEL)
                if cached:
                    cache.parent.mkdir(parents=True);cache.write_text(json.dumps(document),encoding='utf-8')
                resolved=dict(extracted=dict(supplier_name='NCC',items=[dict(invoice_name='Bia Tiger',group_id='')]),items=[dict(invoice_name='Bia Tiger',catalog_code='',confidence=0,needs_review=True,note='',line_id='DE1:1')])
                with patch.object(aw,'wait_ready'),patch.object(aw,'prepare_image',return_value=b'fake'),patch.object(aw,'request_batch_document',return_value=document) as request,patch.object(aw,'resolve_batch_items',return_value=(resolved,[])):
                    rows=multi.read_delivery(image,args,'unused',{}, {},{'suppliers':[]},multi.hashlib.sha256(image.read_bytes()).hexdigest())
                    self.assertEqual(rows[0][0],'Bia Tiger')
                    self.assertEqual(rows[0][12],1)
                    self.assertEqual(request.call_count,0 if cached else 1)

    def test_alcohol_goes_to_bar_without_pr_or_even_with_kitchen_requester(self):
        names=['Bia Tiger','Heineken beer','Rượu vang đỏ','Vodka Absolut','Whisky Johnnie Walker']
        records=[dict(line_id=i,invoice_name=name,supplier_name='Any NCC',requester_name='Cam Van Phu',pr_status='ĐÃ GHÉP PR') for i,name in enumerate(names,1)]
        records.append(dict(line_id=6,invoice_name='Rượu vang trắng',supplier_name='Other NCC'))
        with tempfile.TemporaryDirectory() as tmp,patch.object(wh,'request_choices',side_effect=AssertionError('No API')):
            results=wh.classify_records(records,DIRECTORY,'unused','model',5,tmp,RULES)
        self.assertTrue(all(r[:3]==('1203','Kho bar Ora','FB') for r in results))

    def test_brand_only_alcohol_category_and_non_alcohol_exclusions(self):
        records=[dict(line_id=1,invoice_name='Chivas Regal 18')]
        with tempfile.TemporaryDirectory() as tmp,patch.object(wh,'request_choices',return_value={'items':[dict(line_id=1,category='bar_alcohol',note='Rượu uống')]}):
            self.assertEqual(wh.classify_records(records,DIRECTORY,'unused','model',5,tmp,RULES)[0][:3],('1203','Kho bar Ora','FB'))
        for name in ['Ly bia','Rượu nấu ăn','Bia mộ','Kem vani','Nước ngọt Coca Cola']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp,patch.object(wh,'request_choices',return_value={'items':[dict(line_id=1,category='unknown',note='Cần rà')]}):
                result=wh.classify_records([dict(line_id=1,invoice_name=name,supplier_name='NCC')],DIRECTORY,'unused','model',5,tmp,RULES)
                self.assertNotEqual(result[0][0],'1203')

if __name__=='__main__':unittest.main(verbosity=2)
