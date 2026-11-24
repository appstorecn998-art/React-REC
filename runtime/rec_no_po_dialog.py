"""Explicit no-PR/PO confirmation; persistence stays in the original controller."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QCheckBox,QDialogButtonBox,QWidget
from rec_dialog_surface import surface

def choose(parent,current):
    d=QDialog(parent);d.setObjectName('noPoConfirmation');d.setWindowTitle('Phiếu không có PR/PO');QVBoxLayout(d)
    body=QWidget();v=QVBoxLayout(body);v.setContentsMargins(0,0,0,0);v.setSpacing(22)
    warning=QLabel('Không suy lượng đặt hoặc còn thiếu từ lượng giao. Phiếu vẫn nằm trong Tất cả phiếu; không tự ghi sổ PR.')
    warning.setWordWrap(True);warning.setStyleSheet('background:#f7f5ff;color:#7968ad;border:1px solid #ece5ff;border-radius:9px;padding:15px;');v.addWidget(warning)
    check=QCheckBox('Xác nhận phiếu này không có PR/PO');check.setObjectName('noPoConsent');check.setChecked(current);v.addWidget(check)
    info=QLabel('Bạn theo dõi phần thiếu thủ công trên Sheets. Nguồn phiếu đổi thì trạng thái cần được kiểm tra lại.');info.setWordWrap(True);v.addWidget(info);v.addStretch()
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
    save=buttons.button(QDialogButtonBox.Save);save.setText('Lưu xác nhận');save.setEnabled(check.isChecked());check.toggled.connect(save.setEnabled)
    buttons.button(QDialogButtonBox.Cancel).setText('Trở lại');buttons.rejected.connect(d.reject)
    remove=buttons.addButton('Bỏ chế độ không PR/PO',QDialogButtonBox.ActionRole);remove.setEnabled(current)
    result=[]
    def accept(value):result.append(value);d.accept()
    buttons.accepted.connect(lambda:accept(True));remove.clicked.connect(lambda:accept(False))
    notice=QLabel('Chỉ thay chế độ theo dõi PR/PO của phiếu đang chọn. Lượng thực nhận được giữ nguyên.')
    surface(d,'Phiếu không có PR/PO','Chế độ theo dõi thủ công do bạn xác nhận',body,notice,buttons)
    d.resize(1100,560)
    return result[0] if d.exec()==QDialog.Accepted else None
