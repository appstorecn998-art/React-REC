"""Screen36: local recovery with confirmation, backups and no network downloads."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QDialogButtonBox,QFileDialog,QMessageBox
from rec_pr_surface import flat_page

def show(w):
 previous=getattr(w,'recovery_design_page',None)
 if previous is not None:w.main_pages.setCurrentWidget(previous);return previous
 page=QWidget();page.setObjectName('recoveryDesignPage');QVBoxLayout(page);w.recovery_design_page=page
 content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18)
 table=QTableWidget(3,3);table.setObjectName('recoveryDesignTable');table.setHorizontalHeaderLabels(['Thao tác','Tác động','']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
 actions=[]
 for i,(name,scope,text) in enumerate([('Khôi phục lịch sử nhận ảnh','Giữ bản hiện tại; tự đọc vẫn tắt','Chọn bản dự phòng'),('Khôi phục model OCR','Lấy từ bộ cài, không đổi chứng từ','Kiểm tra / khôi phục'),('Kiểm tra cấu hình offline','Không gửi dữ liệu lên mạng','Chạy kiểm tra')]):
  table.setItem(i,0,QTableWidgetItem(name));table.setItem(i,1,QTableWidgetItem(scope));button=QPushButton(text);button.setFixedSize(175,34);table.setCellWidget(i,2,button);actions.append(button);table.setRowHeight(i,62)
 table.setFixedHeight(232);v.addWidget(table);status=QLabel('Chọn thao tác cần thực hiện. Chưa có dữ liệu nào được khôi phục.');status.setObjectName('recoveryDesignStatus');status.setWordWrap(True);v.addWidget(status)
 notice=QLabel('Trước thao tác thay lịch sử phải có xác nhận. Bản dự phòng sổ và mã nguồn không bị coi là ảnh rác.')
 flat_page(page,'Khôi phục và tài nguyên OCR','Tách rõ dữ liệu lịch sử, tài nguyên nhận diện và cấu hình',content,notice,QDialogButtonBox());page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#recoveryDesignPage {background:white;}')
 for label in page.findChildren(QLabel):
  if label.text()=='PR & đối chiếu / Khôi phục và tài nguyên OCR':label.setText('Danh mục & cấu hình / Khôi phục và tài nguyên OCR')
 def allowed():
  if w.busy or w.inbox_active or getattr(w,'sheets_sync_running',False):status.setText('Chờ lượt đọc/quét/đồng bộ kết thúc trước khi khôi phục.');return False
  return True
 def restore():
  if not allowed():return
  selected,_=QFileDialog.getOpenFileName(w,'Chọn bản dự phòng lịch sử nhận ảnh',str(w.root/'.receiving'),'JSON (*.json)')
  if not selected:return
  try:w.inbox.read_state(selected)
  except (OSError,ValueError,TypeError,KeyError):status.setText('Bản dự phòng không hợp lệ. Lịch sử hiện tại được giữ nguyên.');return
  if QMessageBox.question(w,'Khôi phục lịch sử nhận ảnh','Khôi phục lịch sử từ tệp đã chọn? Bản hiện tại được giữ lại; tự đọc sẽ tắt.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
  if not allowed():return
  w.inbox_toggle.setChecked(False)
  try:w.inbox.restore_from(selected);w.inbox_status.setText(w.inbox.warning);status.setText('Đã khôi phục lịch sử và giữ bản trước đó. Tự đọc vẫn tắt; bật lại khi sẵn sàng.')
  except (OSError,ValueError,TypeError,KeyError):status.setText('Chưa khôi phục được. Giữ tự đọc tắt và kiểm tra quyền ghi/bản dự phòng.')
 def models():
  if not allowed():return
  if w.inbox_toggle.isChecked():status.setText('Tắt nhận ảnh tự động trước khi khôi phục model OCR.');return
  from receiving_qt import Worker
  from rec_runtime import repair_models
  for b in actions:b.setEnabled(False)
  w.set_busy(True,'Đang kiểm tra và khôi phục model OCR…');status.setText('Đang kiểm tra và khôi phục model từ bộ cài…');job=Worker(repair_models,w.root)
  def done(_):w.location_failures.clear();status.setText('Đã kiểm tra / khôi phục model OCR từ bộ cài. Chứng từ được giữ nguyên.')
  job.signals.result.connect(done);job.signals.error.connect(lambda _:status.setText('Chưa khôi phục được model. Kiểm tra tài nguyên trong bộ cài; không tự tải qua mạng.'))
  job.signals.finished.connect(lambda:(w.set_busy(False),[b.setEnabled(True) for b in actions]));w._start_worker(job)
 def diagnostics():
  from rec_settings_design import show
  target=show(w);target.run_diagnostics()
 actions[0].clicked.connect(restore);actions[1].clicked.connect(models);actions[2].clicked.connect(diagnostics);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
