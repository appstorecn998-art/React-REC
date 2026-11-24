import os,sys,unittest
from pathlib import Path
from datetime import date
os.environ['QT_QPA_PLATFORM']='offscreen';stage=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(stage),str(app),str(app/'tests')]
import rec_workspace_v2,rec_youtube_navigation,rec_monthly_prices
import test_receiving_qt as fixture
from rec_price_workspace import day_changes,notify_day
from PySide6.QtWidgets import QDateEdit,QPushButton
from PySide6.QtCore import QDate
class WorkspaceTests(unittest.TestCase):
 def setUp(self):self.f=fixture.DesktopTests('runTest');self.f.setUp();self.w=self.f.window;self.w.inbox_timer.stop()
 def tearDown(self):self.f.doCleanups()
 def sample(self):return dict(warnings=[dict(key='001',name='A',unit='kg',entries=[dict(day='2026-11-05',price='120',sheet='FIRST'),dict(day='2026-11-04',price='100',sheet='OLD')])])
 def test_popup_context_and_once_per_change(self):
  w=self.w;w.main_pages.setCurrentWidget(w.receipt_page);notify_day(w,self.sample());self.assertTrue(w._price_warning_popup.isVisible());popup=w._price_warning_popup;popup.accept();notify_day(w,self.sample());self.assertEqual(len(w._price_popup_seen),1)
  self.assertFalse(day_changes(self.sample(),date(2026,11,4)))
 def test_separate_nav_month_and_receipt_band_removed(self):
  w=self.w;self.assertIn('Giá mua',w.fluent_nav.keys());w.ops_navigate('Giá mua');fixture.pump_until(lambda:not w._workers);self.assertEqual(w.main_pages.currentWidget().objectName(),'priceWorkspace');page=w.main_pages.currentWidget();month=page.findChild(QDateEdit,'priceWorkspaceMonth');month.setDate(QDate(2026,10,1));fixture.pump_until(lambda:not w._workers);self.assertEqual(month.displayFormat(),'MM/yyyy');self.assertIsNotNone(page.findChild(QPushButton));self.assertFalse(w.findChild(QPushButton,'monthlyPriceAlerts').isVisible());w.resize(1500,950);w.show();page.grab().save(str(stage/'preview.png'))
if __name__=='__main__':unittest.main()
