import os,sys,tempfile,json,sqlite3,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
stage=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(stage),str(app),str(app/'tests')]
import rec_pr_library_layout,rec_selection_focus,rec_receipt_toolbar,rec_ledger_surface,rec_shortage_layout,rec_history_layout,rec_register_layout,rec_complete_orders_layout,rec_directory,rec_numeric_review_page,rec_image_navigation
from test_nav_performance import Window,APP
from PySide6.QtWidgets import QListWidget,QLineEdit,QTableWidget,QTableWidgetItem,QDateEdit,QAbstractItemView
from PySide6.QtCore import Qt,QDate,QCoreApplication,QEvent
from PySide6.QtTest import QTest,QSignalSpy
from PIL import Image
from PySide6.QtGui import QFontDatabase,QFont
for filename in ['segoeui.ttf','seguisb.ttf']:QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+filename)
APP.setFont(QFont('Segoe UI',10))
import receiving_pr_library as library
class StabilityTests(unittest.TestCase):
 def test_pr_mouse_clicks_never_rebuild_table_or_reselect_other_row(self):
  with tempfile.TemporaryDirectory() as td:
   w=Window(Path(td));directory=w.pr_library_directory()
   for i in range(28):
    image=Path(td)/f'pr{i}.png';Image.new('RGB',(80,100),(255-i,255,255)).save(image)
    w.remember_pr([dict(item_name='A',quantity='1',unit='kg',pr_reference_id=str(i+1),pr_supplier_name='NCC'+str(i%3),pr_department='Kitchen')],[image])
   w._show_saved_pr(library.cards(directory,[]),[],directory);p=w.pr_library_page;w.resize(1500,950);w.show()
   for _ in range(8):APP.processEvents()
   table=p.findChild(QTableWidget,'prLibraryTable');listing=p.findChild(QListWidget,'savedPRList');counter=[]
   table.model().rowsRemoved.connect(lambda *_:counter.append('removed'));table.model().rowsInserted.connect(lambda *_:counter.append('inserted'))
   original=[table.item(i,0) for i in range(table.rowCount())]
   for offset in [0,160,450,800,1100,300,0]:
    table.verticalScrollBar().setValue(offset);APP.processEvents()
    row=next((i for i in range(table.rowCount()) if table.item(i,0).text().startswith('PR ') and table.visualItemRect(table.item(i,0)).top()>=0 and table.visualItemRect(table.item(i,0)).bottom()<table.viewport().height()),None)
    if row is None:continue
    expected=table.item(row,0).text().split(' · ')[0][3:];before=table.verticalScrollBar().value()
    for _ in range(4):
     QTest.mouseClick(table.viewport(),Qt.LeftButton,pos=table.visualItemRect(table.item(row,0)).center());APP.processEvents()
     self.assertEqual(p.findChild(QLineEdit,'prMeta_number').text(),expected)
     self.assertEqual(table.currentRow(),row);self.assertEqual(table.verticalScrollBar().value(),before)
   self.assertFalse(counter);self.assertEqual(original,[table.item(i,0) for i in range(table.rowCount())])
   w.close();w.deleteLater();APP.processEvents()
 def test_refresh_keeps_identity_multiselection_and_scroll(self):
  from rec_table_state import begin,end
  t=QTableWidget(100,1);t.setSelectionMode(QAbstractItemView.ExtendedSelection);t.resize(400,300);t.show()
  for i in range(100):t.setItem(i,0,QTableWidgetItem(str(i)))
  t.selectRow(25);t.verticalScrollBar().setValue(20);APP.processEvents();before=t.verticalScrollBar().value();keys=list(range(100));state=begin(t,keys);new=list(reversed(keys));t.setRowCount(100)
  for i,key in enumerate(new):t.setItem(i,0,QTableWidgetItem(str(key)))
  end(t,new,state);self.assertEqual(new[t.currentRow()],25);self.assertEqual(t.verticalScrollBar().value(),before)
  state=begin(t,new);t.setRowCount(0);end(t,[],state);self.assertEqual(t.currentRow(),-1);t.close()
 def test_calendar_style_preserves_value_and_bounds(self):
  from rec_calendar_style import install,style_date
  edit=QDateEdit();edit.setCalendarPopup(True);edit.setDateRange(QDate(2020,1,1),QDate(2030,12,31));edit.setDate(QDate(2026,11,14));spy=QSignalSpy(edit.dateChanged);install(APP);style_date(edit);edit.show()
  for _ in range(5):APP.processEvents()
  self.assertEqual(edit.date(),QDate(2026,11,14));self.assertEqual(edit.maximumDate(),QDate(2030,12,31));self.assertEqual(spy.count(),0)
  calendar=edit.calendarWidget();self.assertGreaterEqual(calendar.minimumWidth(),280);calendar.setSelectedDate(edit.date());calendar.show();APP.processEvents();calendar.grab().save(str(Path(tempfile.gettempdir())/'rec-calendar-test.png'));edit.close()
 def test_directory_filter_keeps_selected_code(self):
  from rec_directory import DirectoryPage
  with tempfile.TemporaryDirectory() as td:
   w=Window(Path(td));jobs=[];w._start_worker=jobs.append;p=DirectoryPage(w)
   jobs[-1].signals.result.emit([('001','A first','kg'),('002','A second','kg')]);p.table.selectRow(1);p.search.setText('A')
   self.assertEqual(p.table.item(p.table.currentRow(),0).text(),'002');self.assertTrue(p.copy.isEnabled())
   p.search.setText('nothing');self.assertEqual(p.table.currentRow(),-1);self.assertFalse(p.copy.isEnabled());p.close();w.close()
 def test_numeric_review_refresh_keeps_source_row(self):
  from test_receiving_qt import DesktopTests
  from rec_numeric_review_page import show
  from PySide6.QtWidgets import QComboBox
  fixture=DesktopTests('runTest');fixture.setUp()
  try:
   w=fixture.window;p=show(w);mode=p.findChild(QComboBox,'numericReviewFilter');mode.setCurrentIndex(1);table=p.findChild(QTableWidget,'numericReviewTable');table.setCurrentCell(1,0);mode.currentIndexChanged.emit(1)
   self.assertEqual(table.currentRow(),1);self.assertEqual(w.table.model().source_row(w.table.currentIndex().row()),3)
  finally:fixture.doCleanups()
 def test_queued_image_arrows_safe_after_destroy(self):
  from rec_image_navigation import PageArrows
  from receiving_qt import PreviewView
  from PySide6.QtWidgets import QComboBox
  from shiboken6 import delete
  view=PreviewView();combo=QComboBox(view);arrows=PageArrows(view,combo);delete(view);arrows.sync()
 def test_related_receipt_button_opens_exact_existing_sheet(self):
  from test_receiving_qt import DesktopTests,pump_until
  from rec_pr_receipts_page import show
  import receiving_ledger as ledger
  fixture=DesktopTests('runTest');fixture.setUp();w=fixture.window
  try:
   image=next(p for p in w.images if p.name=='unlinked.png');items=[dict(item_name='A',quantity='2',unit='kg',pr_reference_id='05',pr_supplier_name='NCC',pr_document_date='2026-11-04')];key=w.remember_pr(items,[image])
   lines=[dict(index=0,name='A',unit='kg',ordered='2',price='100',code='',specification='')]
   payload=dict(allocations={'0':'1'},day='2026-11-05',sheet='FIRST',report=str(fixture.report),signature='test')
   ledger.save_receipt(w.ledger_path(),key,'PR05',lines,'receipt1',payload)
   before=fixture.report.read_bytes();page=show(w,key)
   pump_until(lambda:page.findChild(QTableWidget,'prRelatedReceipts').rowCount()==1)
   from PySide6.QtWidgets import QPushButton
   page.findChild(QPushButton,'openPRRelatedReceipt').click();pump_until(lambda:not w.busy and not w._workers)
   self.assertEqual(w.current_sheet,'FIRST');self.assertEqual(fixture.report.read_bytes(),before)
  finally:fixture.doCleanups()
 def test_related_receipts_exact_identity_and_unrecorded_links(self):
  from rec_pr_receipts_page import collect
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);db=root/'ledger.sqlite'
   with sqlite3.connect(db) as c:
    c.execute('CREATE TABLE order_aliases(alias TEXT,order_id TEXT)');c.execute('CREATE TABLE receipts(order_id TEXT,payload TEXT,active INTEGER)');c.execute('INSERT INTO order_aliases VALUES(?,?)',('selected','order1'))
    for key,name in [('order1','correct'),('other','wrong')]:c.execute('INSERT INTO receipts VALUES(?,?,1)',(key,json.dumps(dict(report=str(root/(name+'.xlsx')),sheet=name,day='2026-11-13'))))
   c.close()
   folder=root/'Thang 11/Ngay 12';links=folder/'.receiving/.receiving/manual-pr-links';links.mkdir(parents=True);(folder/'TongHopPhieuNgay_12-11-2026.xlsx').touch();(links/'link.json').write_text(json.dumps(dict(source='pr-library',library_key='selected',sheet='unrecorded')))
   before=db.read_bytes();rows,errors=collect(db,root,'selected',{});self.assertEqual({r['sheet'] for r in rows},{'correct','unrecorded'});self.assertFalse(errors);self.assertEqual(db.read_bytes(),before)
if __name__=='__main__':unittest.main()
