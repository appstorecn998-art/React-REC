"""Explicit exit choices while cloud work is active."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


def confirm(owner):
    dialog = QDialog(owner); dialog.setWindowTitle('Thoát REC'); dialog.setFixedWidth(460)
    layout = QVBoxLayout(dialog); layout.setContentsMargins(24, 22, 24, 22); layout.setSpacing(16)
    title = QLabel('Đồng bộ đang chạy'); title.setStyleSheet('font-size:20px;font-weight:600;color:#26324b;'); layout.addWidget(title)
    status = QLabel(owner._cloud_sync.message); status.setWordWrap(True); layout.addWidget(status)
    note = QLabel('Bạn có thể thoát. Dữ liệu đã lưu và hàng chờ được giữ để tiếp tục lần sau. Yêu cầu mạng hiện tại sẽ kết thúc trong nền.'); note.setWordWrap(True); layout.addWidget(note)
    row = QHBoxLayout(); row.addStretch(); stay = QPushButton('Ở lại'); leave = QPushButton('Thoát REC'); row.addWidget(stay); row.addWidget(leave); layout.addLayout(row)
    dialog.setStyleSheet('QDialog{background:#fff;} QLabel{color:#64748b;} QPushButton{min-height:36px;padding:0 18px;border:1px solid #e2e8f0;border-radius:6px;color:#334155;background:#fff;}')
    leave.setStyleSheet('background:#6552df;color:white;border:0;'); stay.setDefault(True)
    stay.clicked.connect(dialog.reject); leave.clicked.connect(dialog.accept)
    return dialog.exec() == QDialog.Accepted
