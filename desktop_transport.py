"""Run the existing REC request handlers in memory, without a socket."""
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import urlsplit
import json


def dispatch(backend, method, path, headers=None, body=b''):
    url = urlsplit(path)
    if url.scheme or url.netloc or not url.path.startswith('/') or method not in ('GET', 'POST'):
        return 403, 'application/json', b'{"error":"Request denied"}'
    if method == 'POST' and not url.path.startswith('/api/'):
        return 403, 'application/json', b'{"error":"Request denied"}'

    class Request(backend.Handler):
        def __init__(self):
            self.path = path
            self.headers = Message()
            for key, value in (headers or {}).items():
                if key.lower() not in ('host', 'origin', 'sec-fetch-site', 'content-length'):
                    self.headers[key] = value
            self.headers['Host'] = 'localhost'
            self.headers['Content-Length'] = str(len(body))
            self.connection = SimpleNamespace(settimeout=lambda _: None)
            self.rfile = BytesIO(body)
            self.result = None

        def reply(self, data, kind, cache, code=200):
            self.result = (code, kind, data)

        def send_error(self, code, message=None, explain=None):
            self.reply(json.dumps({'error': message or 'Yêu cầu không hợp lệ.'}).encode(),
                       'application/json', 'no-store', code)

    request = Request()
    getattr(request, 'do_'+method)()
    return request.result or (500, 'application/json', b'{"error":"No response"}')
