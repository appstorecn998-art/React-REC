"""HTTP contract tests with synthetic receipt data, no OCR/cloud dependencies."""
import importlib.util
import io
import json
import sys
import threading
import types
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch


class LocationHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        watcher = types.ModuleType('AutoWatcher')
        watcher.parse_simple_quantity = lambda value: value
        watcher.excel_number = lambda value: value
        jobs = types.ModuleType('ocr_jobs')
        jobs.Jobs = lambda *args: object()
        spec = importlib.util.spec_from_file_location('isolated_rec_server', root/'server.py')
        cls.bridge = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'AutoWatcher': watcher, 'ocr_jobs': jobs}):
            spec.loader.exec_module(cls.bridge)

    def request(self, query, data):
        bridge = self.bridge
        with patch.object(bridge, 'load', return_value=data):
            httpd = bridge.ThreadingHTTPServer(('127.0.0.1', 0), bridge.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
                connection.request('GET', '/api/receipt/locations?' + query)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
                httpd.shutdown()
                httpd.server_close()
                thread.join()

    def test_changed_workbook_is_rejected(self):
        status, _ = self.request('day=2026-11-20&sheet=A&version=old&images=image1',
                                 {'version': 'new', 'receipts': []})
        self.assertEqual(status, 409)

    def test_changed_image_is_rejected(self):
        data = {'version': 'v1', 'receipts': [{'file': 'A', 'imageVersion': 'new'}]}
        status, _ = self.request('day=2026-11-20&sheet=A&version=v1&images=old', data)
        self.assertEqual(status, 409)

    def test_empty_image_receipt_returns_pending_not_fake_regions(self):
        data = {'version': 'v1', 'receipts': [{'file': 'A', 'imageVersion': 'i1', 'pages': [],
                 'rows': [{'sourceRow': 2, 'Tên hàng trên phiếu (Ảnh)': 'Fresh lettuce'}]}]}
        import row_locations
        with patch.object(row_locations.preview_cache, '_atomic_write'):
            status, body = self.request('day=2026-11-20&sheet=A&version=v1&images=i1', data)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['regions'], [])
        self.assertEqual(result['pending'], [2])


if __name__ == '__main__':
    unittest.main()
