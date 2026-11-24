"""Consistent review dialogs; original callbacks remain responsible for commits."""
from PySide6.QtWidgets import QLabel,QDialogButtonBox,QComboBox
from rec_control_metrics import normalize
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMessageBox

def confirm_review(parent,sheet,rows,undo=False):
    d=QDialog(parent);d.setObjectName('reviewConfirmation');d.setWindowTitle('Bỏ xác nhận kiểm tra' if undo else 'Xác nhận đã kiểm tra phiếu')
    v=QVBoxLayout(d)
    label=QLabel(f'Phiếu {sheet} · {len(rows)} dòng');label.setWordWrap(True);v.addWidget(label)
    t=QTableWidget(3,2);t.setHorizontalHeaderLabels(['Điểm kiểm tra','Kết quả'])
    for i,pair in enumerate([('Nhà cung cấp, ngày giao','Chờ bạn xác nhận'),('Mã / tên chuẩn / ĐVT nguồn','Chờ bạn xác nhận'),('Số lượng / thực nhận / giá / kho','Chờ bạn xác nhận')]):
        for j,text in enumerate(pair):t.setItem(i,j,QTableWidgetItem(text))
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    t.verticalHeader().hide();t.setShowGrid(False);t.setEditTriggers(QAbstractItemView.NoEditTriggers);t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for i in range(3):t.setRowHeight(i,44)
    v.addWidget(t)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Save).setText('Bỏ xác nhận kiểm tra' if undo else 'Đánh dấu đã kiểm tra');box.accepted.connect(d.accept);box.rejected.connect(d.reject);v.addWidget(box)
    arrange(d,'Bỏ xác nhận đã kiểm tra' if undo else 'Xác nhận đã kiểm tra phiếu','Đánh dấu đã kiểm không tự cộng lượng vào sổ. Nếu nguồn đổi, dấu xác nhận có thể không còn hợp lệ.')
    box.button(QDialogButtonBox.Cancel).setText('Trở lại')
    t.setObjectName('reviewChecklist')
    from PySide6.QtGui import QColor,QFont
    t.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
    t.horizontalHeader().setSectionResizeMode(1,QHeaderView.Fixed);t.setColumnWidth(1,430)
    t.horizontalHeader().setFixedHeight(42)
    for i in range(3):
        t.setRowHeight(i,49)
        status=t.item(i,1);status.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)
        status.setData(Qt.UserRole,bool(undo))
        status.setToolTip("Bấm để chuyển Đã rà / Cần xác nhận")
    def refresh():
        for i in range(3):
            status=t.item(i,1);checked=bool(status.data(Qt.UserRole))
            status.setText('• Đã rà' if checked else '• Cần xác nhận')
            status.setForeground(QColor('#007c5b' if checked else '#a56800'))
            font=status.font();font.setWeight(QFont.DemiBold);status.setFont(font)
    def changed(item):
        if item.column()==1:
            t.blockSignals(True);refresh();t.blockSignals(False)
    def toggle_status(row,col):
        if col==1:
            status=t.item(row,1);status.setData(Qt.UserRole,not bool(status.data(Qt.UserRole)))
    t.cellClicked.connect(toggle_status)
    t.itemChanged.connect(changed);t.blockSignals(True);refresh();t.blockSignals(False)
    from rec_dialog_surface import surface
    surface(d,'Bỏ xác nhận đã kiểm tra phiếu' if undo else 'Xác nhận đã kiểm tra phiếu',
            'Đã rà soát ≠ đã ghi sổ ≠ đã đồng bộ',t,v.itemAt(1).widget(),box)
    from rec_department_guard import department_message
    message='' if undo else department_message(rows)
    if message:
        box.button(QDialogButtonBox.Save).setEnabled(False)
        box.button(QDialogButtonBox.Save).setToolTip(message)
        warning=QLabel(message);warning.setWordWrap(True);warning.setStyleSheet('color:#b91c1c;padding:8px;');d.layout().insertWidget(0,warning)
    def commit():
        if undo or not department_message(rows):d.accept()
    box.accepted.disconnect(d.accept);box.accepted.connect(commit)
    return QMessageBox.Yes if d.exec()==QDialog.Accepted else QMessageBox.No

def arrange(dialog,title,description,combo=None):
    layout=dialog.layout();layout.setContentsMargins(24,22,24,22);layout.setSpacing(16)
    heading=QLabel(title);heading.setStyleSheet('font-size:21px;font-weight:600;color:#25314b;')
    layout.insertWidget(0,heading)
    hint=QLabel(description);hint.setWordWrap(True)
    hint.setStyleSheet('background:#f7f5ff;color:#7968ad;padding:12px;border:1px solid #e7e0fb;border-radius:8px;')
    layout.insertWidget(1,hint)
    box=dialog.findChild(QDialogButtonBox)
    if box:
        box.setStyleSheet('QDialogButtonBox {border-top:1px solid #edf0f5;padding-top:12px;}')
        for button in box.buttons():
            normalize(button);button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text())+38)
        save=box.button(QDialogButtonBox.Save)
        if save:save.setObjectName('primary')
        cancel=box.button(QDialogButtonBox.Cancel)
        if cancel:cancel.setText('Hủy')
    if combo is not None:
        combo.setMinimumHeight(36)
        save=box.button(QDialogButtonBox.Save)
        def validate(*_):
            valid=bool(combo.currentText().strip()) if combo.isEditable() else combo.currentData() is not None
            save.setEnabled(valid)
        combo.currentIndexChanged.connect(validate)
        if combo.isEditable():combo.editTextChanged.connect(validate)
        validate()
        dialog.resize(700,300)
