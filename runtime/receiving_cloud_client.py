"""Authenticated REC cloud transport. Password/session live in memory only."""
import hashlib
import json
import time
import threading
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CloudError(ValueError):
    def __init__(self, message, status=0):
        super().__init__(message); self.status = status


class CloudClient:
    def __init__(self, endpoint, allow_local=False):
        endpoint = str(endpoint).strip().rstrip('/')
        url = urlparse(endpoint)
        local = allow_local and url.hostname in ('127.0.0.1', 'localhost')
        if (url.scheme != 'https' and not (local and url.scheme == 'http')) or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise CloudError('Nhập địa chỉ HTTPS của REC Cloud, không kèm đường dẫn hoặc mật khẩu.')
        self.endpoint = endpoint; self.token = None; self.role = None; self.username = None; self.snapshot_id = None
        self.lock = threading.RLock(); self.opener = build_opener(NoRedirect()); self.refresh_at = float("inf")

    def request(self, method, path, payload=None, content=None, mime=None, limit=20*1024*1024):
        with self.lock:
            return self._request(method, path, payload, content, mime, limit)

    def _request(self, method, path, payload=None, content=None, mime=None, limit=20*1024*1024):
        if self.token and path != '/session' and time.monotonic() >= self.refresh_at:
            result = self.request('POST', '/session')
            self.token = result['token']; self.role = result['role']
            self.refresh_at = time.monotonic() + 600
        headers = {'Accept': 'application/json', 'User-Agent': 'REC/0.9 Desktop'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        if payload is not None:
            content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8'); mime = 'application/json'
        if mime:
            headers['Content-Type'] = mime
        request = Request(self.endpoint+path, data=content, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=45) as response:
                body = response.read(limit+1)
                if len(body) > limit:
                    raise CloudError('Dữ liệu cloud vượt giới hạn hỗ trợ.')
                if method == 'HEAD':
                    return True
                return body if response.headers.get_content_type().startswith('image/') else json.loads(body.decode('utf-8'))
        except HTTPError as error:
            body = error.read(4096).decode('utf-8', errors='replace')
            content_type = error.headers.get_content_type()
            error.close()
            if error.code == 403 and content_type != 'application/json':
                raise CloudError('Cloudflare đang chặn kết nối từ REC (403). Đây không phải lỗi quyền tài khoản REC.', 403) from None
            if error.code == 401:
                self.token = None; self.role = None
            if error.code == 503:
                safe_messages = {'Turso từ chối token. Kiểm tra Secret TURSO_TOKEN trên Worker.', 'Địa chỉ Turso không hợp lệ. Kiểm tra Secret TURSO_URL bắt đầu bằng https://.', 'Turso không thực hiện được truy vấn. Kiểm tra schema và database kết nối.', 'Chưa kết nối được dịch vụ Turso. Thử lại sau.'}
                try: message = json.loads(body).get('error')
                except (ValueError, AttributeError): message = None
                if message in safe_messages: raise CloudError(message, 503) from None
                try: code = json.loads(body).get('code', '')
                except (ValueError, AttributeError): code = ''
                if code in {'REC_DB_NETWORK', 'REC_DB_RESPONSE', 'login-rate', 'login-user', 'login-password', 'login-session', 'request'}:
                    raise CloudError('REC Cloud chưa sẵn sàng. Mã kiểm tra: '+code, 503) from None
            messages = {401: 'Phiên đăng nhập hết hạn hoặc thông tin chưa đúng.', 403: 'Tài khoản này không được phép thực hiện thao tác.',
                        404: 'Chưa có dữ liệu hoặc ảnh được chia sẻ.', 409: 'Dữ liệu cloud đã đổi hoặc ảnh chưa đầy đủ. Tải lại rồi thử lại.',
                        413: 'Dữ liệu vượt giới hạn. Chọn khoảng ngày nhỏ hơn.', 429: 'Đăng nhập quá nhiều lần. Đợi một phút rồi thử lại.'}
            raise CloudError(messages.get(error.code, 'REC Cloud chưa sẵn sàng. Thử lại sau.'), error.code) from None
        except (URLError, TimeoutError, OSError):
            raise CloudError('Không kết nối được REC Cloud. Kiểm tra mạng và địa chỉ máy chủ.') from None
        except (UnicodeError, json.JSONDecodeError):
            raise CloudError('Phản hồi REC Cloud không hợp lệ.') from None

    def login(self, username, password):
        result = self.request('POST', '/login', {'username': username, 'password': password})
        self.token = result['token']; self.role = result['role']; self.username = result['username']; self.refresh_at = time.monotonic() + 600
        return result

    def logout(self):
        self.token = None; self.role = None; self.username = None; self.snapshot_id = None

    def state(self):
        return self.request('GET', '/state')

    def dataset(self):
        result = self.request('GET', '/dataset')
        try:
            data = result['dataset']
            if data['schema'] != 1 or not isinstance(data['scope'], dict) or any(not isinstance(data[key], list) for key in ('receipts', 'orders', 'summary', 'warnings')):
                raise ValueError()
            for item in data['receipts']:
                if any(key not in item for key in ('day', 'label', 'pr_numbers', 'posting', 'rows', 'images')) or item['posting'] not in ('verified', 'needs_review', 'not_posted'): raise ValueError()
            for item in data['orders']:
                if not isinstance(item['items'], list) or not isinstance(item['images'], list): raise ValueError()
            self.snapshot_id = result['snapshot']
            if len(self.snapshot_id) != 64 or any(c not in '0123456789abcdef' for c in self.snapshot_id): raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise CloudError('Bản dữ liệu chia sẻ không hợp lệ. Yêu cầu máy chủ công bố lại.') from None
        return result

    def image(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise CloudError('Mã ảnh không hợp lệ.')
        suffix = '?snapshot='+self.snapshot_id if self.snapshot_id else ''
        body = self.request('GET', '/assets/'+key+suffix, limit=16*1024*1024)
        if not isinstance(body, bytes) or hashlib.sha256(body).hexdigest() != key:
            raise CloudError('Ảnh tải về không khớp mã kiểm tra. Tải lại dữ liệu.')
        return body

    def publish(self, dataset, files, expected_revision, progress=lambda message: None, before_commit=lambda: None, known_assets=None):
        if self.role != 'publisher':
            raise CloudError('Tài khoản này chỉ được xem dữ liệu.', 403)
        # The current published snapshot already proves these hashes were uploaded.
        known_assets = known_assets or {}
        candidates = [(key, meta) for key, meta in dataset['assets'].items() if known_assets.get(key) != meta]
        progress(f'Đã có trên cloud {len(dataset["assets"])-len(candidates)} ảnh; cần kiểm tra {len(candidates)} ảnh mới')
        for number, (key, meta) in enumerate(candidates, 1):
            progress(f'Đang kiểm tra ảnh mới {number}/{len(candidates)}')
            try:
                self.request('HEAD', '/assets/'+key)
                continue
            except CloudError as error:
                if error.status != 404:
                    raise
            content = Path(files[key]).read_bytes()
            if len(content) != meta['size'] or hashlib.sha256(content).hexdigest() != key:
                raise CloudError('Ảnh nguồn vừa đổi. Chuẩn bị dữ liệu lại trước khi gửi.')
            progress(f'Đang tải ảnh mới {number}/{len(candidates)}')
            self.request('PUT', '/assets/'+key, content=content, mime=meta['mime'])
        progress('Ảnh đã đủ; đang công bố bản dữ liệu…')
        before_commit()
        # Only this final CAS makes a complete dataset visible to readers.
        return self.request('POST', '/publish', {'expected_revision': expected_revision, 'dataset': dataset})
