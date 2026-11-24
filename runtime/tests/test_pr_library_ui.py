import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QListWidget, QDialogButtonBox
from PIL import Image
import test_receiving_qt as fixture
import receiving_pr_library as lib


class LibraryUITests(unittest.TestCase):
    setUp=fixture.DesktopTests.setUp
    close_window=fixture.DesktopTests.close_window

    def test_choose_stored_pr_outside_current_day_and_preserve_receipt(self):
        w=self.window;image=self.root/'old-pr.png';Image.new('RGB',(200,300),'white').save(image)
        items=[dict(item_name='A',unit='kg',quantity='2',pr_reference_id='123',pr_supplier_name='NCC A',pr_document_date='2026-10-05')]
        key=w.remember_pr(items,[image]);image.unlink();before=self.report.read_bytes()
        errors=[]
        def select():
            dialog=fixture.APP.activeModalWidget()
            try:
                listing=dialog.findChild(QListWidget,'savedPRList')
                self.assertEqual(listing.count(),1);self.assertIn('PR 123',listing.item(0).text())
                self.assertIn('NCC A',listing.item(0).text())
                self.assertTrue(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).isEnabled())
                dialog.accept()
            except Exception as exc:errors.append(exc);dialog.reject()
        QTimer.singleShot(100,select)
        self.assertTrue(w.choose_saved_pr())
        if errors:raise errors[0]
        refs=w.receipt_references();self.assertEqual(len(refs),1)
        self.assertNotIn(refs[0],w.images);self.assertEqual(w.stored_pr_items(refs),items)
        with patch.object(w,'show_pr_comparison') as show,patch('PySide6.QtWidgets.QMessageBox.question',side_effect=AssertionError('Must not call Gemini')):
            w.compare_current_pr();show.assert_called_once()
        self.assertEqual(self.report.read_bytes(),before)
        w.move_receipt(1);self.assertEqual(w.receipt_references(),[])
        w.use_library_pr(key);self.assertEqual(w.receipt_references(),refs)
        refs[0].write_bytes(b'changed');self.assertEqual(w.receipt_references(),[])
