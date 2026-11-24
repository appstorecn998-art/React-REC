"""Screen35: stage inbox choices; scanning remains the existing hash-based engine."""
import hashlib
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QFileDialog
from rec_pr_surface import flat_page
from receiving_service import IMAGE_EXTENSIONS,atomic_json

def show(w):
 old=getattr(w,'inbox_design_page',None)
 if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
 page=QWidget();page.setObjectName('inboxDesignPage');QVBoxLayout(page);w.inbox_design_page=page
 content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18);grid=QGridLayout();grid.setHorizontalSpacing(18)
 folder=QLineEdit(str(w.inbox_source));folder.setReadOnly(True);folder.setObjectName('inboxDesignFolder');state=QLineEdit('Bật' if w.inbox_toggle.isChecked() else 'Tắt / chờ bạn bật');state.setReadOnly(True)
 for col,(text,field) in enumerate([('Thư mục nhận ảnh',folder),('Trạng thái tự đọc',state)]):
  wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);label=QLabel(text);label.setStyleSheet('font-size:11px;color:#7b869a;');column.addWidget(label);column.addWidget(field);grid.addWidget(wrap,0,col);grid.setColumnStretch(col,1)
 v.addLayout(grid);enabled=QCheckBox('Bật nhận và đọc ảnh tự động');enabled.setObjectName('inboxDesignEnabled');enabled.setChecked(w.inbox_toggle.isChecked());v.addWidget(enabled)
 table=QTableWidget(0,2);table.setObjectName('inboxDesignTable');table.setHorizontalHeaderLabels(['Ảnh','Tình trạng']);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44);v.addWidget(table)
 status=QLabel();status.setObjectName('inboxDesignStatus');status.setWordWrap(True);v.addWidget(status)
 box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Save).setText('Lưu lựa chọn');box.button(QDialogButtonBox.Cancel).setText('Chọn thư mục')
 notice=QLabel('Quét nền chờ ảnh không chiếm bảng tác vụ chính. Khi có lỗi lịch sử, tự đọc phải tạm dừng.')
 flat_page(page,'Nhận ảnh tự động','Theo dõi thư mục ảnh; giữ chống đọc trùng',content,notice,box);page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#inboxDesignPage {background:white;}')
 for label in page.findChildren(QLabel):
  if label.text()=='PR & đối chiếu / Nhận ảnh tự động':label.setText('Danh mục & cấu hình / Nhận ảnh tự động')
 def refresh():
  from receiving_qt import Worker
  source=Path(folder.text());done=set(w.inbox.done);blocked=w.inbox.blocked
  def read():
   if not source.is_dir():raise ValueError('Không tìm thấy thư mục nhận ảnh.')
   rows=[]
   for p in sorted(source.iterdir()):
    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
     before=p.stat();raw=p.read_bytes();after=p.stat()
     stable=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns) and bool(raw)
     rows.append((p.name,'Tạm dừng · kiểm tra lịch sử' if blocked else 'Không đọc lại cùng nguồn' if hashlib.sha256(raw).hexdigest() in done else 'Ảnh mới · chờ lượt xử lý' if stable else 'Đang sao chép · chờ ổn định'))
   return rows
  def ready(rows):
   table.setRowCount(len(rows))
   for i,row in enumerate(rows):
    for j,text in enumerate(row):table.setItem(i,j,QTableWidgetItem(text))
    table.setRowHeight(i,49)
   table.setFixedHeight(min(400,44+49*max(1,len(rows))+2));status.setText(w.inbox.warning if w.inbox.blocked else f'{len(rows)} ảnh trong thư mục. Thay đổi chỉ áp dụng khi bấm Lưu lựa chọn.')
  job=Worker(read);job.signals.result.connect(ready);job.signals.error.connect(lambda text:status.setText(text));w._start_worker(job)
 def choose():
  selected=QFileDialog.getExistingDirectory(w,'Chọn thư mục nhận ảnh',folder.text())
  if selected:folder.setText(selected);refresh()
 def save():
  if w.busy or w.inbox_active:status.setText('Chờ lượt đọc/quét hiện tại kết thúc trước khi đổi lựa chọn.');return
  if enabled.isChecked() and w.inbox.blocked:status.setText('Lịch sử nhận ảnh lỗi. Khôi phục lịch sử trước khi bật tự đọc.');enabled.setChecked(False);return
  source=Path(folder.text())
  if not source.is_dir():status.setText('Thư mục nhận ảnh không tồn tại.');return
  try:
   atomic_json(w.root/'.receiving/inbox-settings.json',dict(source=str(source),enabled=enabled.isChecked()));w.inbox_source=source;w.inbox.observed.clear();w.inbox_folder.setToolTip(str(source))
   w.inbox_toggle.setChecked(enabled.isChecked());w._sync_manual_controls();state.setText('Bật · đang theo dõi' if enabled.isChecked() else 'Tắt / chờ bạn bật');status.setText('Đã lưu lựa chọn. Ảnh đã xử lý vẫn được chống đọc trùng.')
  except OSError:status.setText('Chưa lưu được lựa chọn. Kiểm tra quyền ghi hồ sơ.')
 enabled.toggled.connect(lambda checked:state.setText('Bật sau khi lưu' if checked else 'Tắt sau khi lưu'));box.accepted.connect(save);box.rejected.connect(choose);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);refresh();return page
