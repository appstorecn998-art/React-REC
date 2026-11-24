"""Responsive receipt controls; existing widgets keep their signals and state."""
from PySide6.QtCore import Qt,QEvent,QTimer
from shiboken6 import isValid
from PySide6.QtWidgets import QWidget,QGridLayout,QHBoxLayout,QSizePolicy

class ReceiptToolbar(QWidget):
    def __init__(self,w):
        super().__init__();self.w=w;self.compact=None;self.pending=False;self.reflowing=False
        w.ops_receipt_actions.viewport().installEventFilter(self)
        self.setObjectName('receiptCompactToolbar');self.grid=QGridLayout(self);self.grid.setContentsMargins(0,6,0,6);self.grid.setSpacing(8);self.grid.setColumnStretch(0,1);self.grid.setColumnStretch(1,0)
        self.navigation=QWidget();nav=QHBoxLayout(self.navigation);nav.setContentsMargins(0,0,0,0);nav.setSpacing(6)
        self.actions=QWidget();actions=QHBoxLayout(self.actions);actions.setContentsMargins(0,0,0,0);actions.setSpacing(8)
        w.receipt_search.setFixedWidth(210);w.date_edit.setFixedWidth(128);w.receipt_picker.setFixedWidth(178)
        for control in [w.receipt_search,w.date_edit,w.previous,w.receipt_picker,w.next,w.reload_button]:
            nav.addWidget(control);control.show()
        from PySide6.QtWidgets import QPushButton
        bulk_time=QPushButton('Đổi giờ hàng loạt');bulk_time.setObjectName('bulkCaptureTime');bulk_time.clicked.connect(lambda:__import__('rec_bulk_capture_time').show(w));nav.addWidget(bulk_time)
        remove=QPushButton('Xóa phiếu');remove.setObjectName('removeReceiptVisible');remove.clicked.connect(lambda:__import__('rec_remove_receipt').show(w));nav.addWidget(remove);w.remove_receipt_visible=remove
        nav.addStretch()
        for control in [w.bulk_pr_button,w.ops_review_button,w.publish_button]:
            actions.addWidget(control);control.show()
        self.grid.addWidget(self.navigation,0,0);self.grid.addWidget(self.actions,0,1)
        for control in [w.bulk_pr_button,w.ops_review_button,w.publish_button]:control.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.LayoutRequest,QEvent.StyleChange,QEvent.FontChange,QEvent.Resize) and not self.pending and not self.reflowing:
            self.pending=True;QTimer.singleShot(0,self.reflow)
        return super().eventFilter(obj,event)
    def resizeEvent(self,event):super().resizeEvent(event);self.reflow()
    def reflow(self):
        if not isValid(self) or not isValid(self.w) or not isValid(self.navigation) or not isValid(self.actions) or not isValid(self.w.ops_receipt_actions):return
        if self.reflowing:return
        self.pending=False;self.reflowing=True
        required=self.navigation.minimumSizeHint().width()+self.actions.minimumSizeHint().width()+12
        compact=self.w.ops_receipt_actions.viewport().width()<required
        if compact!=self.compact:
            self.compact=compact;self.grid.removeWidget(self.actions)
            if compact:self.grid.addWidget(self.actions,1,0,1,2,Qt.AlignRight)
            else:self.grid.addWidget(self.actions,0,1,Qt.AlignRight)
            self.w.ops_receipt_actions.setFixedHeight(96 if compact else 54)
        self.reflowing=False

def install(w):
    scroll=w.ops_receipt_actions;old=scroll.takeWidget()
    if old:
        while old.layout().count():old.layout().takeAt(0)
    toolbar=ReceiptToolbar(w);scroll.setWidget(toolbar)
    # Duplicate day text is replaced by the existing editable date control.
    w.ops_profile.hide()
    if old:
        for control in old.findChildren(QWidget,options=Qt.FindDirectChildrenOnly):control.setParent(w);control.hide()
        old.deleteLater()
    w.receipt_toolbar=toolbar
    w.row_detail.setStyleSheet('background:transparent;border:0;padding:2px 0;color:#475569;font-size:12px;')
    if w.row_detail.text().startswith('Chọn dòng'):w.row_detail.clear();w.row_detail.hide()
    for label in [w.paper_total_label,w.total_label]:
        label.setStyleSheet('font-family:Segoe UI;font-size:15px;font-weight:600;color:#334155;background:transparent;border:0;padding:4px 0;')
        label.setMinimumHeight(0);label.setMaximumHeight(48);label.setWordWrap(True);label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter);label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    w.total_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
    w.paper_total_label.setToolTip('Tổng tiền ghi trên chứng từ gốc, dùng để đối chiếu.')
    w.total_label.setToolTip('Tổng tiền tính từ các dòng dữ liệu của phiếu đang xem.')
    toolbar.reflow()
