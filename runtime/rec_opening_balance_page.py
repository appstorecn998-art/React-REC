"""Explicit pre-start received quantities by PR; never manufactures receipt documents."""
import json,sqlite3
from pathlib import Path
from contextlib import closing
from fractions import Fraction
from PySide6.QtCore import Qt,QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QDateEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QCheckBox,QPushButton,QScrollArea,QFrame
from receiving_units import exact_text
from receiving_service import digest
from rec_approval_evidence import EvidencePanel

def show_for_current(w):
 from receiving_pr_library import identity
 images=w.receipt_references()
 if not images:return w.show_top_notice('Chưa chọn PR','Ghép hoặc chọn PR trước khi nhập lượng nhận trước.',variant='warning')
 return show(w,identity(images,w.pr_library_directory()),True)

def show(w,identity,from_comparison=False):
 if w.busy or not w._leave_pr():return
 import receiving_ledger as ledger
 from receiving_opening_balance import read,scope,save
 from receiving_pr_library import load,images_for
 from receiving_qt import Worker
 directory=w.pr_library_directory();record=load(directory).get(identity)
 if not record:return
 ledger_path=w.ledger_path();oid=ledger.resolve_order(ledger_path,identity)
 try:
  images_for(record)
  source_lines=ledger.order_lines(record['items']);existing=next((lines for key,_,lines in ledger.list_orders(ledger_path) if key==oid),None)
  if existing and scope(existing)!=scope(source_lines):raise ValueError('PR khác nội dung đã ghi sổ. Rà lại PR trước khi nhập lượng nhận trước.')
  from receiving_pr_number_identity import check_new_order
  check_new_order(directory,ledger_path,identity,oid,ledger.list_orders(ledger_path),source_lines)
  lines=existing or source_lines;old=read(ledger_path,oid).get(oid,{})
  from receiving_validation import check as check_receipt
  validation_cache={}
  summary,history=ledger.summary(ledger_path,lambda payload:check_receipt(payload,validation_cache),order_id=oid);expected_receipts=ledger.fingerprint(sorted((r['receipt_id'],r['revision'],int(r['active'])) for r in history if r['order_id']==oid));by_index={int(r['index']):r for r in summary if r['order_id']==oid}
 except (OSError,ValueError) as exc:w.show_top_notice('Chưa mở được lượng nhận trước',str(exc),variant='warning');return
 previous=getattr(w,'opening_balance_page',None)
 if previous is not None:w.main_pages.removeWidget(previous);previous.deleteLater()
 page=QWidget();page.setObjectName('openingBalancePage');w.opening_balance_page=page;outer=QVBoxLayout(page);outer.setContentsMargins(20,20,20,20)
 scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);content=QWidget();v=QVBoxLayout(content);v.setSpacing(14);scroll.setWidget(content);outer.addWidget(scroll,1)
 heading=QLabel('Đã nhận trước khi dùng REC · PR '+str(record.get('number') or 'chưa rõ số'));heading.setStyleSheet('font-size:21px;font-weight:600;');v.addWidget(heading)
 description=QLabel(str(record.get('supplier') or 'Chưa rõ NCC')+' · '+str(record.get('department') or 'Chưa rõ bộ phận')+'\nNhập tổng lượng đã nhận trước mốc bắt đầu. Không nhập lại lượng của các phiếu đã có trong REC.');description.setWordWrap(True);v.addWidget(description)
 row=QHBoxLayout();boundary=QDateEdit();boundary.setCalendarPopup(True);boundary.setDisplayFormat('dd/MM/yyyy');boundary.setObjectName('openingBoundary');boundary.setDate(QDate.fromString(old.get('before','2026-11-03'),'yyyy-MM-dd'));row.addWidget(QLabel('Đã nhận trước ngày'));row.addWidget(boundary);row.addStretch();v.addLayout(row)
 table=QTableWidget(len(lines),6);table.setObjectName('openingQuantities');table.setHorizontalHeaderLabels(['Hàng PR','ĐVT','Lượng đặt','Đã nhận trước (nhập)','Đã ghi trong REC','Còn thiếu sau khai báo']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.verticalHeader().hide();table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setMinimumHeight(230);v.addWidget(table,1)
 received={};unknown_received={int(index) for receipt in history if receipt['active'] for index in receipt.get('uncertain_indices',[])}
 for i,line in enumerate(lines):
  known=by_index.get(i,{});received[i]=Fraction(known.get('recorded_received','0'))-Fraction(known.get('opening_received','0'))
  texts=[line['name'],line['unit'],line['ordered'],old.get('quantities',{}).get(str(i),'0'),exact_text(received[i])+(' · Chưa xác minh' if i in unknown_received else ''),'']
  for col,text in enumerate(texts):
   cell=QTableWidgetItem(str(text));cell.setToolTip('Nhấp đúp để nhập lượng nhận trước, theo ĐVT PR' if col==3 else str(text))
   if col==3:cell.setBackground(QColor('#f0f5ff'));cell.setForeground(QColor('#145bcc'))
   if col!=3:cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
   table.setItem(i,col,cell)
  table.setRowHeight(i,48)
 person=QLineEdit(old.get('person',''));person.setObjectName('openingPerson');person.setPlaceholderText('Người / bộ phận xác nhận lượng đã nhận trước');v.addWidget(QLabel('Người / bộ phận xác nhận'));v.addWidget(person)
 reason=QLineEdit(old.get('reason',''));reason.setObjectName('openingReason');reason.setPlaceholderText('Căn cứ: sổ cũ, phiếu cũ, xác nhận của bộ phận…');v.addWidget(QLabel('Căn cứ lượng đã nhận trước'));v.addWidget(reason)
 proof_old=dict(old)
 if Path(ledger_path).exists():
  with closing(sqlite3.connect(Path(ledger_path).resolve().as_uri()+'?mode=ro',uri=True)) as conn:
   proof_old['attachment_history']=[dict(json.loads(raw),time=stamp) for stamp,raw in conn.execute('SELECT time,after_json FROM audit WHERE receipt_id=? ORDER BY time',('opening:'+oid,))]
 evidence=EvidencePanel(w,proof_old);v.addWidget(evidence)
 consent=QCheckBox('Tôi đã kiểm tra: đây là lượng nhận trước mốc, chưa nằm trong các phiếu đã nhập REC.');consent.setObjectName('openingConsent');v.addWidget(consent)
 help_text=QLabel('Số 0 = không có lượng nhận trước. Lưu lại là thay thế số đầu kỳ, không cộng dồn. Nhập phiếu cũ trùng kỳ sẽ bị chặn để tránh tính hai lần. Nếu phiếu REC chưa xác minh nguồn, chưa kết luận được phần còn thiếu. Ảnh bằng chứng có thể bổ sung; nếu không còn ảnh, phải ghi rõ căn cứ xác nhận thủ công.');help_text.setWordWrap(True);v.addWidget(help_text)
 status=QLabel();status.setObjectName('openingStatus');status.setWordWrap(True);v.addWidget(status)
 footer=QHBoxLayout();back=QPushButton('Về đối chiếu PR' if from_comparison else 'Về thư viện PR');save_button=QPushButton('Lưu lượng đã nhận trước');save_button.setObjectName('saveOpeningBalance');footer.addWidget(back);footer.addStretch();footer.addWidget(save_button);outer.addLayout(footer)
 def refresh(*_):
  valid=True;blocked=table.blockSignals(True)
  for i,line in enumerate(lines):
   try:
    value=ledger.amount(table.item(i,3).text().replace(',','.'))
    if i in unknown_received:table.item(i,5).setText('Chưa xác minh nguồn phiếu');continue
    remaining=Fraction(line['ordered'])-received[i]-value;table.item(i,5).setText(('Nhận dư '+exact_text(-remaining)) if remaining<0 else exact_text(remaining));table.item(i,5).setForeground(QColor('#b45309' if remaining<0 else '#334155'))
   except ValueError:valid=False;table.item(i,5).setText('Nhập số ≥ 0')
  table.blockSignals(blocked);save_button.setEnabled(valid and consent.isChecked() and bool(person.text().strip()) and bool(reason.text().strip()) and not w.busy)
 table.itemChanged.connect(refresh);person.textChanged.connect(refresh);reason.textChanged.connect(refresh);consent.toggled.connect(refresh)
 def apply():
  refresh()
  if not save_button.isEnabled():return
  try:
   refs=evidence.persist();values={str(i):exact_text(ledger.amount(table.item(i,3).text().replace(',','.'))) for i in range(len(lines))};before=boundary.date().toString('yyyy-MM-dd');who=person.text();basis=reason.text()
  except (OSError,ValueError,KeyError) as exc:status.setText(str(exc));return
  def write():
   if w.ledger_path()!=ledger_path or load(directory).get(identity)!=record:raise ValueError('Nguồn PR hoặc thư mục đã đổi. Mở lại trước khi lưu.')
   images_for(record)
   return save(ledger_path,oid,'PR '+str(record.get('number') or '')+' · '+str(record.get('supplier') or ''),lines,values,before,who,basis,refs,old.get('revision',0),expected_receipts,record['images'],dict(index=str((Path(directory)/'index.json').resolve()),identity=identity,items_hash=ledger.fingerprint(record['items'])))
  def ready(revision):
   old['revision']=revision;w._pr_library_cached=None;status.setText('Đã lưu riêng lượng nhận trước và lịch sử. Tổng nhận = lượng này + các phiếu REC. Chưa tự đồng bộ Sheets.');consent.setChecked(False)
  w.set_busy(True,'Đang lưu lượng nhận trước…');save_button.setEnabled(False);task=Worker(write);task.signals.result.connect(ready);task.signals.error.connect(lambda message:status.setText('Chưa lưu: '+message));task.signals.finished.connect(lambda:(w.set_busy(False),refresh()));w._start_worker(task)
 def leave():
  if w.busy:return
  if from_comparison:w.main_pages.setCurrentWidget(w.receipt_page);w.compare_current_pr()
  else:w.choose_saved_pr()
 save_button.clicked.connect(apply);back.clicked.connect(leave);refresh()
 page.setStyleSheet('QWidget#openingBalancePage {background:white;color:#475569;font-family:"Segoe UI";font-size:13px;} QLineEdit,QDateEdit,QPushButton {min-height:36px;} QHeaderView::section {background:#f1f5f9;border:0;padding:9px;} QPushButton#saveOpeningBalance {background:#6554d9;color:white;border:0;border-radius:7px;padding:0 16px;} QPushButton#saveOpeningBalance:disabled {background:#e4e0f3;color:#9b92b5;}');w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
