import io,json,unittest
from unittest.mock import patch
import ocr_test_server as app

class PlaygroundTests(unittest.TestCase):
    def test_eta_decreases_and_completed_duration_stays_fixed(self):
        job={'status':'running','startedAt':100,'estimate':{'seconds':12,'samples':2}}
        self.assertEqual(app.timing(job,104)['remaining'],8)
        self.assertEqual(app.timing(job,110)['remaining'],2)
        self.assertEqual(app.timing(job,120)['remaining'],0)
        job.update(status='done',newResult={'seconds':8.81})
        self.assertEqual(app.timing(job,1000)['elapsed'],8.8)
        self.assertIsNone(app.timing(job,1000)['remaining'])
    def test_error_diagnostics_redact_secret_and_preserve_status(self):
        error=RuntimeError('Authorization: Bearer hidden-token test-secret')
        error.status_code=429
        with patch.object(app.server.ocr_jobs,'_secrets',return_value=['test-secret']):
            details=app.error_details(error)
        self.assertEqual(details['http_status'],429)
        self.assertNotIn('test-secret',details['message']);self.assertNotIn('hidden-token',details['traceback'])
        self.assertIn('RuntimeError',details['traceback'])
    def handler(self,headers,body=b'{}',path='/api/run'):
        handler=object.__new__(app.Handler)
        handler.headers=headers;handler.rfile=io.BytesIO(body);handler.path=path
        handler.connection=type('Connection',(),{'settimeout':lambda *args:None})()
        handler.send=lambda data,**kw:setattr(handler,'response',(data,kw.get('code',200)))
        handler.send_error=lambda code:setattr(handler,'response',({},code))
        return handler
    def test_untrusted_and_missing_token_cannot_start_paid_request(self):
        for headers in ({'Host':'evil.test:8769'},{'Host':'127.0.0.1:8769'}, {'Host':'127.0.0.1:8769','Origin':'https://evil.test','X-REC-Token':app.TOKEN}):
            h=self.handler(headers);h.do_POST();self.assertEqual(h.response[1],403)
    def test_unknown_image_rejected_before_job(self):
        body=json.dumps({'name':'../../private.jpg'}).encode()
        from email.message import Message
        headers=Message()
        for key,value in {'Host':'127.0.0.1:8769','X-REC-Token':app.TOKEN,'Content-Type':'application/json','Content-Length':str(len(body))}.items():headers[key]=value
        h=self.handler(headers,body);h.do_POST();self.assertEqual(h.response[1],400)
    def test_failure_keeps_benchmark_pair_and_releases_lock(self):
        name=next(iter(app.names));target=app.OUT/(name+'.original.json');before=target.read_bytes()
        app.guard.acquire()
        with patch.object(app.aw,'load_catalog_data',side_effect=RuntimeError('test')):app.run_pair(name)
        self.assertEqual(app.job['status'],'error');self.assertFalse(app.guard.locked())
        self.assertEqual(before,target.read_bytes())
    def test_new_read_records_real_stages_and_writes_only_test_output(self):
        import tempfile
        from pathlib import Path
        import copy
        key=next(iter(app.library));source=app.library[key];before=source.read_bytes()
        fixture=copy.deepcopy(app.result(next(iter(app.names)),'original')['document'])
        previous=copy.deepcopy(app.job)
        try:
            with tempfile.TemporaryDirectory() as td,patch.object(app,'OUT',Path(td)),patch.object(app,'prepare',return_value=source.read_bytes()),patch.object(app.aw,'load_catalog_data',return_value=({},{})),patch.object(app.server.ocr_jobs,'_secrets',return_value=['test-key']),patch.object(app.aw,'request_batch_document',return_value=fixture):
                import time
                app.job.clear();app.job.update(id='offline',name=key,kind='new',status='running',startedAt=time.time(),events=[])
                app.guard.acquire();app.run_new(key)
                self.assertFalse(app.guard.locked());self.assertEqual(app.job['status'],'done',str(app.job.get('events',[])[-1:]))
                self.assertIn('image_ready',[e['stage'] for e in app.job['events']]);self.assertIn('row',[e['stage'] for e in app.job['events']]);self.assertEqual(app.job['events'][-1]['stage'],'done')
                self.assertTrue((Path(td)/'new-tests/offline/result.json').exists())
                self.assertEqual(app.job['newResult']['document'],fixture)
                self.assertEqual(before,source.read_bytes())
        finally:app.job.clear();app.job.update(previous)

if __name__=='__main__':unittest.main()
