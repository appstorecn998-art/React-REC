import sys,os,time,tempfile,unittest,threading
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app),str(app/'tests')]
import receiving_pr_library_ui as module
from PySide6.QtWidgets import QApplication,QMainWindow,QStackedWidget,QWidget,QLineEdit
from PySide6.QtCore import QObject,QThreadPool
from PIL import Image
APP=QApplication.instance() or QApplication([])
class Nav(QObject):
 def set_current(self,value):self.current=value
class Window(QMainWindow,module.PRLibraryUI):
 def __init__(self,root):
  super().__init__();self.root=root;self.report=root/'report.xlsx';self.current_sheet='';self.source_hash='';self.data_by_sheet={};self.main_pages=QStackedWidget();self.setCentralWidget(self.main_pages);self.other=QWidget();self.main_pages.addWidget(self.other);self.fluent_nav=Nav();self.jobs=[];self.pool=QThreadPool(self)
 def ledger_path(self):return self.root/'receiving-ledger.sqlite'
 def _leave_pr(self):return True
 def receipt_references(self):return []
 def _start_worker(self,job):self.jobs.append(job);self.pool.start(job)
def pump(condition):
 end=time.monotonic()+8
 while time.monotonic()<end:
  APP.processEvents()
  if condition():return
  time.sleep(.005)
 raise AssertionError('Qt work timeout')
class NavTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.w=Window(self.root)
  image=self.root/'pr.png';Image.new('RGB',(200,300),'white').save(image)
  self.key=self.w.remember_pr([dict(item_name='A',quantity='1',unit='kg',pr_reference_id='1',pr_supplier_name='NCC')],[image])
 def tearDown(self):
  self.w.pool.waitForDone();APP.processEvents();self.w.hide();self.w.deleteLater();APP.processEvents();self.temp.cleanup()
 def test_navigation_async_reuses_page_and_invalidates_image_changes(self):
  release=threading.Event();original=module.load_library_data
  def slow(*args):release.wait(2);return original(*args)
  with patch.object(module,'load_library_data',side_effect=slow) as load:
   start=time.perf_counter();self.w.choose_saved_pr();self.assertLess(time.perf_counter()-start,.1)
   self.assertEqual(self.w.main_pages.currentWidget().objectName(),'prLibraryLoading')
   self.w.main_pages.setCurrentWidget(self.w.other);APP.processEvents();self.assertIs(self.w.main_pages.currentWidget(),self.w.other)
   release.set();pump(lambda:self.w._pr_library_loading is None)
   self.assertIs(self.w.main_pages.currentWidget(),self.w.other)
   self.w.choose_saved_pr();page=self.w.pr_library_page
   search=page.findChild(QLineEdit,'prLibrarySearch');search.setText('NCC')
   self.w.main_pages.setCurrentWidget(self.w.other);start=time.perf_counter();self.w.choose_saved_pr();elapsed=time.perf_counter()-start
   self.assertIs(self.w.pr_library_page,page);self.assertEqual(search.text(),'NCC');self.assertEqual(load.call_count,1);self.assertLess(elapsed,.1)
   print('Nav cached ms',round(elapsed*1000,2))
   import receiving_pr_library as library
   record=library.load(self.w.pr_library_directory())[self.key];Path(next(iter(record['images']))).write_bytes(b'changed')
   self.w.choose_saved_pr();pump(lambda:self.w._pr_library_loading is None);self.assertEqual(load.call_count,2)
 def test_index_change_refreshes_metadata(self):
  self.w.choose_saved_pr();pump(lambda:self.w._pr_library_loading is None)
  previous=self.w.pr_library_page
  module.library.update_metadata(self.w.pr_library_directory(),self.key,number='999')
  self.w.choose_saved_pr();pump(lambda:self.w._pr_library_loading is None)
  self.assertIsNot(self.w.pr_library_page,previous)
  from PySide6.QtWidgets import QListWidget
  listing=self.w.pr_library_page.findChild(QListWidget,'savedPRList');self.assertIn('999',listing.item(0).text())
 def test_context_changes_during_loading_never_show_stale_data(self):
  release=threading.Event();original=module.load_library_data
  def slow(*args):release.wait(2);return original(*args)
  with patch.object(module,'load_library_data',side_effect=slow):
   self.w.choose_saved_pr();self.w.current_sheet='changed';release.set()
   pump(lambda:self.w._pr_library_loading is None)
   self.assertFalse(hasattr(self.w,'pr_library_page'))
   self.assertFalse(hasattr(self.w,'_pr_library_cached'))
  self.w.choose_saved_pr();pump(lambda:self.w._pr_library_loading is None)
  self.assertIs(self.w.main_pages.currentWidget(),self.w.pr_library_page)
 def test_failed_load_can_retry(self):
  with patch.object(module,'load_library_data',side_effect=ValueError('Read failed')):
   self.w.choose_saved_pr();pump(lambda:self.w._pr_library_loading is None)
  self.assertFalse(hasattr(self.w,'_pr_library_cached'))
  self.w.choose_saved_pr();pump(lambda:self.w._pr_library_loading is None)
  self.assertIs(self.w.main_pages.currentWidget(),self.w.pr_library_page)
if __name__=='__main__':unittest.main(verbosity=1)
