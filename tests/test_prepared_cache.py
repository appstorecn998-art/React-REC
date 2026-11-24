"""Shared prepared-cache contracts; synthetic temporary images only, no OCR API."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw
import ocr_quality
import preview_cache
import straightening


class PreparedCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'project' / 'output' / 'straightened'
        self.patch_root = patch.object(preview_cache, 'ROOT', self.cache)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        self.path = self.root / 'source.png'
        image = Image.new('RGB', (180, 300), 'white')
        ImageDraw.Draw(image).rectangle((10, 30, 70, 100), fill='blue')
        image.save(self.path)
        self.original = self.path.read_bytes()

    def unchanged(self):
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_explicit_rotation_hit_and_rotation_variants_reused(self):
        with patch('straightening.straighten', side_effect=lambda im: (im, 'test')) as process:
            first = preview_cache.build(self.path, 90)
            target = self.cache / first['file']
            before = (target.read_bytes(), target.stat().st_mtime_ns)
            self.assertEqual(first, preview_cache.build(self.path, 90))
            self.assertEqual(first, preview_cache.build(self.path))
            second = preview_cache.build(self.path, 0)
            self.assertNotEqual(first['file'], second['file'])
            self.assertEqual(first, preview_cache.build(self.path, 90))
            self.assertEqual(process.call_count, 2)
            self.assertEqual(before, (target.read_bytes(), target.stat().st_mtime_ns))
        self.assertEqual((first['width'], first['height']), (300, 180))
        self.assertEqual(first['image_id'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(target.stem, first['cache_key'])
        self.assertEqual(first['version'], straightening.VERSION)
        self.assertEqual(first['method'], 'test')
        self.assertEqual(preview_cache.saved_rotation(self.path), 90)
        self.unchanged()

    def test_project_move_and_source_mtime_do_not_invalidate_cache(self):
        first = preview_cache.build(self.path, 270)
        original_identity = preview_cache.identity(self.path)
        moved = self.root / 'moved-project'
        shutil.move(str(self.cache.parents[1]), moved)
        new_cache = moved / 'output' / 'straightened'
        new_path = moved / 'renamed.png'
        shutil.copyfile(self.path, new_path)
        os.utime(new_path, ns=(1_000_000_000, 1_000_000_000))
        with patch.object(preview_cache, 'ROOT', new_cache):
            with patch('straightening.straighten', side_effect=AssertionError('cache miss')):
                self.assertEqual(preview_cache.identity(new_path), original_identity)
                self.assertEqual(preview_cache.saved_rotation(new_path), 270)
                self.assertEqual(preview_cache.build(new_path), first)
                self.assertEqual(ocr_quality.prepare(new_path), (new_cache / first['file']).read_bytes())
        self.unchanged()

    def test_changed_content_invalidates_even_with_same_size_and_mtime(self):
        path = self.root / 'fixed-size.bmp'
        Image.new('RGB', (60, 100), 'blue').save(path)
        old_stat = path.stat()
        first = preview_cache.build(path, 90)
        Image.new('RGB', (60, 100), 'red').save(path)
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size, old_stat.st_size)
        second = preview_cache.build(path)
        self.assertNotEqual(first['image_id'], second['image_id'])
        self.assertNotEqual(first['file'], second['file'])
        self.assertEqual(second['rotation'], 0)

    def test_straightening_version_changes_pixels_key_not_reviewed_rotation(self):
        first = preview_cache.build(self.path, 90)
        with patch.object(straightening, 'VERSION', 'test-next-version'):
            second = preview_cache.build(self.path)
        self.assertEqual(first['image_id'], second['image_id'])
        self.assertNotEqual(first['cache_key'], second['cache_key'])
        self.assertEqual(second['rotation'], 90)
        self.assertEqual(second['version'], 'test-next-version')
        self.unchanged()

    def test_preparation_settings_version_invalidates_artifact(self):
        first = preview_cache.build(self.path, 180)
        with patch.object(preview_cache, 'PREPARED_VERSION', 'prepared-test-v2'):
            second = preview_cache.build(self.path)
        self.assertNotEqual(first['file'], second['file'])
        self.assertEqual(second['rotation'], 180)

    def test_legacy_path_orientation_migrates_before_source_is_moved(self):
        self.cache.mkdir(parents=True)
        st = self.path.stat()
        source = f'{self.path.resolve()}:{st.st_size}:{st.st_mtime_ns}'
        legacy = self.cache / (hashlib.sha256(source.encode()).hexdigest() + '.orientation.json')
        legacy.write_text(json.dumps({'rotation': 180}))
        self.assertEqual(preview_cache.saved_rotation(self.path), 180)
        durable = self.cache / (hashlib.sha256(self.original).hexdigest() + '.orientation.json')
        self.assertEqual(json.loads(durable.read_text()), {'rotation': 180})
        moved = self.root / 'moved.png'
        self.path.rename(moved)
        self.assertEqual(preview_cache.saved_rotation(moved), 180)
        self.assertEqual(preview_cache.build(moved)['rotation'], 180)
        preview_cache.build(moved, 0)
        self.assertEqual(preview_cache.saved_rotation(moved), 0)

    def test_legacy_processing_metadata_keeps_review_across_versions(self):
        self.cache.mkdir(parents=True)
        st = self.path.stat()
        source = f'{self.path.resolve()}:{st.st_size}:{st.st_mtime_ns}'
        for version, rotation in [(straightening.VERSION, 0), ('grid-full-frame-v3-paper-padding', 90)]:
            key = hashlib.sha256(f'{version}:{source}'.encode()).hexdigest()
            (self.cache / (key + '.json')).write_text(json.dumps({'rotation': rotation}))
        self.assertEqual(preview_cache.saved_rotation(self.path), 90)
        self.assertEqual(preview_cache.build(self.path)['rotation'], 90)

    def test_legacy_v7_review_survives_a_new_straightening_version(self):
        self.cache.mkdir(parents=True)
        st = self.path.stat()
        source = f'{self.path.resolve()}:{st.st_size}:{st.st_mtime_ns}'
        key = hashlib.sha256(f'paper-boundary-v7-visible-side:{source}'.encode()).hexdigest()
        (self.cache / (key + '.json')).write_text(json.dumps({'rotation': 270}))
        with patch.object(straightening, 'VERSION', 'future-version'):
            self.assertEqual(preview_cache.saved_rotation(self.path), 270)
            self.assertEqual(preview_cache.build(self.path)['rotation'], 270)
        self.unchanged()

    def test_parallel_identical_sources_prepare_once_in_process(self):
        duplicate = self.root / 'duplicate.png'
        duplicate.write_bytes(self.original)
        barrier = threading.Barrier(8)
        def process(image):
            time.sleep(.03)
            return image, 'parallel-test'
        def request(index):
            barrier.wait()
            return preview_cache.build(self.path if index % 2 else duplicate, 90)
        with patch('straightening.straighten', side_effect=process) as straighten:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(request, range(8)))
        straighten.assert_called_once()
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(list(self.cache.glob('*.tmp')), [])
        with Image.open(self.cache / results[0]['file']) as image:
            image.load()
            self.assertEqual(image.size, (300, 180))
        self.unchanged()

    def test_preview_and_enhanced_ocr_use_exact_saved_bytes_without_second_straighten(self):
        with patch('straightening.straighten', side_effect=lambda im: (im, 'shared')) as process:
            prepared = preview_cache.build(self.path, 90)
            preview = preview_cache.resolve_preview(self.path)
            expected = preview.read_bytes()
            for processed in (False, True):
                self.assertEqual(ocr_quality.prepare(self.path, processed=processed), expected)
                self.assertEqual(ocr_quality.prepare(self.path, self.original, processed=processed), expected)
                self.assertEqual(ocr_quality.prepare(self.path, enhanced=False, processed=processed), expected)
            process.assert_called_once()
        with Image.open(io.BytesIO(expected)) as image:
            self.assertEqual(image.size, (prepared['width'], prepared['height']))
        self.unchanged()

    def test_ocr_first_creates_same_preview_artifact(self):
        with patch('straightening.straighten', side_effect=lambda im: (im, 'ocr-first')) as process:
            data = ocr_quality.prepare(self.path)
            self.assertEqual(data, preview_cache.resolve_preview(self.path).read_bytes())
            process.assert_called_once()
        self.unchanged()

    def test_reduced_mode_only_resizes_shared_canonical_pixels(self):
        Image.new('RGB', (4000, 2000), 'blue').save(self.path)
        self.original = self.path.read_bytes()
        with patch('straightening.straighten', side_effect=lambda im: (im, 'canonical')) as process:
            prepared = preview_cache.build(self.path, 90)
            target = self.cache / prepared['file']
            canonical = target.read_bytes()
            reduced = ocr_quality.prepare(self.path, enhanced=False, processed=True)
            self.assertEqual(ocr_quality.prepare(self.path), canonical)
            process.assert_called_once()
        self.assertEqual((prepared['width'], prepared['height']), (1600, 3200))
        with Image.open(io.BytesIO(canonical)) as image:
            expected = image.convert('RGB')
        expected.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        stream = io.BytesIO()
        expected.save(stream, 'JPEG', quality=92)
        self.assertEqual(reduced, stream.getvalue())
        with Image.open(io.BytesIO(reduced)) as image:
            self.assertEqual(image.size, (1200, 2400))
        self.assertEqual(target.read_bytes(), canonical)
        self.unchanged()

    def test_final_prepared_image_is_bounded_after_straightening_expands_it(self):
        with patch('straightening.straighten', return_value=(Image.new('RGB', (3600, 1800), 'red'), 'expanded')):
            result = preview_cache.build(self.path)
        self.assertEqual((result['width'], result['height']), (3200, 1600))
        with Image.open(self.cache / result['file']) as image:
            self.assertEqual(image.size, (3200, 1600))
        self.unchanged()

    def test_exif_transpose_then_reviewed_rotation_matches_ocr(self):
        path = self.root / 'exif.jpg'
        image = Image.new('RGB', (80, 140), 'blue')
        exif = Image.Exif()
        exif[274] = 6
        image.save(path, exif=exif)
        before = path.read_bytes()
        prepared = preview_cache.build(path, 90)
        self.assertEqual((prepared['width'], prepared['height']), (80, 140))
        self.assertEqual(ocr_quality.prepare(path), (self.cache / prepared['file']).read_bytes())
        self.assertEqual(path.read_bytes(), before)

    def test_source_bytes_snapshot_is_honored_without_writing_source(self):
        snapshot = self.root / 'snapshot-only.png'
        prepared = preview_cache.build(snapshot, 0, source_bytes=self.original)
        self.assertEqual(prepared['image_id'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(ocr_quality.prepare(snapshot, self.original), (self.cache / prepared['file']).read_bytes())
        self.assertFalse(snapshot.exists())
        self.unchanged()

    def test_broken_metadata_is_rebuilt(self):
        prepared = preview_cache.build(self.path)
        metadata = self.cache / (prepared['cache_key'] + '.json')
        for value in ('broken', '[]', '{}'):
            with self.subTest(value=value):
                metadata.write_text(value)
                self.assertEqual(preview_cache.build(self.path), prepared)
        self.unchanged()

    def test_failed_image_write_does_not_publish_partial_file(self):
        def fail(image, target, *args, **kwargs):
            Path(target).write_bytes(b'partial jpeg')
            raise OSError('simulated disk failure')
        with patch.object(Image.Image, 'save', new=fail):
            with self.assertRaisesRegex(OSError, 'simulated disk failure'):
                preview_cache.build(self.path, 90)
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assertEqual(preview_cache.build(self.path, 90)['rotation'], 90)
        self.unchanged()

    def test_failed_metadata_write_preserves_previous_complete_variant(self):
        first = preview_cache.build(self.path, 0)
        original = (self.cache / first['file']).read_bytes()
        write = preview_cache._atomic_write
        def fail(destination, callback):
            if destination.name.endswith('-90.json'):
                raise OSError('metadata failure')
            return write(destination, callback)
        with patch.object(preview_cache, '_atomic_write', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'metadata failure'):
                preview_cache.build(self.path, 90)
        self.assertEqual(preview_cache.saved_rotation(self.path), 0)
        self.assertEqual(preview_cache.build(self.path), first)
        self.assertEqual((self.cache / first['file']).read_bytes(), original)
        self.assertEqual(preview_cache.build(self.path, 90)['rotation'], 90)
        self.assertEqual(list(self.cache.glob('*.tmp')), [])
        self.unchanged()

    def test_invalid_rotation_does_not_change_saved_review(self):
        preview_cache.build(self.path, 90)
        with self.assertRaisesRegex(ValueError, 'Invalid page rotation'):
            preview_cache.build(self.path, 45)
        self.assertEqual(preview_cache.saved_rotation(self.path), 90)
        self.unchanged()

    def test_request_records_the_actual_prepared_variant(self):
        aw = SimpleNamespace(receipt_rules_fingerprint=lambda: b'old-rules',
                             prepare_image=None, extract_batch_document=lambda: None,
                             batch_document_cache_path=lambda path: Path('cached.json'),
                             BATCH_DOCUMENT_SCHEMA={'properties': {'items': {'items': {'properties': {}}}}},
                             FULL_NAME_PROMPT='', request_batch_document=lambda *args: {'items': []})
        with patch.dict(sys.modules, {'AutoWatcher': aw}):
            ocr_quality.install(self.root/'unused-report.json', enhanced=False)
            aw.prepare_image(self.path)
            expected = preview_cache.build(self.path)['cache_key']
            self.assertEqual(aw.request_batch_document('dummy')['_rec_prepared_key'], expected)
            self.assertIn('row_box', aw.BATCH_DOCUMENT_SCHEMA['properties']['items']['items']['properties'])

    def test_ocr_fingerprint_changes_with_shared_pixel_versions(self):
        def fingerprint(version, prepared_version):
            aw = SimpleNamespace(receipt_rules_fingerprint=lambda: b'old-rules',
                                 prepare_image=None, extract_batch_document=lambda: None,
                                 batch_document_cache_path=lambda path: Path('cached.json'),
                                 BATCH_DOCUMENT_SCHEMA={'properties': {'items': {'items': {'properties': {}}}}},
                                 FULL_NAME_PROMPT='',request_batch_document=lambda *args: {})
            with patch.dict(sys.modules, {'AutoWatcher': aw}):
                with patch.object(straightening, 'VERSION', version):
                    with patch.object(preview_cache, 'PREPARED_VERSION', prepared_version):
                        ocr_quality.install(self.root / 'unused-report.json', enhanced=False)
                        return aw.receipt_rules_fingerprint()
        original = fingerprint('v1', 'prepared-v1')
        self.assertNotEqual(original, fingerprint('v2', 'prepared-v1'))
        self.assertNotEqual(original, fingerprint('v1', 'prepared-v2'))
        self.assertFalse((self.root / 'unused-report.json').exists())


if __name__ == '__main__':
    unittest.main()
