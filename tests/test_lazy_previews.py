import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import preview_cache


class LazyPreviewTests(unittest.TestCase):
    def test_registering_pages_does_not_process_images(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'page.png'
            Image.new('RGB', (100, 200), 'white').save(path)
            allowed = {}
            with patch.object(preview_cache, 'build') as build:
                urls = preview_cache.attach_lazy([path], allowed)
            build.assert_not_called()
            self.assertTrue(urls[0].startswith('/api/preview/'))
            self.assertEqual(allowed[urls[0].rsplit('/', 1)[1]], path)

    def test_empty_pages_return_none(self):
        self.assertIsNone(preview_cache.attach_lazy([], {}))

    def test_only_requested_page_is_built_and_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'page.png'
            Image.new('RGB', (100, 200), 'white').save(path)
            original = path.read_bytes()
            with patch.object(preview_cache, 'ROOT', Path(folder) / 'cache'):
                with patch('straightening.straighten', side_effect=lambda im: (im, 'original')) as straighten:
                    first = preview_cache.resolve_preview(path)
                    second = preview_cache.resolve_preview(path)
                self.assertEqual(first, second)
                self.assertTrue(first.is_file())
                self.assertEqual(straighten.call_count, 1)
            self.assertEqual(path.read_bytes(), original)

    def test_bad_preview_falls_back_to_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.png'
            path.write_bytes(b'not an image')
            with patch.object(preview_cache, 'ROOT', Path(folder) / 'cache'):
                self.assertEqual(preview_cache.resolve_preview(path), path)


if __name__ == '__main__':
    unittest.main()
