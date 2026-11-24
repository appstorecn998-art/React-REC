"""Screen38: source-row numeric flags and actual document image, no guessed values."""
from pathlib import Path
from receiving_image_archive import image_name, source_digest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QSplitter,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox
from rec_pr_surface import flat_page

def show(w):
 old=getattr(w,'numeric_review_page',None)
 if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
 page=QWidget();page.setObjectName('numericReviewPage');QVBoxLayout(page);w.numeric_review_page=page
 content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18)
 tools=QHBoxLayout();mode=QComboBox();mode.setObjectName('numericReviewFilter');mode.addItems(['Chỉ dòng cần rà số','Tất cả dòng']);next_button=QPushButton('Dòng cần rà tiếp theo');tools.addWidget(mode);tools.addWidget(next_button);tools.addStretch();v.addLayout(tools)
 split=QSplitter(Qt.Horizontal);v.addWidget(split)
 from receiving_qt import PreviewView
 preview=PreviewView();preview.setFixedHeight(420);split.addWidget(preview)
 right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(0,0,0,0);rv.setSpacing(16)
 table=QTableWidget(0,4);table.setObjectName('numericReviewTable');table.setHorizontalHeaderLabels(['Dòng','Lượng giao','Thực nhận','Giá']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44);rv.addWidget(table)
 warning=QLabel('Chọn dòng để định vị vùng ảnh. Nếu không định vị được, mở toàn ảnh để kiểm tra; không đoán số.');warning.setWordWrap(True);warning.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;');rv.addWidget(warning)
 status=QLabel();status.setWordWrap(True);status.setObjectName('numericReviewStatus');rv.addWidget(status)
 actionrow=QHBoxLayout();actionrow.addStretch();edit=QPushButton('Sửa dòng');edit.setStyleSheet('background:#6054d8;color:white;');actionrow.addWidget(edit);rv.addLayout(actionrow);rv.addStretch();split.addWidget(right);split.setSizes([650,650]);split.setChildrenCollapsible(False)
 box=QDialogButtonBox(QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Cancel).setText('Trở lại phiếu');box.rejected.connect(lambda:w.main_pages.setCurrentWidget(w.receipt_page))
 notice=QLabel('');flat_page(page,'Rà số lượng và giá','Lọc các dòng có số cần xác minh rồi xem vùng ảnh tương ứng',content,notice,box);notice.hide();page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#numericReviewPage {background:white;}')
 for label in page.findChildren(QLabel):
  if label.text()=='PR & đối chiếu / Rà số lượng và giá':label.setText('Rà soát / Rà số lượng và giá')
 sheet=w.current_sheet;report=w.report;state={'rows':[]};w.update_numeric_flags()
 def sync(row):
  if row<0 or row>=len(state['rows']):return False
  source,_=state['rows'][row]
  if w.current_sheet!=sheet or w.report!=report:status.setText('Phiếu đang xem đã đổi. Mở lại Rà số để kiểm tra đúng nguồn.');return False
  for i,(physical,_) in enumerate(w.table.model().rows):
   if physical==source:
    selection=w.table.selectionModel();blocked=selection.blockSignals(True)
    try:w.table.setCurrentIndex(w.table.model().index(i,0))
    finally:selection.blockSignals(blocked)
    return True
  return False
 def selected(row,*_):
  edit.setEnabled(sync(row))
  if not edit.isEnabled():return
  source,values=state['rows'][row];refs=[p for p in w.images if image_name(p)==image_name(str(values.get('Ảnh nguồn') or ''))]
  status.setText('; '.join(w.numeric_flags.get(source,[])) or 'Không có cảnh báo số học; vẫn cần đối chiếu ảnh.')
  if len(refs)!=1 or not refs[0].is_file():preview.clear_image('Không tìm thấy một ảnh nguồn duy nhất');status.setText(status.text()+'\nẢnh nguồn thiếu hoặc không rõ; không tự suy số.');return
  preview.set_image(refs[0])
  preview.set_focus_region()
 def fill(*_):
  from rec_table_state import begin,end
  refresh_state=begin(table,[source for source,_ in state['rows']])
  state['rows']=[pair for pair in w.data_by_sheet.get(sheet,[]) if mode.currentIndex()==1 or w.numeric_flags.get(pair[0])];rows=state['rows'];table.setRowCount(len(rows))
  for i,(source,values) in enumerate(rows):
   texts=[str(values.get('Tên hàng trên phiếu (Ảnh)') or '')]+['Cần xác minh' if values.get(k) is None else str(values[k]).replace('.',',') for k in ['Số lượng','Thực nhận','Đơn giá']]
   for col,text in enumerate(texts):cell=QTableWidgetItem(text);cell.setToolTip('; '.join(w.numeric_flags.get(source,[])));table.setItem(i,col,cell)
   table.setRowHeight(i,57)
  table.setFixedHeight(min(350,44+57*max(1,len(rows))+2));edit.setEnabled(False);next_button.setEnabled(any(w.numeric_flags.get(source) for source,_ in rows))
  end(table,[source for source,_ in rows],refresh_state)
  if rows:
   if table.currentRow()<0:table.setCurrentCell(0,0)
   selected(table.currentRow())
  else:status.setText('Không có dòng cần rà số.' if mode.currentIndex()==0 else 'Chưa có dòng phiếu.');preview.clear_image('Chưa có dòng để xem ảnh')
 def next_row():
  indices=[i for i,(physical,_) in enumerate(state['rows']) if w.numeric_flags.get(physical)]
  if indices:table.setCurrentCell(next((i for i in indices if i>table.currentRow()),indices[0]),0)
 def edit_row():
  if not sync(table.currentRow()) or w.busy:return
  w.edit_current()
  def refreshed():
   if w.busy:return
   refresh_timer.stop();w.update_numeric_flags();fill()
  refresh_timer=QTimer(page);refresh_timer.setInterval(100);refresh_timer.timeout.connect(refreshed);refresh_timer.start()
 table.currentCellChanged.connect(selected);mode.currentIndexChanged.connect(fill);next_button.clicked.connect(next_row);edit.clicked.connect(edit_row);fill();w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
