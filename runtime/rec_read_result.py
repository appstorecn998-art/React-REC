"""Actionable automatic OCR summary based on confirmed engine events."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFrame

def show_result(w,code):
    p=w.read_progress;okay=code==0 and not p.errors
    dialog=QDialog(w);dialog.setObjectName('readResultDialog');dialog.setWindowTitle('Kết quả nhận ảnh');dialog.setMinimumWidth(540)
    v=QVBoxLayout(dialog);v.setContentsMargins(24,24,24,24);v.setSpacing(16)
    title=QLabel('✓ Đã lưu kết quả đọc ảnh' if okay else '⚠ Lượt đọc chưa hoàn tất');title.setStyleSheet('font-size:20px;font-weight:600;color:'+('#166534' if okay else '#9a3412')+';');v.addWidget(title)
    note=QLabel('Ngày lưu: '+w.day.strftime('%d/%m/%Y')+' · Cần kiểm phiếu trước khi ghi sổ');note.setWordWrap(True);v.addWidget(note)
    stats=QFrame();stats.setStyleSheet('background:#f1f5f9;border-radius:8px;');row=QHBoxLayout(stats)
    remaining=max(0,p.total-len(p.saved|p.skipped))
    for number,label in [(p.total,'Ảnh đầu vào'),(len(p.saved),'Ảnh đã lưu'),(len(p.skipped),'Bỏ qua'),(remaining,'Chưa hoàn tất')]:
        col=QVBoxLayout();n=QLabel(str(number));n.setStyleSheet('font-size:24px;font-weight:600;');col.addWidget(n);col.addWidget(QLabel(label));row.addLayout(col)
    v.addWidget(stats)
    detail=QLabel((str(p.invoices)+' phiếu vừa lưu. ' if p.invoices else '')+('Kết quả đã lưu được giữ; ảnh chưa hoàn tất cần kiểm tra nhật ký.' if not okay else 'Đọc xong chưa đồng nghĩa mã hàng, đơn vị, lượng và giá đã đúng.'))
    detail.setWordWrap(True);v.addWidget(detail)
    if p.errors or p.warning_count:
        warning=QLabel(p.errors[-1] if p.errors else f'{p.warning_count} cảnh báo cần rà trong nhật ký.');warning.setWordWrap(True);warning.setStyleSheet('background:#fff7ed;color:#9a3412;padding:12px;border-radius:8px;');v.addWidget(warning)
    actions=QHBoxLayout();logs=QPushButton('Xem nhật ký');close=QPushButton('Đóng');review=QPushButton('Mở Kiểm phiếu');review.setEnabled(bool(p.saved or w.data_by_sheet));review.setStyleSheet('background:#6054d8;color:white;font-weight:600;');actions.addWidget(logs);actions.addStretch();actions.addWidget(close);actions.addWidget(review);v.addLayout(actions)
    logs.clicked.connect(lambda:(w.main_pages.setCurrentWidget(w.workspace_reading),w.workspace_reading.logs.show(),dialog.reject()))
    close.clicked.connect(dialog.reject);review.clicked.connect(dialog.accept)
    dialog.setStyleSheet('QDialog#readResultDialog {background:white;color:#334155;font-family:Segoe UI;font-size:13px;} QPushButton {min-height:36px;padding:0 14px;border:1px solid #dbe2ec;border-radius:7px;}')
    return dialog.exec()==QDialog.Accepted
