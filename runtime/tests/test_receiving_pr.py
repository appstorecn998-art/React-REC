import sys
from pathlib import Path
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
import tempfile
import unittest
from unittest.mock import patch
from receiving_pr import compare, read_pr, request_pr_page

class PRTests(unittest.TestCase):
    def test_timeout_retry_is_bounded_and_reports_vietnamese_error(self):
        import AutoWatcher as aw
        messages=[]
        with patch.object(aw,'request_batch_document',side_effect=[TimeoutError('timed out'),{'document_type':'pr'}]) as api:
            self.assertEqual(request_pr_page(aw,'test',b'x',{},'pr.jpg',messages.append),{'document_type':'pr'})
            self.assertEqual([c.args[-1] for c in api.call_args_list],[90,180])
            self.assertTrue(any('thử lại' in m for m in messages))
        with patch.object(aw,'request_batch_document',side_effect=TimeoutError('timed out')) as api:
            with self.assertRaisesRegex(RuntimeError,'Các trang PR đã đọc'):
                request_pr_page(aw,'test',b'x',{},'pr.jpg',messages.append)
            self.assertEqual(api.call_count,2)
        with patch.object(aw,'request_batch_document',side_effect=ValueError('unauthorized')) as api:
            with self.assertRaisesRegex(RuntimeError,'Kiểm tra kết nối đến dịch vụ đọc ảnh'):
                request_pr_page(aw,'test',b'x',{},'pr.jpg',messages.append)
            self.assertEqual(api.call_count,1)

    def test_partial_success_is_cached_and_next_run_resumes_failed_page(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'a.jpg';b=root/'b.jpg';a.write_bytes(b'a');b.write_bytes(b'b')
            document={'document_type':'pr','reference_id':'PR1','items':[{'item_name':'A'}]}
            with patch('AutoWatcher.load_catalog_data',return_value=({},{})), patch('AutoWatcher.validate_batch_document',side_effect=lambda d:d), patch.dict('os.environ',{'GEMINI_API_KEY':'test'}):
                with patch('AutoWatcher.request_batch_document',side_effect=[document,TimeoutError(),TimeoutError()]):
                    with self.assertRaises(RuntimeError): read_pr(root,root,[a,b])
                self.assertEqual(len(list(root.rglob('*.json'))),1)
                with patch('AutoWatcher.request_batch_document',return_value=document) as api:
                    items=read_pr(root,root,[a,b])
                    self.assertEqual(len(items),2);self.assertEqual(api.call_count,1)
                    self.assertEqual(api.call_args.args[2],b'b')
    def pr(self, **kw):
        return dict(item_name='Cam sành',catalog_code='001',quantity='10',unit_price='15.000',unit='kg',**kw)
    def row(self, **kw):
        d={'Tên hàng trên phiếu (Ảnh)':'Cam sành','Mã vật tư':'001','Đơn vị tính':'kg','Số lượng':8,'Thực nhận':7,'Đơn giá':16000}
        d.update(kw);return d
    def test_price_shortage_zero_and_unknown_are_separate(self):
        r=compare([self.pr()],[(2,self.row())])[0]
        self.assertEqual(r['remaining'],3);self.assertIn('Đơn giá khác nhau',r['status'])
        self.assertEqual(compare([self.pr()],[(2,self.row(**{'Thực nhận':0}))])[0]['remaining'],10)
        r=compare([self.pr()],[(2,self.row(**{'Thực nhận':None}))])[0]
        self.assertIsNone(r['remaining']);self.assertIn('Chưa xác định đủ số lượng',r['status'])
    def test_units_and_duplicate_rows_are_not_guessed(self):
        r=compare([self.pr()],[(2,self.row(**{'Đơn vị tính':'thùng'}))])[0]
        self.assertIsNone(r['remaining']);self.assertIn('Đơn vị khác nhau',r['status'])
        r=compare([self.pr()],[(2,self.row()),(3,self.row())])[0]
        self.assertIsNone(r['row']);self.assertIsNone(r['remaining'])
        r=compare([self.pr()],[(2,self.row()),(3,self.row())],{0:None})[0]
        self.assertEqual(r['remaining'],10);self.assertIn('đã xác định',r['status'])
    def test_manual_match_cannot_hide_code_conflict_or_duplicate_assignment(self):
        r=compare([self.pr()],[(2,self.row(**{'Mã vật tư':'002'}))],{0:2})[0]
        self.assertIn('Khác mã',r['status'])
        r=compare([self.pr(),self.pr()],[(2,self.row())],{0:2,1:2})
        self.assertTrue(all('Trùng ghép' in x['status'] for x in r))
    def test_read_uses_exact_images_cache_and_rejects_wrong_document(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'pr.jpg';image.write_bytes(b'test')
            with patch('AutoWatcher.load_catalog_data',return_value=({},{})), patch('AutoWatcher.request_batch_document',return_value={'document_type':'delivery'}) as api, patch.dict('os.environ',{'GEMINI_API_KEY':'test'}):
                with self.assertRaises(ValueError):read_pr(root,root,[image])
                self.assertEqual(api.call_count,1)
                self.assertFalse(list(root.rglob('*.json')))

if __name__=='__main__':unittest.main()
