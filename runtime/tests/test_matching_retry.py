"""Lỗi API được dựng offline; không gửi ảnh hoặc ghi báo cáo thật."""
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

import httpx
from google.genai import errors
from google.genai._gaos.lib import compat_errors

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import multi_delivery as multi


def server_error(code=503):
    response=httpx.Response(code,request=httpx.Request('POST','https://example.invalid'))
    return compat_errors.APIStatusError('server error: secret-must-not-appear',response=response,body={})


class MatchingRetryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('socket.socket.connect',side_effect=AssertionError('Offline test')))
        self.sleep=self.stack.enter_context(patch.object(multi.time,'sleep'))

    def test_server_overload_recovers_with_same_rows_supplier_model_and_timeout(self):
        items=[dict(item_name='Cá',quantity='5',received_quantity='0')]
        original=deepcopy(items);result=({'items':[]},[])
        args=SimpleNamespace(timeout=90)
        with patch.object(multi.aw,'resolve_batch_items',side_effect=[server_error(),result]) as resolve, \
             self.assertLogs(level='INFO') as messages:
            self.assertIs(multi.resolve_invoice_items(items,args,'unused',{}, {},{},'NCC test'),result)
        self.assertEqual(resolve.call_count,2)
        self.assertEqual(resolve.call_args_list[0],resolve.call_args_list[1])
        self.assertEqual(items,original)
        self.sleep.assert_called_once_with(15)
        output=' '.join(messages.output)
        self.assertIn('503',output);self.assertIn('2/3',output)
        self.assertNotIn('secret-must-not-appear',output)

    def test_persistent_overload_stops_after_three_attempts_and_keeps_original_error(self):
        error=server_error()
        with patch.object(multi.aw,'resolve_batch_items',side_effect=error) as resolve:
            with self.assertRaisesRegex(RuntimeError,'503 sau 3 lượt') as failure:
                multi.resolve_invoice_items([],SimpleNamespace(timeout=90),'unused',{}, {},{},'')
        self.assertIs(failure.exception.__cause__,error)
        self.assertEqual(resolve.call_count,3)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list],[15,30])

    def test_legacy_genai_server_error_uses_code_instead_of_status_code(self):
        error=errors.ServerError(503,{'error':{'message':'overloaded','status':'UNAVAILABLE'}})
        with patch.object(multi.aw,'resolve_batch_items',side_effect=[error,('ok',[])]) as resolve:
            self.assertEqual(multi.resolve_invoice_items([],SimpleNamespace(timeout=5),'unused',{}, {},{},''),('ok',[]))
        self.assertEqual(resolve.call_count,2)

    def test_server_error_switches_to_fallback_and_keeps_it_for_next_part(self):
        args=SimpleNamespace(timeout=90,matching_fallback_model='fallback-model')
        with patch.object(multi.aw,'resolve_batch_items',side_effect=[server_error(),('ok',[]),('next',[])]) as resolve:
            self.assertEqual(multi.resolve_invoice_items([],args,'unused',{}, {},{},''),('ok',[]))
            self.assertEqual(multi.resolve_invoice_items([],args,'unused',{}, {},{},''),('next',[]))
        self.assertEqual([call.args[1] for call in resolve.call_args_list],[multi.aw.MODEL,'fallback-model','fallback-model'])
        self.assertEqual(args.active_matching_model,'fallback-model')
        self.sleep.assert_called_once_with(15)

    def test_fallback_is_not_used_for_auth_or_data_errors(self):
        args=SimpleNamespace(timeout=90,matching_fallback_model='fallback-model')
        with patch.object(multi.aw,'resolve_batch_items',side_effect=server_error(401)) as resolve:
            with self.assertRaises(compat_errors.APIStatusError):
                multi.resolve_invoice_items([],args,'unused',{}, {},{},'')
        resolve.assert_called_once()
        self.assertFalse(hasattr(args,'active_matching_model'))
        self.sleep.assert_not_called()

    def test_bad_input_auth_and_validation_fail_without_retry(self):
        for error in [*(server_error(code) for code in (400,401,403,404)),
                      ValueError('AI changed row order'),PermissionError('Excel locked')]:
            with self.subTest(error=type(error).__name__,status=getattr(error,'status_code',None)), \
                 patch.object(multi.aw,'resolve_batch_items',side_effect=error) as resolve:
                with self.assertRaises(type(error)) as failure:
                    multi.resolve_invoice_items([],SimpleNamespace(timeout=90),'unused',{}, {},{},'')
                self.assertIs(failure.exception,error)
                resolve.assert_called_once()
        self.sleep.assert_not_called()

    def test_ctrl_c_interrupts_backoff_without_another_request(self):
        self.sleep.side_effect=KeyboardInterrupt
        with patch.object(multi.aw,'resolve_batch_items',side_effect=server_error()) as resolve:
            with self.assertRaises(KeyboardInterrupt):
                multi.resolve_invoice_items([],SimpleNamespace(timeout=90),'unused',{}, {},{},'')
        resolve.assert_called_once()

    def fixture(self,root):
        image=root/'one.jpg';image.write_bytes(b'offline fixture')
        document=dict(document_type='delivery',reference_id='PG1',supplier_name='NCC',delivery_date='2026-11-05',
            items=[dict(item_name='Cá',english_name='',vietnamese_name='',catalog_code='',quantity='1',
                        received_quantity='0',receipt_mark='cross_without_number',unit='kg',unit_price='10',
                        line_amount='10',specification='',group_id='')])
        entries=[dict(path=str(image),document=document,digest=hashlib.sha256(image.read_bytes()).hexdigest())]
        result=dict(extracted=dict(supplier_name='NCC',items=[dict(invoice_name='Cá',group_id='')]),
                    items=[dict(invoice_name='Cá',catalog_code='',confidence=0,needs_review=True,note='',line_id='DE1:1')])
        return entries,result,SimpleNamespace(output=root,timeout=90)

    def test_successful_retry_is_cached_and_next_read_needs_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries,result,args=self.fixture(root)
            with patch.object(multi.aw,'resolve_batch_items',side_effect=[server_error(),(result,[])]) as resolve:
                rows,items=multi.read_invoice(entries,args,'unused',{}, {},{'suppliers':[]})
            self.assertEqual(resolve.call_count,2)
            caches=list(root.glob('.autowatcher-cache/multiple-deliveries/*.json'))
            self.assertEqual(len(caches),1)
            self.assertEqual(json.loads(caches[0].read_text(encoding='utf-8'))['items'][0]['invoice_name'],'Cá')
            with patch.object(multi.aw,'resolve_batch_items',side_effect=AssertionError('Must use matching cache')):
                repeated,_=multi.read_invoice(entries,args,'unused',{}, {},{'suppliers':[]})
            self.assertEqual(repeated,rows)
            self.assertEqual(rows[0][13],0)

    def test_exhausted_retries_never_cache_failed_results_or_change_existing_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries,_,args=self.fixture(root)
            report=root/'TongHopPhieuNgay_05-11-2026.xlsx';report.write_bytes(b'existing report')
            with patch.object(multi.aw,'resolve_batch_items',side_effect=server_error()):
                with self.assertRaises(RuntimeError):
                    multi.read_invoice(entries,args,'unused',{}, {},{'suppliers':[]})
            self.assertEqual(report.read_bytes(),b'existing report')
            self.assertEqual(list(root.glob('.autowatcher-cache/multiple-deliveries/*.json')),[])


if __name__=='__main__':unittest.main(verbosity=2)
