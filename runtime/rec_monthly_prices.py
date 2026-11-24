"""Async monthly price warnings integrated with receipt review."""
from PySide6.QtCore import QTimer,Qt,QDate
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QLineEdit
from shiboken6 import isValid

def install(w):
 host=QWidget(w);host.hide();row=QHBoxLayout(host);row.setContentsMargins(0,0,0,0)
 note=QLabel('');note.setWordWrap(True);row.addWidget(note,1);button=QPushButton('Kiểm tra giá trong tháng');button.setObjectName('monthlyPriceAlerts');row.addWidget(button)
 state={'result':None,'context':None,'running':False,'pending':False,'notified':None};timer=QTimer(w);timer.setSingleShot(True);timer.setInterval(350)
 def context():return (str(w.root),str(w.destination),w.day.year,w.day.month)
 def reflect():
  result=state['result'];related=[]
  if result and state['context']==context():related=[r for r in result['warnings'] if any(e['report']==str(w.report) and e['sheet']==w.current_sheet for e in r['entries'])]
  note.setText('Cần rà giá: '+str(len(related))+' mặt hàng trên phiếu cùng NCC đổi giá từ 2 lần trong tháng.' if related else '')
  note.setStyleSheet('color:#9a5a05;background:#fff8eb;padding:8px;border-radius:6px;' if related else '')
  button.setText('Giá tháng · '+str(len(result['warnings']))+' món cần rà' if result and state['context']==context() else 'Kiểm tra giá trong tháng')
 def load(force=False,open_after=False):
  if not isValid(w):return
  if state['running']:state['pending']=True;return
  expected=context();state['running']=True;button.setEnabled(False)
  from receiving_qt import Worker
  from receiving_monthly_prices import scan,stamp
  root=w.root;destination=w.destination;day=w.day;cached=state['result'] if state['context']==expected else None
  def work():
   if not force and cached and cached['stamp']==stamp(root,destination,day):return cached
   return scan(root,destination,day)
  def ready(result):
   if not isValid(w) or not isValid(host) or context()!=expected:return
   state.update(result=result,context=expected);reflect()
   signature=(expected,tuple((r['key'],tuple(r['prices']),r['purchases']) for r in result['warnings']))
   from rec_price_workspace import notify_day
   notify_day(w,result)
   if open_after:show(w,result,lambda:load(True,True))
  def failed(message):
   if isValid(note):note.setText('Chưa kiểm tra đủ giá trong tháng: '+message)
  def finished():
   if not isValid(w) or not isValid(button):return
   state['running']=False;button.setEnabled(True)
   if state['pending']:state['pending']=False;timer.start()
  task=Worker(work);task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished);w._start_worker(task)
 timer.timeout.connect(load);button.clicked.connect(lambda:load(False,True))
 original=w.refresh_table
 def refreshed(*a,**kw):
  result=original(*a,**kw);reflect();timer.start();return result
 w.refresh_table=refreshed;w.monthly_price_refresh=lambda:load(True,True)
 if w.report:timer.start()

