from pathlib import Path
import hashlib
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import multi_delivery as multi


class FastResumeTests(unittest.TestCase):
    def test_locked_quick_read_falls_back_to_stability_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'copying.jpg';image.write_bytes(b'fixture')
            with patch.object(Path,'read_bytes',side_effect=PermissionError('copying')):
                self.assertIsNone(multi.stable_image_digest(image))

    def test_saved_and_renamed_images_skip_without_wait_or_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'renamed.jpg';image.write_bytes(b'already saved')
            digest=hashlib.sha256(image.read_bytes()).hexdigest()
            with patch.object(multi,'saved_sheets',return_value=set()),patch.object(multi,'saved_image_digests',return_value={digest}),patch.object(multi.aw,'wait_ready',side_effect=AssertionError('No delay')),patch.object(multi.aw,'extract_batch_document',side_effect=AssertionError('No OCR')):
                self.assertEqual(list(multi.invoice_groups([image],root/'report.xlsx',SimpleNamespace(),'unused',{})),[])

    def test_legacy_saved_sheet_still_skips_without_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'old.jpg';image.write_bytes(b'old')
            sheet=multi.aw.sheet_name(multi.image_key(hashlib.sha256(b'old').hexdigest()))
            with patch.object(multi,'saved_sheets',return_value={sheet}),patch.object(multi,'saved_image_digests',return_value=set()),patch.object(multi.aw,'wait_ready',side_effect=AssertionError('No delay')):
                self.assertEqual(list(multi.invoice_groups([image],root/'report.xlsx',SimpleNamespace(),'unused',{})),[])

    def test_new_or_changed_image_waits_before_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'same-name.jpg';image.write_bytes(b'new contents')
            doc=dict(path=str(image),document=dict(document_type='delivery',reference_id='',supplier_name='',items=[dict(item_name='Cá',english_name='',vietnamese_name='',catalog_code='',quantity='1',received_quantity='1',unit_price='10',line_amount='10',unit='kg',specification='',group_id='')],has_total=True))
            with patch.object(multi,'saved_sheets',return_value=set()),patch.object(multi,'saved_image_digests',return_value={hashlib.sha256(b'old contents').hexdigest()}),patch.object(multi.aw,'wait_ready') as wait,patch.object(multi.aw,'extract_batch_document',return_value=doc) as ocr:
                self.assertEqual(len(list(multi.invoice_groups([image],root/'report.xlsx',SimpleNamespace(),'unused',{}))),1)
                wait.assert_called_once_with(image);ocr.assert_called_once()

    def test_file_changing_during_hash_waits_and_still_unstable_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'copying.jpg';image.write_bytes(b'fixture')
            with patch.object(multi,'saved_sheets',return_value=set()),patch.object(multi,'saved_image_digests',return_value=set()),patch.object(multi,'stable_image_digest',side_effect=[None,None]),patch.object(multi.aw,'wait_ready') as wait,patch.object(multi.aw,'extract_batch_document') as ocr:
                with self.assertRaisesRegex(ValueError,'thay đổi'):list(multi.invoice_groups([image],root/'report.xlsx',SimpleNamespace(),'unused',{}))
                wait.assert_called_once();ocr.assert_not_called()


if __name__=='__main__':unittest.main()
