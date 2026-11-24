import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import preview_cache
import row_locations as locations


def row(number, name):
    return {'sourceRow': number, 'Tên hàng trên phiếu (Ảnh)': name}


def box(name, y=.2):
    return dict(text=name, x=.1, y=y, right=.6, bottom=y+.025)


class RowLocationTests(unittest.TestCase):
    def test_exact_name_and_grid_bounds(self):
        pages = [dict(candidates=[box('Fresh green lettuce')], separators=[.18, .24])]
        regions, pending = locations.match_rows([row(2, 'Fresh green lettuce')], pages)
        self.assertEqual(pending, [])
        self.assertEqual(regions[0]['sourceRow'], 2)
        self.assertAlmostEqual(regions[0]['y'], .18)
        self.assertAlmostEqual(regions[0]['height'], .06)

    def test_same_name_on_two_pages_is_pending(self):
        regions, pending = locations.match_rows([row(2, 'Fresh green lettuce')],
                    [dict(candidates=[box('Fresh green lettuce')])] * 2)
        self.assertEqual(regions, [])
        self.assertEqual(pending, [2])

    def test_two_rows_cannot_claim_one_region(self):
        regions, pending = locations.match_rows([row(2, 'Fresh green lettuce'), row(3, 'Fresh green lettuce')],
                    [dict(candidates=[box('Fresh green lettuce')])])
        self.assertEqual(regions, [])
        self.assertEqual(pending, [2, 3])

    def test_unmatched_name_is_not_assigned_by_row_number(self):
        regions, pending = locations.match_rows([row(2, 'Fresh green lettuce')],
                    [dict(candidates=[box('Olive oil')])])
        self.assertEqual(regions, [])
        self.assertEqual(pending, [2])

    def test_no_local_reader_returns_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.png'
            Image.new('RGB', (300, 400), 'white').save(path)
            with patch.object(preview_cache, 'ROOT', Path(folder)/'cache'), patch.object(locations, 'executable', return_value=None):
                data = locations.locate([path], [row(2, 'Fresh green lettuce')], {})
                self.assertEqual(data['status'], 'unavailable')
                self.assertEqual(data['regions'], [])
                self.assertEqual(data['pending'], [2])

    def test_ocr_boxes_persist_without_local_engine_and_survive_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'original.png'
            Image.new('RGB', (300, 400), 'white').save(source)
            original = source.read_bytes()
            moved = root/'moved.png'
            moved.write_bytes(original)
            document = {'items': [{'item_name': 'Fresh green lettuce', 'row_box': '200,100,250,900'},
                                  {'item_name': 'Bad', 'row_box': '900,100,100,900'}]}
            with patch.object(preview_cache, 'ROOT', root/'cache'), patch.object(locations, 'executable', return_value=None):
                document['_rec_prepared_key'] = preview_cache.build(source)['cache_key']
                locations.record_document(source, document)
                allowed = {}
                data = locations.locate([moved], [row(2, 'Fresh green lettuce')], allowed)
                self.assertEqual(len(data['regions']), 1)
                self.assertEqual(data['pending'], [])
                self.assertTrue(next(iter(allowed.values())).is_file())
                with patch.object(locations, 'match_rows', side_effect=AssertionError('must use saved mapping')):
                    self.assertEqual(data, locations.locate([moved], [row(2, 'Fresh green lettuce')], {}))
            self.assertEqual(source.read_bytes(), original)

    def test_rotation_change_does_not_relabel_ocr_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'original.png'
            Image.new('RGB', (300, 400), 'white').save(source)
            with patch.object(preview_cache, 'ROOT', root/'cache'):
                old = preview_cache.build(source)
                preview_cache.build(source, 90)
                locations.record_document(source, {'_rec_prepared_key': old['cache_key'],
                    'items': [{'item_name': 'Fresh green lettuce', 'row_box': '200,100,250,900'}]})
                self.assertFalse((root/'cache'/'row-locations').exists())

    def test_close_competitor_below_threshold_still_blocks_match(self):
        from difflib import SequenceMatcher
        class Similarity:
            def __init__(self, _, name, text): self.text = text
            def ratio(self): return .857 if self.text == 'candidate one' else .824
        with patch.object(locations, 'SequenceMatcher', Similarity):
            regions, pending = locations.match_rows([row(2, 'Fresh red lettuce')],
                [dict(candidates=[box('candidate one', .2), box('candidate two', .4)])])
        self.assertEqual(regions, [])
        self.assertEqual(pending, [2])

    def test_ocr_boxes_reject_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'original.png'
            Image.new('RGB', (300, 400), 'white').save(source)
            with patch.object(preview_cache, 'ROOT', root/'cache'):
                locations.record_document(source, {'items': [{'item_name': 'Bad', 'row_box': 'NaN,0,100,100'}]})
                self.assertFalse((root/'cache'/'row-locations').exists())


if __name__ == '__main__':
    unittest.main()
