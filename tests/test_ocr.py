import base64,copy,hashlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image,ImageDraw
import ocr_quality as quality
from ocr_jobs import Jobs
import server

class PreparationTest(unittest.TestCase):
    def test_complete_page_crop_and_clipped_page_fallback(self):
        image=Image.new('RGB',(900,1200),'#292624');d=ImageDraw.Draw(image)
        d.polygon([(70,80),(820,65),(830,1120),(60,1140)],fill='white')
        for y in range(200,950,50):d.line((130,y,760,y),fill='black',width=2)
        result,warped=quality.safe_page_crop(image)
        self.assertTrue(warped);self.assertLess(result.width,900);self.assertGreater(result.height,1000)
        image=Image.new('RGB',(900,1200),'white')
        result,warped=quality.safe_page_crop(image)
        self.assertFalse(warped);self.assertIs(result,image)
    def test_color_resolution_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'test.png';image=Image.new('RGB',(3300,4200),'white');ImageDraw.Draw(image).rectangle((100,100,1000,400),fill='blue');image.save(path)
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            prepared=Image.open(io.BytesIO(quality.prepare(path)))
            self.assertEqual(max(prepared.size),3200);self.assertEqual(prepared.mode,'RGB')
            pixel=prepared.getpixel((200,200));self.assertGreater(pixel[2],pixel[0]+100)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
    def test_audit_does_not_guess_or_mutate(self):
        doc={'document_type':'delivery','items':[{'source_stt':'1','receipt_mark':'unclear','quantity':'','unit_price':''},{'source_stt':'3','quantity':'2','unit_price':'100'},{'source_stt':'3','quantity':'2','unit_price':'100'}]}
        before=copy.deepcopy(doc);warnings=quality.audit(doc)
        self.assertGreaterEqual(len(warnings),4);self.assertEqual(doc,before)
    def test_written_quantity_requires_unambiguous_row_evidence(self):
        from AutoWatcher import parse_simple_quantity
        from receipt_rules import apply_receipt_rules

        cases = [
            ('cross_without_number', 'quantity', 'other_row', '15', '0', False),
            ('cross_without_number', 'quantity', 'unclear', '0', '', True),
            ('cross_without_number', 'quantity', 'same_row', '0', '', True),
            ('cross_without_number', 'other', 'none', '', '', True),
            ('cross_with_number', 'quantity', 'same_row', '2,5', '2.5', False),
            ('cross_with_number', 'quantity', 'other_row', '2,5', '', True),
            ('written', 'none', 'same_row', '0', '0', False),
            ('written', 'none', 'other_row', '2', '', True),
            ('unmarked', 'none', 'same_row', '2', '', True),
            ('unmarked', 'none', 'none', '', '10', False),
        ]
        for mark, mark_location, number_location, raw, expected, review in cases:
            with self.subTest(mark=mark, number_location=number_location):
                item = dict(receipt_mark=mark, receipt_mark_location=mark_location,
                            receipt_number_location=number_location,
                            received_quantity=raw, quantity='10')
                for _ in range(2):  # Cached results pass through validation again.
                    apply_receipt_rules(item, parse_simple_quantity)
                    self.assertEqual(item['received_quantity'], expected)
                    self.assertEqual(item['receipt_needs_review'], review)

    def test_cache_hits_still_create_review_warnings(self):
        import AutoWatcher as aw
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'quality.json'
            cached={'path':'cached-image.webp','document':{'document_type':'delivery','reference_id':'R1','items':[{'source_stt':'1','receipt_mark':'unclear','quantity':'1','unit_price':'10'}]}}
            with patch.object(aw,'extract_batch_document',return_value=cached),patch.object(aw,'prepare_image'),patch.object(aw,'receipt_rules_fingerprint',return_value=b'original'):
                quality.install(report)
                result=aw.extract_batch_document(None)
                self.assertIs(result,cached)
                self.assertIn('chưa rõ',report.read_text(encoding='utf-8'))

class JobTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.profile=self.root/'profile';self.profile.mkdir()
        self.jobs=Jobs(self.root/'store',self.root/'jobs',profile=self.profile)
        image=Image.new('RGB',(80,100),'white');stream=io.BytesIO();image.save(stream,format='PNG')
        self.file={'name':'IMG_test.png','content':base64.b64encode(stream.getvalue()).decode()}
    def tearDown(self):self.temp.cleanup()
    def test_stage_validation_and_no_external_path(self):
        staged=self.jobs.stage({'day':'2026-11-21','files':[self.file]})
        self.assertEqual(staged['count'],1)
        for name in ['../x.png','C:/x.png','CON.png','x.png.']:
            with self.assertRaises(ValueError):self.jobs.stage({'day':'2026-11-21','files':[dict(self.file,name=name)]})
        with self.assertRaises(ValueError):self.jobs.stage({'day':'2026-11-21','files':[self.file,self.file]})
        with self.assertRaises(Exception):self.jobs.stage({'day':'bad','files':[self.file]})
    def test_worker_reuses_rec_import_selection_and_reports_success(self):
        import receiving_service as service
        from datetime import date
        staged=self.jobs.stage({'day':'2026-11-21','files':[self.file]});upload=self.jobs.uploads[staged['uploadId']]
        image=upload['paths'][0];report=self.root/'report.xlsx';captured={}
        class FakeProcess:
            stdout=['Đang đọc ảnh…\n','ĐÃ LƯU phiếu\n']
            def wait(self):return 0
            def kill(self):pass
        def popen(args,**kwargs):captured.update(args=args,env=kwargs['env']);return FakeProcess()
        self.jobs.current={'id':'testjob','status':'importing','logs':[],'day':'2026-11-21','count':1}
        with patch.object(service,'import_images',return_value=[image]) as imports,patch.object(service,'paths',return_value=(self.root,report)),patch.object(service,'day_images',return_value=[image]),patch('receiving_image_archive.source_digest',return_value=hashlib.sha256(image.read_bytes()).hexdigest()),patch.object(service,'snapshot',side_effect=[('before',[]),('after',[('New',[(2,{'item':'A'})])])]),patch('ocr_jobs.subprocess.Popen',side_effect=popen),patch('ocr_jobs.threading.Thread') as previews,patch('ocr_jobs.threading.Timer'):
            self.jobs._run(upload,'testjob',True)
        self.assertEqual(self.jobs.current['status'],'complete');self.assertEqual(self.jobs.current['newReceipts'],1)
        self.assertEqual(self.jobs.current['preview']['total'],1)
        self.assertEqual(self.jobs.current['preview']['status'],'running')
        previews.return_value.start.assert_called_once()
        with patch('preview_cache.build',return_value={'method':'paper-crop+deskew'}):
            self.jobs._build_previews(self.jobs.current,[image])
        self.assertEqual(self.jobs.current['preview']['status'],'complete')
        self.assertEqual(self.jobs.current['preview']['cropped'],1)
        self.assertIn('--enhanced',captured['args']);self.assertEqual(len(json.loads(captured['env']['REC_SELECTED_IMAGE_HASHES'])),1)
        self.assertNotIn('REC_DEBT_MODE',captured['env']);imports.assert_called_once()
    def test_failure_never_reports_complete_and_redacts_keys(self):
        self.jobs.current={'id':'failure','status':'running','logs':[]}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'private-test-secret'}):
            self.assertNotIn('private-test-secret',self.jobs._redact('failure private-test-secret'))
        with self.assertRaises(ValueError):self.jobs.start({'uploadId':'missing'})

if __name__=='__main__':unittest.main()
