import os,sys,unittest
from pathlib import Path
from datetime import date
os.environ['QT_QPA_PLATFORM']='offscreen';stage=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(stage),str(app),str(app/'tests')]
import test_receiving_qt as fixture
from PySide6.QtWidgets import QDateEdit,QPushButton,QWidget
from PySide6.QtCore import QDate
class EmptyDayTests(unittest.TestCase):
 def setUp(self):self.f=fixture.DesktopTests('runTest');self.f.setUp();self.w=self.f.window;self.w.inbox_timer.stop()
 def tearDown(self):self.f.doCleanups()
 def empty(self):
  self.w.day=date(2026,11,14);self.w.date_edit.setDate(QDate(2026,11,14));fixture.pump_until(lambda:not self.w.busy and not self.w._workers);self.assertEqual(self.w.main_pages.currentWidget().objectName(),'emptyReceiptPage');return self.w.main_pages.currentWidget()
 def test_click_selected_day_reveals_receipts(self):
  p=self.empty();p.findChild(QDateEdit,'emptyReceiptDate').setDate(QDate(2026,11,5));p.findChild(QPushButton,'emptyReceiptOpen').click();fixture.pump_until(lambda:not self.w.busy and not self.w._workers);self.assertIs(self.w.main_pages.currentWidget(),self.w.receipt_page);self.assertEqual(len(self.w.data),2);self.assertTrue(self.w.current_sheet)
 def test_same_day_reload_and_empty_day(self):
  p=self.empty();p.findChild(QPushButton,'emptyReceiptOpen').click();fixture.pump_until(lambda:not self.w.busy and not self.w._workers);self.assertEqual(self.w.main_pages.currentWidget().objectName(),'emptyReceiptPage')
 def test_background_success_does_not_steal_other_page(self):
  self.empty();other=QWidget();self.w.main_pages.addWidget(other);self.w.main_pages.setCurrentWidget(other);self.w.day=self.f.day;self.w._day_loaded(self.w._load_day(self.f.day,self.f.destination,self.f.root));self.assertIs(self.w.main_pages.currentWidget(),other)
if __name__=='__main__':unittest.main()
