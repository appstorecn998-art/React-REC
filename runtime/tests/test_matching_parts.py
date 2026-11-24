"""Giữ đủ dòng/phiếu khi chia request và tiếp tục sau lỗi, không gọi mạng."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import multi_delivery as multi
from test_matching_retry import server_error


def sources(count):
    return [dict(line_id=f'DE1:{i}',item_name='Hàng trùng',quantity='2',received_quantity='0',
                 receipt_mark='cross_without_number',unit_price='10',line_amount='20',
                 english_name='',vietnamese_name='Hàng trùng',unit='kg',group_id='',
                 source_image='one.jpg',source_stt=str(i),delivery_date='2026-11-05',supplier_name='NCC')
            for i in range(1,count+1)]


def result(items):
    # Matching response tries to overwrite quantity; restoring must keep OCR.
    return dict(extracted=dict(supplier_name='NCC',items=[dict(invoice_name=i['item_name'],group_id='') for i in items]),
                items=[dict(line_id=i['line_id'],invoice_name=i['item_name'],catalog_code='',confidence=0,
                            needs_review=True,note='',quantity='999',received_quantity='999') for i in items]),[]


class MatchingPartsTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('socket.socket.connect',side_effect=AssertionError('Offline test')))
        self.stack.enter_context(patch.object(multi.time,'sleep'))

    def test_68_rows_keep_order_duplicates_zeros_and_dates_with_maximum_8_per_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            items=sources(68);before=deepcopy(items);args=SimpleNamespace(output=Path(tmp),timeout=90)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=lambda key,model,rows,*a:result(rows)) as resolver:
                combined=multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC','invoice-1')
            self.assertEqual([len(call.args[2]) for call in resolver.call_args_list],[8]*8+[4])
            self.assertEqual([i['line_id'] for i in combined['items']],[i['line_id'] for i in items])
            self.assertEqual(len(combined['extracted']['items']),68)
            self.assertTrue(all(i['quantity']=='2' and i['received_quantity']=='0' for i in combined['items']))
            self.assertTrue(all(i['delivery_date']=='2026-11-05' for i in combined['items']))
            self.assertEqual(items,before)

    def test_failed_part_resumes_from_validated_cache_without_repeating_completed_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(output=Path(tmp),timeout=90);items=sources(17)
            calls=[]
            def failing(key,model,rows,*a):
                calls.append(rows[0]['line_id'])
                if rows[0]['line_id']=='DE1:9':raise server_error()
                return result(rows)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=failing):
                with self.assertRaises(RuntimeError):
                    multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC','invoice-1')
            self.assertEqual(calls,['DE1:1','DE1:9','DE1:9','DE1:9'])
            self.assertEqual(len(list(Path(tmp).glob('.autowatcher-cache/multiple-delivery-parts/*.json'))),1)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=lambda key,model,rows,*a:result(rows)) as resolver:
                combined=multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC','invoice-1')
            self.assertEqual([call.args[2][0]['line_id'] for call in resolver.call_args_list],['DE1:9','DE1:17'])
            self.assertEqual(len(combined['items']),17)

    def test_resume_keeps_fallback_used_by_completed_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(output=Path(tmp),timeout=90,matching_fallback_model='fallback-model')
            items=sources(9)
            def failing(key,model,rows,*a):
                if model==multi.aw.MODEL or rows[0]['line_id']=='DE1:9':raise server_error()
                return result(rows)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=failing):
                with self.assertRaises(RuntimeError):
                    multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC')
            restarted=SimpleNamespace(output=Path(tmp),timeout=90,matching_fallback_model='fallback-model')
            with patch.object(multi.aw,'resolve_batch_items',side_effect=lambda key,model,rows,*a:result(rows)) as resolver:
                multi.resolve_invoice_parts(items,restarted,'unused',{}, {},{'suppliers':[]},'NCC')
            resolver.assert_called_once()
            self.assertEqual(resolver.call_args.args[1],'fallback-model')

    def test_changed_image_catalog_rules_or_model_cannot_reuse_prior_part_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(output=Path(tmp),timeout=90);items=sources(9)
            def resolve(rows,catalog=None,rules=None,identity='image-1'):
                return multi.resolve_invoice_parts(rows,args,'unused',catalog or {}, {},rules or {'suppliers':[]},'NCC',identity)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=lambda key,model,rows,*a:result(rows)) as resolver:
                resolve(items);self.assertEqual(resolver.call_count,2)
                resolver.reset_mock();resolve(items);resolver.assert_not_called()
                resolve(items,identity='image-2');self.assertEqual(resolver.call_count,2)
                resolver.reset_mock();resolve(items,catalog={'NEW':('Unrelated','kg')});self.assertEqual(resolver.call_count,2)
                resolver.reset_mock();resolve(items,rules={'suppliers':[],'fixture_version':'new'});self.assertEqual(resolver.call_count,2)
                resolver.reset_mock()
                with patch.object(multi.aw,'MODEL','changed-model'):resolve(items)
                self.assertEqual(resolver.call_count,2)

    def test_reordered_identical_names_missing_rows_and_outdated_cache_are_rejected(self):
        for kind in ('order','missing','cache'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                args=SimpleNamespace(output=Path(tmp),timeout=90);items=sources(9)
                def invalid(key,model,rows,*a):
                    payload,plans=result(rows)
                    if kind=='order':payload['items'].reverse()
                    if kind=='missing':payload['items'].pop()
                    return payload,plans
                with patch.object(multi.aw,'resolve_batch_items',side_effect=invalid):
                    if kind!='cache':
                        with self.assertRaises(ValueError):multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC')
                        self.assertEqual(list(Path(tmp).glob('.autowatcher-cache/multiple-delivery-parts/*.json')),[])
                        continue
                    multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC')
                cache=next(Path(tmp).glob('.autowatcher-cache/multiple-delivery-parts/*.json'))
                cached=json.loads(cache.read_text(encoding='utf-8'));cached['items'].pop()
                cache.write_text(json.dumps(cached),encoding='utf-8')
                with patch.object(multi.aw,'resolve_batch_items',side_effect=AssertionError('No API for invalid cache')):
                    with self.assertRaises(ValueError):multi.resolve_invoice_parts(items,args,'unused',{}, {},{'suppliers':[]},'NCC')

    def test_read_invoice_only_writes_whole_cache_after_all_parts_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'one.jpg';image.write_bytes(b'fixture')
            entries=[dict(path=str(image),digest=hashlib.sha256(image.read_bytes()).hexdigest(),document=dict(
                document_type='delivery',reference_id='',supplier_name='NCC',delivery_date='2026-11-05',
                items=[dict(item_name=i['item_name'],english_name='',vietnamese_name='',catalog_code='',
                           quantity='2',received_quantity='0',receipt_mark='cross_without_number',unit_price='10',
                           line_amount='20',unit='kg',specification='',group_id='') for i in sources(9)]))]
            args=SimpleNamespace(output=root,timeout=90)
            def fail_last(key,model,rows,*a):
                if rows[0]['line_id']=='DE1:9':raise server_error()
                return result(rows)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=fail_last):
                with self.assertRaises(RuntimeError):multi.read_invoice(entries,args,'unused',{}, {},{'suppliers':[]})
            self.assertEqual(list(root.glob('.autowatcher-cache/multiple-deliveries/*.json')),[])
            self.assertEqual(list(root.glob('*.xlsx')),[])
            with patch.object(multi.aw,'resolve_batch_items',side_effect=lambda key,model,rows,*a:result(rows)) as resolver:
                rows,items=multi.read_invoice(entries,args,'unused',{}, {},{'suppliers':[]})
            resolver.assert_called_once();self.assertEqual(len(rows),9)
            self.assertEqual(len(list(root.glob('.autowatcher-cache/multiple-deliveries/*.json'))),1)


if __name__=='__main__':unittest.main(verbosity=2)
