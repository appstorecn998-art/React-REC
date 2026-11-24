import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QLineEdit,QPlainTextEdit
import test_receiving_qt as qt_tests
APP=qt_tests.APP


class ReleaseUITests(unittest.TestCase):
    def setUp(self):
        self.fixture=qt_tests.DesktopTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.w=self.fixture.window;self.w.inbox_timer.stop();self.w.show();APP.processEvents()

    def test_notice_visible_on_settings_and_status_is_retained(self):
        from rec_fluent_ui import show_settings
        show_settings(self.w);APP.processEvents()
        self.w.statusBar().showMessage('Đã lưu thông báo kiểm thử');APP.processEvents()
        self.assertTrue(self.w.top_notice.isVisible())
        self.assertEqual(self.w.operation_status.text(),'Đã lưu thông báo kiểm thử')
        self.assertIsNotNone(self.w.findChild(QPushButton,'runtimeSetup'))

    def test_setup_masks_key_and_saves_only_to_test_profile_without_network(self):
        from rec_setup import show_setup
        observations=[]
        def act():
            dialog=APP.activeModalWidget()
            if dialog is None:return
            QTimer.singleShot(1000,dialog.reject)
            key=dialog.findChild(QLineEdit,'setupGeminiKey')
            observations.append(key.echoMode()==QLineEdit.Password)
            key.setText('test-only-secret')
            next(button for button in dialog.findChildren(QPushButton) if button.text()=='Lưu khóa Gemini và mã Sheets').click()
            observations.extend([key.text()=='','test-only-secret' not in dialog.findChild(QPlainTextEdit,'setupDiagnostics').toPlainText()])
            dialog.accept()
        QTimer.singleShot(50,act)
        with patch('requests.sessions.Session.request',side_effect=AssertionError('Network forbidden')):show_setup(self.w)
        self.assertEqual(observations,[True,True,True])
        self.assertEqual((self.w.root/'gemini_api_key.txt').read_text(),'test-only-secret')