def show(w,result,reload,embedded=False):
 old=getattr(w,'monthly_price_page',None)
 if not embedded and old is not None:w.main_pages.removeWidget(old);old.deleteLater()
 page=QWidget();page.setObjectName('monthlyPricePage');
 if not embedded:w.monthly_price_page=page
 v=QVBoxLayout(page);v.setContentsMargins(24,24,24,24);v.setSpacing(14)
 title=QLabel('Giá mua nhiều lần · tháng '+result['month']);title.setStyleSheet('font-size:21px;font-weight:600;');v.addWidget(title)
 if embedded:title.hide()
 guide=QLabel('So sánh đơn giá trên phiếu theo tháng lưu trong REC, cùng nhà cung cấp, cùng mã hàng (hoặc tên gốc khớp hoàn toàn), đơn vị và quy cách; chỉ cảnh báo khi đổi giá từ 2 lần trong tháng. Không tự quy đổi giá, VAT hay chiết khấu. Đây là cảnh báo để rà, không tự đổi giá hoặc chặn ghi sổ.');guide.setWordWrap(True);v.addWidget(guide)
 summary=QLabel(str(len(result['warnings']))+' nhóm hàng/NCC đổi giá từ 2 lần · '+str(result['excluded'])+' dòng không đủ dữ liệu/không có thực nhận để so sánh'+(' · Có báo cáo chưa đọc được, kết quả chưa đầy đủ.' if result['errors'] else ''));summary.setText(summary.text()+(' · Có lỗi thông tin PR; giá vẫn được so sánh.' if result.get('pr_errors') else ''));summary.setWordWrap(True);summary.setToolTip('\n'.join(result['errors']+result.get('pr_errors',[])));v.addWidget(summary)
 table=QTableWidget(0,6);table.setObjectName('monthlyPriceTable');table.setHorizontalHeaderLabels(['Mặt hàng / mã','Ngày lưu','Nhà cung cấp','Đơn giá / ĐVT','Số PR','Chênh thấp → cao']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.verticalHeader().hide();table.setWordWrap(True);v.addWidget(table,1);entries=[]
 for warning in result['warnings']:
  for entry in warning['entries']:
   entries.append(entry);i=table.rowCount();table.insertRow(i)
   from receiving_price_pr import pr_label,format_price
   texts=[entry['name']+'\n'+entry['code'],entry['day'],entry['supplier'],format_price(entry['price'])+' / '+entry['unit'],pr_label(entry),'— (giá thấp là 0)' if warning['increase'] is None else format(__import__('decimal').Decimal(warning['increase']),'.2f')+'%']
   for col,text in enumerate(texts):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,col,cell)
   from PySide6.QtGui import QColor
   money=table.item(i,3);font=money.font();font.setBold(True);font.setPointSize(12);money.setFont(font);money.setForeground(QColor('#334155'))
   pr=table.item(i,4);prfont=pr.font();prfont.setBold(True);prfont.setPointSize(12);pr.setFont(prfont);pr.setForeground(QColor('#334155'))
   table.item(i,4).setToolTip('Bấm đúp để nhập/sửa số PR tham chiếu.\nPR: '+pr_label(entry)+(' (nhập tay — tham chiếu)' if entry.get('manual_pr') else '')+'\nPhiếu nguồn: '+entry['sheet'])
   table.setRowHeight(i,82)
 status=QLabel();status.setWordWrap(True);v.addWidget(status);footer=QHBoxLayout();back=QPushButton('Về kiểm phiếu');refresh=QPushButton('Tải lại');open_=QPushButton('Mở phiếu đã chọn');footer.addWidget(back);footer.addWidget(refresh);footer.addStretch();footer.addWidget(open_);v.addLayout(footer)
 back.clicked.connect(lambda:w.main_pages.setCurrentWidget(w.receipt_page));refresh.clicked.connect(reload);open_.setEnabled(bool(entries))
 if embedded:refresh.hide()
 def open_selected():
  i=table.currentRow()
  if w.busy or not 0<=i<len(entries) or table.isRowHidden(i) or not w._leave_pr():return
  entry=entries[i];from datetime import date
  from receiving_qt import Worker
  day=date.fromisoformat(entry['day']);destination=w.destination;root=w.root
  def read():
   payload=w._load_day(day,destination,root)
   if __import__('pathlib').Path(payload[1]).resolve()!=__import__('pathlib').Path(entry['report']).resolve() or entry['sheet'] not in dict(payload[3]):raise ValueError('Phiếu đã đổi. Tải lại cảnh báo trước khi mở.')
   return payload
  def ready(payload):
   if w.destination!=destination or not isValid(page) or not (w.main_pages.currentWidget() is page or w.main_pages.currentWidget().isAncestorOf(page)):return
   w.day=day;blocked=w.date_edit.blockSignals(True);w.date_edit.setDate(QDate(day.year,day.month,day.day));w.date_edit.blockSignals(blocked);w.receipt_search.clear();w._day_loaded(payload);w.select_sheet(entry['sheet']);w.main_pages.setCurrentWidget(w.receipt_page)
  w.set_busy(True,'Đang mở phiếu có chênh lệch giá…');task=Worker(read);task.signals.result.connect(ready);task.signals.error.connect(lambda message:status.setText(message) if isValid(status) else None);task.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(task)
 edit_pr=QPushButton('Nhập / sửa số PR của dòng đã chọn');edit_pr.setObjectName('priceManualPR');v.insertWidget(v.indexOf(table),edit_pr,0,Qt.AlignLeft);edit_pr.setEnabled(bool(entries))
 def edit_reference():
  i=table.currentRow()
  if w.busy or not 0<=i<len(entries) or table.isRowHidden(i):return
  entry=entries[i]
  from PySide6.QtWidgets import QInputDialog
  text,okay=QInputDialog.getText(w,'Số PR tham chiếu của phiếu','Phiếu '+entry['sheet']+' · '+entry['day']+'\nChỉ ghi số tham chiếu, không tạo PR trong thư viện. Để trống để bỏ số nhập tay.',text=entry.get('manual_pr') or ', '.join(entry.get('pr_numbers') or []))
  if not okay:return
  try:
   from receiving_price_pr import save_reference
   save_reference(entry['report'],entry['sheet'],text,entry['source_signature'],entry.get('manual_pr',''))
   number=text.strip()
   for index,other in enumerate(entries):
    if other['report']==entry['report'] and other['sheet']==entry['sheet']:
     other['manual_pr']=number;other['pr_numbers']=[number] if number else [];other['pr_error']=''
     table.item(index,4).setText(number or 'Chưa rõ số PR');table.item(index,4).setToolTip('Số PR tham chiếu nhập tay · Bấm đúp để sửa')
   status.setText('Đã lưu số PR tham chiếu. Ảnh PR đang ghép vẫn giữ nguyên.');reload()
  except (OSError,ValueError,KeyError) as exc:status.setText('Chưa lưu số PR: '+str(exc))
 edit_pr.clicked.connect(edit_reference)
 open_.clicked.connect(open_selected);table.cellDoubleClicked.connect(lambda row,col:edit_reference() if col==4 else open_selected())
 search=QLineEdit();search.setObjectName('priceItemSearch');search.setPlaceholderText('Tìm tên hàng hoặc mã hàng…');search.setClearButtonEnabled(True);search.setMinimumHeight(36)
 search.setAccessibleName('Tìm tên hoặc mã hàng trong Giá mua')
 count=QLabel();count.setObjectName('priceSearchCount')
 filterbar=QHBoxLayout();filterbar.addWidget(search,1);filterbar.addWidget(count);v.insertLayout(v.indexOf(edit_pr),filterbar)
 from rec_receipt_search import normalize
 texts=[normalize(e['name']+' '+e['code']) for e in entries]
 def filter_items(*_):
  query=search.text();w._price_item_query=query;terms=normalize(query).split()
  visible=[]
  for index,text in enumerate(texts):
   matches=all(term in text for term in terms);table.setRowHidden(index,not matches)
   if matches:visible.append(index)
  count.setText(str(len(visible))+' / '+str(len(entries))+' dòng')
  if table.currentRow() not in visible:
   table.clearSelection();table.setCurrentCell(-1,-1)
   if visible:table.selectRow(visible[0])
  edit_pr.setEnabled(bool(visible));open_.setEnabled(bool(visible))
 search.textChanged.connect(filter_items);search.setText(getattr(w,'_price_item_query',''));filter_items()

 table.horizontalHeader().setMinimumHeight(54)
 page.setStyleSheet('QTableWidget#monthlyPriceTable {font-family: Segoe UI;font-size:15px;color:#334155;} QTableWidget#monthlyPriceTable::item {padding:10px;} QTableWidget#monthlyPriceTable QHeaderView::section {font-size:14px;font-weight:600;color:#475569;} QWidget#monthlyPricePage {background:white;color:#475569;font-family:"Segoe UI";font-size:13px;} QHeaderView::section {background:#f1f5f9;border:0;padding:10px;} QPushButton {min-height:36px;padding:0 16px;}')
 if not embedded:w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
 return page
