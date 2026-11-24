"""Find receipts by saved PR identity, without inferring links from supplier names."""
import json,re,sqlite3
from contextlib import closing
from shiboken6 import isValid
from pathlib import Path
from datetime import date

def collect(ledger_path,destination,identity,record):
 rows={};errors=[];aliases={identity};ledger_path=Path(ledger_path)
 if ledger_path.is_file():
  with closing(sqlite3.connect(ledger_path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as conn:
   if conn.execute("SELECT name FROM sqlite_master WHERE name='order_aliases'").fetchone():
    found=conn.execute('SELECT order_id FROM order_aliases WHERE alias=?',(identity,)).fetchone()
    if found:aliases.add(found[0])
   for oid,raw,active in conn.execute('SELECT order_id,payload,active FROM receipts'):
    if oid not in aliases:continue
    data=json.loads(raw);key=(str(Path(data['report']).resolve()),data['sheet'])
    rows[key]=dict(report=data['report'],sheet=data['sheet'],day=data['day'],status='Đã ghi sổ' if active else 'Lần nhận đã gỡ')
 from receiving_image_archive import image_name
 expected={image_name(k):v for k,v in record.get('source_ids',{}).items()}
 for link in Path(destination).glob('**/manual-pr-links/*.json'):
  if link.name.endswith('.comparison.json') or any('backup' in p.lower() for p in link.parts):continue
  try:
   data=json.loads(link.read_text(encoding='utf-8'))
   related=data.get('library_key') in aliases if data.get('source')=='pr-library' else bool(expected and {image_name(k):v for k,v in data.get('images',{}).items()}==expected)
   if not related:continue
   day_folder=next((p for p in link.parents if re.fullmatch(r'Ngay \d{1,2}',p.name)),None)
   if day_folder is None:continue
   reports=list(day_folder.glob('TongHopPhieuNgay_*.xlsx'))
   if len(reports)!=1:errors.append('Chưa xác định được báo cáo: '+str(day_folder));continue
   report=reports[0];match=re.search(r'(\d{2})-(\d{2})-(\d{4})',report.stem)
   if not match:continue
   stored_day=date(int(match[3]),int(match[2]),int(match[1])).isoformat();key=(str(report.resolve()),data['sheet'])
   rows.setdefault(key,dict(report=str(report),sheet=data['sheet'],day=stored_day,status='Đã ghép PR · chưa xác minh ghi sổ'))
  except (OSError,ValueError,KeyError,TypeError) as exc:errors.append('Chưa đọc được liên kết: '+str(link))
 return sorted(rows.values(),key=lambda r:(r['day'],r['sheet']),reverse=True),errors

def show(w,identity,direct=False):
 from PySide6.QtCore import Qt,QDate
 from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMessageBox
 from receiving_qt import Worker
 from receiving_pr_library import load
 if w.busy or not w._leave_pr():return
 origin=w.main_pages.currentWidget()
 directory=w.pr_library_directory();record=load(directory).get(identity)
 if not record:return
 page=QWidget();page.setObjectName('prReceiptsPage');layout=QVBoxLayout(page);layout.setContentsMargins(24,24,24,24);layout.setSpacing(16)
 title=QLabel('Phiếu giao hàng của PR '+str(record.get('number') or 'chưa rõ số'));title.setStyleSheet('font-size:22px;font-weight:600;');layout.addWidget(title)
 label=QLabel(str(record.get('supplier') or 'Chưa phân loại')+' · '+str(record.get('date') or 'Chưa rõ ngày')+' · '+str(record.get('department') or 'Chưa phân loại'));label.setWordWrap(True);layout.addWidget(label)
 note=QLabel('Đang tìm phiếu đã ghi sổ và phiếu đã ghép với PR này…');note.setWordWrap(True);layout.addWidget(note)
 table=QTableWidget(0,3);table.setObjectName('prRelatedReceipts');table.setHorizontalHeaderLabels(['Ngày lưu / nhận','Phiếu giao hàng','Trạng thái liên kết']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.verticalHeader().hide();table.setWordWrap(True);layout.addWidget(table,1)
 footer=QHBoxLayout();back=QPushButton('Về thư viện PR');open_button=QPushButton('Mở phiếu giao hàng');open_button.setObjectName('openPRRelatedReceipt');open_button.setEnabled(False);footer.addWidget(back);footer.addStretch();footer.addWidget(open_button);layout.addLayout(footer)
 ledger_path=w.ledger_path();destination=w.destination
 def current_context():
  return isValid(page) and isValid(w) and w.ledger_path()==ledger_path and w.destination==destination and w.main_pages.currentWidget() is (origin if direct else page)
 def set_note(message):
  if isValid(note):note.setText(message)
 def failed(message):
  if not current_context():return
  if direct:QMessageBox.warning(w,'Phiếu giao của PR',message)
  else:set_note(message)
 state={'rows':[]};back.clicked.connect(lambda:w.main_pages.setCurrentWidget(w.pr_library_page))
 table.itemSelectionChanged.connect(lambda:open_button.setEnabled(0<=table.currentRow()<len(state['rows'])))
 def ready(result):
  if not isValid(page) or not isValid(w):return
  if w.ledger_path()!=ledger_path or w.destination!=destination:
   set_note('Thư mục dữ liệu đã đổi. Mở lại danh sách phiếu của PR.');return
  rows,errors=result;state['rows']=rows;table.setRowCount(len(rows))
  for i,r in enumerate(rows):
   for col,text in enumerate([date.fromisoformat(r['day']).strftime('%d/%m/%Y'),r['sheet'],r['status']]):
    cell=QTableWidgetItem(text);cell.setToolTip(r['report']);table.setItem(i,col,cell)
   table.setRowHeight(i,56)
  note.setText((str(len(rows))+' phiếu liên kết với PR này.' if rows else 'Chưa tìm thấy phiếu đã ghép với PR này. Dùng Tra cứu phiếu để tìm theo tên hàng hoặc NCC; PR chưa ghép sẽ không có trong danh sách này.')+(' Có nguồn chưa đọc được; kết quả có thể chưa đầy đủ.' if errors else ''));note.setToolTip('\n'.join(errors))
  if rows:
   table.selectRow(0)
   if direct and w.main_pages.currentWidget() is origin:
    if len(rows)==1:open_selected()
    else:
     from PySide6.QtWidgets import QMenu
     from PySide6.QtGui import QCursor
     menu=QMenu(w)
     for index,target in enumerate(rows):
      action=menu.addAction(date.fromisoformat(target['day']).strftime('%d/%m/%Y')+' · '+target['sheet'])
      action.triggered.connect(lambda checked=False,i=index:(table.selectRow(i),open_selected()))
     menu.setAttribute(Qt.WA_DeleteOnClose);menu.popup(QCursor.pos())
  elif direct and w.main_pages.currentWidget() is origin:
   QMessageBox.information(w,'Phiếu giao của PR','Chưa xác minh được đầy đủ liên kết phiếu giao. Hãy kiểm tra lại nguồn dữ liệu.' if errors else 'PR này chưa được ghép với phiếu giao nào.')
 def open_selected():
  i=table.currentRow()
  if not current_context() or w.busy or not 0<=i<len(state['rows']) or not w._leave_pr():return
  target=state['rows'][i]
  from receiving_service import snapshot,day_images,sheet_signature
  def read():
   report=Path(target['report']);digest,data=snapshot(report)
   if target['sheet'] not in dict(data):raise ValueError('Phiếu đã đổi hoặc không còn trong báo cáo. Tìm lại trước khi mở.')
   folder=report.parent/'.receiving';review=folder/'reviewed.json';reviews=json.loads(review.read_text(encoding='utf-8')) if review.exists() else {}
   return folder,report,digest,data,day_images(report.parent),{n:sheet_signature(n,rows) for n,rows in data},reviews
  def opened(payload):
   if not isValid(page) or not isValid(w) or w.main_pages.currentWidget() is not (origin if direct else page):return
   if w.ledger_path()!=ledger_path or w.destination!=destination:return
   w.day=date.fromisoformat(target['day']);blocked=w.date_edit.blockSignals(True);w.date_edit.setDate(QDate(w.day.year,w.day.month,w.day.day));w.date_edit.blockSignals(blocked)
   w.receipt_search.clear();w._day_loaded(payload);w.select_sheet(target['sheet']);w.main_pages.setCurrentWidget(w.receipt_page)
   blocked=w.fluent_nav.blockSignals(True);w.fluent_nav.set_current('Kiểm tra phiếu');w.fluent_nav.blockSignals(blocked)
  w.set_busy(True,'Đang mở phiếu giao hàng của PR…');task=Worker(read);task.signals.result.connect(opened);task.signals.error.connect(lambda message:failed('Chưa mở được phiếu: '+message));task.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(task)
 open_button.clicked.connect(open_selected);table.cellDoubleClicked.connect(lambda *_:open_selected())
 page.setStyleSheet('QWidget#prReceiptsPage {background:white;color:#475569;font-family:"Segoe UI";font-size:13px;} QTableWidget {border:1px solid #e2e8f0;} QHeaderView::section {background:#f1f5f9;border:0;padding:12px;} QPushButton {min-height:36px;border:1px solid #ddd7ef;border-radius:7px;padding:0 16px;} QPushButton#openPRRelatedReceipt {background:#6554d9;color:white;}')
 old=getattr(w,'pr_related_receipts_page',None)
 if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
 w.pr_related_receipts_page=page;w.main_pages.addWidget(page)
 if not direct:w.main_pages.setCurrentWidget(page)
 task=Worker(collect,ledger_path,destination,identity,record);task.signals.result.connect(ready);task.signals.error.connect(lambda message:failed('Chưa tìm được phiếu: '+message));w._start_worker(task)
 return page
