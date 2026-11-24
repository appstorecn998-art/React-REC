import base64,http.client,io,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from PIL import Image
from ocr_jobs import Jobs
import server

class HttpGuardTest(unittest.TestCase):
    def test_upload_requires_same_origin_token_and_only_stages(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);jobs=Jobs(root/'store',root/'jobs',profile=root/'profile')
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
            def request(method,path,body=None,headers=None):
                conn=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
                conn.request(method,path,body,headers or {});response=conn.getresponse();data=response.read();conn.close();return response.status,data
            try:
                with patch.object(server,'ocr_jobs',jobs):
                    status,data=request('GET','/api/ocr/status');token=json.loads(data)['token'];self.assertEqual(status,200)
                    stream=io.BytesIO();Image.new('RGB',(50,80),'white').save(stream,'PNG')
                    body=json.dumps({'day':'2026-11-21','files':[{'name':'receipt.png','content':base64.b64encode(stream.getvalue()).decode()}]})
                    headers={'Content-Type':'application/json'}
                    self.assertEqual(request('POST','/api/ocr/upload',body,headers)[0],403)
                    headers['X-REC-Token']=token;headers['Origin']='https://unrelated.example'
                    self.assertEqual(request('POST','/api/ocr/upload',body,headers)[0],403)
                    headers['Origin']='http://127.0.0.1:8768'
                    self.assertEqual(request('POST','/api/ocr/upload',body,headers)[0],200)
                    self.assertFalse((root/'store').exists());self.assertIsNone(jobs.current)
            finally:httpd.shutdown();httpd.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main()
