"""Shared operation display and compact global action header."""
import re,time
from PySide6.QtCore import QObject,QTimer
from PySide6.QtWidgets import QWidget,QFrame,QHBoxLayout,QVBoxLayout,QLabel,QProgressBar,QSizePolicy

class Tasks(QObject):
    def __init__(self,w,panel):
        super().__init__(w);self.w=w;self.panel=panel;self.active={};self.failed=False
        self.title=QLabel('Sẵn sàng');self.title.setStyleSheet('font-weight:600;color:#164c8d;')
        self.message=QLabel('Chọn thao tác bên trái để bắt đầu.');self.message.setWordWrap(True);self.message.setMinimumWidth(0);self.message.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);self.message.setMaximumHeight(44)
        self.bar=QProgressBar();self.bar.setRange(0,100);self.bar.setValue(0);self.bar.setFixedHeight(5);self.bar.setTextVisible(False);self.bar.setStyleSheet('QProgressBar {border:0;background:#e9e5f5;border-radius:2px;} QProgressBar::chunk {background:#7968dd;border-radius:2px;}')
        v=QVBoxLayout(panel);v.setContentsMargins(14,10,14,10);v.setSpacing(5);v.addWidget(self.title);v.addWidget(self.message,1);v.addWidget(self.bar)
    def status(self,message):
        if not message:return
        self.message.setText(message[:260]);self.message.setToolTip(message)
        match=re.search(r'Đã xử lý (\d+)\s*/\s*(\d+)',message)
        if match and self.active and int(match[2])>0:
            self.bar.setRange(0,int(match[2]));self.bar.setValue(min(int(match[1]),int(match[2])))
    def begin(self,key,title):
        if not self.active:self.failed=False
        self.active[key]=title;self.title.setText(title);self.status(title);self.bar.setRange(0,0)
    def end(self,key,error=''):
        if key not in self.active and not error:return
        if error:self.failed=True;self.status(error)
        self.active.pop(key,None)
        if self.active:self.title.setText(next(reversed(self.active.values())))
        else:
            self.title.setText('Cần kiểm tra lại' if self.failed else 'Đã hoàn tất');self.bar.setRange(0,100);self.bar.setValue(0 if self.failed else 100)
            if not self.failed and self.message.text().startswith('Đang'):self.status('Đã kết thúc tác vụ.')

def install(w,page_layout,content_layout,scroll,bar):
    # Move the existing authoritative controls into two compact rows.
    header=content_layout.takeAt(0)
    def hide_layout(layout):
        if not layout:return
        for i in range(layout.count()):
            item=layout.itemAt(i)
            if item.widget():item.widget().hide()
            elif item.layout():hide_layout(item.layout())
    hide_layout(header.layout() if header else None)
    content_layout.removeWidget(scroll);scroll.hide()
    while bar.count():bar.takeAt(0)
    top=QWidget();row=QHBoxLayout(top);row.setContentsMargins(22,12,22,8);row.setSpacing(14)
    left=QWidget();left.setMinimumWidth(0);left.setFixedHeight(108);lv=QVBoxLayout(left);lv.setContentsMargins(0,0,0,0);lv.setSpacing(7)
    title=QLabel('REC · Nhận hàng và báo cáo');title.setStyleSheet('font-size:16px;font-weight:600;');lv.addWidget(title)
    first=QHBoxLayout();first.setSpacing(6)
    for item in [QLabel('Ngày'),w.date_edit,w.previous,w.receipt_picker,w.next,w.reload_button]:item.setParent(w);first.addWidget(item);item.show()
    first.addStretch();lv.addLayout(first)
    second=QHBoxLayout();second.setSpacing(6)
    for item in [w.add_button,w.read_button,w.merge_button,w.bulk_pr_button,w.publish_button]:second.addWidget(item);item.show()
    w.add_button.setText('Chọn ảnh');w.read_button.setText('Đọc ảnh');w.merge_button.setText('Ghép trang');w.publish_button.setText('Xuất phiếu .xlsx')
    second.addStretch();lv.addLayout(second)
    # Horizontal scrolling keeps controls reachable in narrow windows.
    from PySide6.QtWidgets import QScrollArea
    from PySide6.QtCore import Qt
    action_scroll=QScrollArea();action_scroll.setWidgetResizable(True);action_scroll.setFrameShape(QFrame.NoFrame);action_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn);action_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);action_scroll.setWidget(left);action_scroll.setMinimumWidth(0)
    panel=QFrame();panel.setObjectName('taskDisplay');panel.setMinimumWidth(270);panel.setMaximumWidth(410);panel.setStyleSheet('QFrame#taskDisplay {background:#faf9ff;border:1px solid #e7e3f6;border-radius:10px;}');row.addWidget(action_scroll,3);row.addWidget(panel,2);top.setFixedHeight(146)
    page_layout.insertWidget(0,top);w.task_display=Tasks(w,panel);w.global_action_header=top
    w.statusBar().messageChanged.connect(w.task_display.status)
    old_busy=w.set_busy
    def busy(value,message=''):
        old_busy(value,message)
        w.bulk_pr_button.setEnabled(not value)
        if hasattr(w,'operation_ring'):w.operation_ring.hide()
        if value:w.task_display.begin('busy',message or 'Đang xử lý…')
        else:w.task_display.end('busy')
        if message:w.task_display.status(message)
    w.set_busy=busy
    old_notice=w.show_top_notice
    def notice(title,message,variant='info'):
        w.task_display.status(title+' · '+message)
        if variant in ('warning','error'):
            w.task_display.failed=True
            if not w.task_display.active:w.task_display.title.setText('Cần kiểm tra lại')
        # The task display is the single place for operation notifications.
    w.show_top_notice=notice
    original=w._start_worker
    labels={'load':'Đang tải Sổ nhận hàng','sync':'Đang đồng bộ Google Sheets','prepare':'Đang chuẩn bị dữ liệu','apply':'Đang ghi dữ liệu','close_day':'Đang xuất phiếu'}
    def start(job):
        name=getattr(job.function,'__name__','')
        # Idle inbox scans and image previews must not overwrite a user task.
        module=getattr(job.function,'__module__','')
        tracked=w.busy or name in ('sync','close_day') or module in ('receiving_ledger_loader','receiving_bulk_ledger')
        if tracked:
            key=id(job);w.task_display.begin(key,labels.get(name,'Đang xử lý tác vụ'));errors=[]
            job.signals.progress.connect(w.task_display.status)
            job.signals.error.connect(lambda msg:errors.append(msg))
            job.signals.finished.connect(lambda:w.task_display.end(key,errors[-1] if errors else ''))
        original(job)
    w._start_worker=start

    consume=w.read_progress.consume
    def reading(text,final=False):
        consume(text,final)
        if w.read_progress.total:
            w.task_display.bar.setRange(0,w.read_progress.total);w.task_display.bar.setValue(min(len(w.read_progress.saved|w.read_progress.skipped),w.read_progress.total))
        if w.read_progress.errors:w.task_display.failed=True
    w.read_progress.consume=reading
