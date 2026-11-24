"""Offline failure simulation; never calls Gemini or touches live reports."""
import sys,tempfile,unittest,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack,nullcontext
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
import ocr_retry as retry
import AutoWatcher as aw
import multi_delivery as md
import receiving_app as app

class ResilienceTests(unittest.TestCase):
    def test_transient_retry_and_source_change_and_no_auth_retry(self):
        with patch.object(retry.time,'sleep') as sleep:
            operation=unittest.mock.Mock(side_effect=[TimeoutError(),SimpleNamespace(ok=True)])
            self.assertTrue(retry.call(operation,'image').ok);self.assertEqual(operation.call_count,2)
            error=RuntimeError();error.status_code=401
            operation=unittest.mock.Mock(side_effect=error)
            with self.assertRaises(RuntimeError):retry.call(operation,'image')
            self.assertEqual(operation.call_count,1)
            with self.assertRaisesRegex(ValueError,'thay đổi'):retry.call(lambda:(_ for _ in ()).throw(TimeoutError()),'image',lambda:False)
    def test_retry_after_and_bounded_attempts(self):
        error=RuntimeError();error.status_code=429;error.response=SimpleNamespace(headers={'Retry-After':'45'})
        operation=unittest.mock.Mock(side_effect=error)
        with patch.object(retry.time,'sleep') as sleep:
            with self.assertRaises(RuntimeError):retry.call(operation,'image')
            self.assertEqual(operation.call_count,3);self.assertEqual([c.args[0] for c in sleep.call_args_list],[45,45])
    def test_gap_never_joins_or_saves_partial_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);images=[];docs={}
            for n in range(5):
                p=root/f'{n}.jpg';p.write_bytes(str(n).encode());images.append(p)
                docs[md.stable_image_digest(p)]={'document_type':'delivery','supplier_name':'S','items':[{'source_stt':'1' if n in (0,4) else '2'}],'has_total':n==4}
            args=SimpleNamespace(preclassified_documents=docs,failed_image_names={'2.jpg'},held_image_names=[])
            with patch.object(md,'saved_sheets',return_value=set()),patch.object(md,'saved_image_digests',return_value=set()),patch.object(aw,'wait_ready'),patch.object(aw,'validate_batch_document'),patch.object(md,'continues_invoice',return_value=True):
                groups=list(md.invoice_groups(images,root/'report',args,'unused',{}))
            self.assertEqual([[Path(e['path']).name for e in group] for group in groups],[['4.jpg']])
            self.assertEqual(args.held_image_names,['0.jpg','1.jpg','3.jpg'])
    def test_worker_reads_remaining_39_of_40_after_one_failure(self):
        import receiving_service as service
        import receiving_image_archive as archive
        import receiving_pr_auto as pr
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);images=[]
            for n in range(40):
                p=root/f'{n:03}.jpg';p.write_bytes(str(n).encode());images.append(p)
            done=[]
            def extract(path,*args):
                done.append(path.name)
                if path==images[7]:raise TimeoutError()
                return {'document':{'document_type':'delivery','items':[{'source_stt':'1'}]}}
            def run(args,key):
                self.assertEqual(len(list(args.input.iterdir())),40)
                self.assertEqual(args.failed_image_names,{images[7].name})
                self.assertEqual(len(args.preclassified_documents),39)
                return 0
            stack.enter_context(patch.dict(os.environ,{'GEMINI_API_KEY':'offline-placeholder'}))
            stack.enter_context(patch.object(sys,'argv',['worker','--worker','2026-11-21',str(root)]))
            stack.enter_context(patch('builtins.input'))
            for obj,name,value in [(service,'paths',(root,root/'report.xlsx')),(service,'day_images',images),(service,'accounting_root',root),(aw,'load_catalog_data',({},{})),(md,'saved_image_digests',set()),(pr,'possible_pr_continuation',False)]:stack.enter_context(patch.object(obj,name,return_value=value))
            stack.enter_context(patch.object(aw,'extract_batch_document',side_effect=extract));stack.enter_context(patch.object(aw,'validate_batch_document'))
            stack.enter_context(patch.object(md,'run',side_effect=run))
            with self.assertRaisesRegex(RuntimeError,'Chưa hoàn tất nhóm'):app.worker()
            self.assertEqual(len(done),40)

if __name__=='__main__':unittest.main()
