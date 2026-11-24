"""Read-only OCR progress page fed by the existing ReadingProgress lifecycle."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QProgressBar,QPlainTextEdit,QTableWidgetItem
from rec_workspace_v2 import page,grid,action
from rec_status_ui import status_item,COLORS

class ReadingPage(QWidget):
    def __init__(self,w):
        super().__init__();self.w=w;self.images=[];self.code=None;self.started=False
        content,v=page('Đọc ảnh và nhật ký','Theo dõi ảnh thực tế; kết quả đã lưu được giữ khi một ảnh lỗi.')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(content)
        self.state=QLabel('Chưa có lượt đọc');self.state.setStyleSheet('font-size:17px;font-weight:600;color:#6054d8;');v.addWidget(self.state)
        self.stage=QLabel('Chọn ảnh ở Tiếp nhận ảnh để bắt đầu.');self.stage.setWordWrap(True);v.addWidget(self.stage)
        from rec_progress_ring import ProgressRing
        self.ring=ProgressRing();summary=QHBoxLayout();v.removeWidget(self.state);summary.addWidget(self.state,1);summary.addWidget(self.ring);v.insertLayout(0,summary)
        self.bar=QProgressBar();self.bar.setRange(0,1);self.bar.setValue(0);self.bar.setTextVisible(False);self.bar.setFixedHeight(7);self.bar.hide()
        self.counts=QLabel();v.addWidget(self.counts)
        self.table=grid(['Ảnh','Bước xử lý','Trạng thái']);self.table.setColumnWidth(1,200);self.table.setColumnWidth(2,190);v.addWidget(self.table,1)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('background:#fff0f2;color:#b3364e;padding:14px;border-radius:8px;');self.error.hide();v.addWidget(self.error)
        self.warning=QLabel();self.warning.setWordWrap(True);self.warning.setStyleSheet('background:#fff8e8;color:#ad781b;padding:14px;border-radius:8px;');self.warning.hide();v.addWidget(self.warning)
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(1200);self.logs.hide();self.logs.setMaximumHeight(200);v.addWidget(self.logs)
        buttons=QHBoxLayout();buttons.addWidget(action('Tiếp nhận ảnh',lambda:w.fluent_nav.set_current('Tiếp nhận ảnh')))
        self.log_toggle=action('Xem nhật ký chi tiết',self.toggle_log);buttons.addWidget(self.log_toggle);buttons.addStretch()
        self.results=action('Kiểm tra kết quả',lambda:w.fluent_nav.set_current('Kiểm tra phiếu'),True);buttons.addWidget(self.results)
        v.addLayout(buttons)
        self.results.setEnabled(False)
    def toggle_log(self):
        self.logs.setVisible(not self.logs.isVisible())
        self.log_toggle.setText('Ẩn nhật ký chi tiết' if self.logs.isVisible() else 'Xem nhật ký chi tiết')
    def begin(self,total):
        self.code=None;self.started=True
        self.state.setStyleSheet('font-size:17px;font-weight:600;color:#6054d8;')
        self.images=list(getattr(self.w,'_workspace_read_selection',None) or self.w.images)
        self.bar.setRange(0,max(1,total));self.ring.set_progress(0);self.logs.clear();self.update_view()
    def update_view(self):
        p=self.w.read_progress;self.logs.setPlainText(p.activity.toPlainText())
        done=min(p.total,len(p.saved|p.skipped))
        self.ring.set_progress(p.completion_percent())
        self.ring.setToolTip(f'{done}/{p.total} ảnh đã lưu hoặc bỏ qua. Chỉ đạt 100% khi bộ đọc kết thúc thành công.')
        self.counts.setText(f'{p.total} ảnh đầu vào · {len(p.read)} đã đọc · {len(p.saved)} đã lưu · {len(p.skipped)} bỏ qua')
        self.stage.setText(p.stage.text());self.table.setRowCount(len(self.images))
        for i,image in enumerate(self.images):
            name=Path(image).name;key=name.casefold()
            if key in p.saved:step,text,kind='Đã lưu vào báo cáo','Đã lưu','done'
            elif key in p.skipped:step,text,kind='Giữ kết quả đã có','Bỏ qua','neutral'
            elif key in p.read:step,text,kind='Đã đọc, chờ lưu / đối chiếu','Chờ xử lý','warning'
            else:step,text,kind='Chờ kết quả','Chưa hoàn tất' if self.code is not None else 'Đang chờ','warning' if self.code is not None else 'running'
            self.table.setItem(i,0,QTableWidgetItem(name));self.table.setItem(i,1,QTableWidgetItem(step));self.table.setItem(i,2,status_item(QTableWidgetItem(),text,kind));self.table.setRowHeight(i,52)
        if self.code is None:
            self.state.setText('Đang đọc ảnh' if self.started else 'Chưa có lượt đọc')
            if done and done<p.total:self.bar.setRange(0,p.total);self.bar.setValue(done)
        else:
            okay=self.code==0 and not p.errors
            self.state.setText(('Đã kết thúc lượt đọc — có cảnh báo cần rà' if p.warning_count else 'Đã kết thúc lượt đọc — cần rà kết quả') if okay else 'Lượt đọc chưa hoàn tất — xem lỗi')
            self.state.setStyleSheet('font-size:17px;font-weight:600;color:'+COLORS[('warning' if p.warning_count else 'done') if okay else 'error']+';')
            self.bar.setRange(0,max(1,p.total));self.bar.setValue(min(done,p.total))
        if p.errors or (self.code is not None and self.code!=0):
            self.error.setText('Các phiếu đã lưu vẫn được giữ. '+(p.errors[-1] if p.errors else 'Bộ đọc đã dừng. Xem nhật ký; chọn lại ảnh lỗi ở Tiếp nhận ảnh để thử tiếp.'));self.error.show()
        else:self.error.hide()
        self.warning.setVisible(bool(p.warning_count) and not p.errors)
        if p.warning_count:self.warning.setText(f'{p.warning_count} thông báo cần chú ý. Kết thúc đọc ảnh chưa đồng nghĩa dữ liệu đã đúng. Mở Kiểm tra kết quả để rà mã, đơn vị, lượng và giá trước khi ghi sổ.')
        self.results.setEnabled(bool(self.w.data_by_sheet))
    def finish(self,code):self.code=code;self.update_view()

def install(w,callbacks):
    p=ReadingPage(w);w.workspace_reading=p;w.main_pages.addWidget(p)
    w.progress_toggle.setParent(w);w.progress_toggle.hide()
    def show():
        w.main_pages.setCurrentWidget(p)
        side=w.fluent_nav;side.blockSignals(True)
        try:side.set_current('Tiếp nhận ảnh')
        finally:side.blockSignals(False)
    callbacks['Đọc ảnh và nhật ký']=show
    # The workflow opens this contextually; there is no extra sidebar module.
    start=w.read_progress.start;consume=w.read_progress.consume;finish=w.read_progress.finish
    def on_start(total):
        w._reading_progress_active=True
        w.operation_banner.hide();w.operation_ring.hide();w.task_display.bar.hide();w.read_progress.bar.hide()
        start(total);p.begin(total);w.set_busy(True,'Đang đọc ảnh; bạn vẫn có thể xem và chuyển phiếu đã có.');show()
    def on_consume(text,final=False):consume(text,final);p.update_view()
    def on_finish(code):finish(code);p.finish(code);w._reading_progress_active=False
    w.read_progress.start=on_start;w.read_progress.consume=on_consume;w.read_progress.finish=on_finish
