"""Local configuration, credential import and offline diagnostics."""
import json
import re
from pathlib import Path
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QLineEdit,QPushButton,
                              QFileDialog,QMessageBox,QPlainTextEdit)
from rec_runtime import atomic_bytes,config_check


def show_setup(w):
    if w.busy or getattr(w,'sheets_sync_running',False):
        QMessageBox.information(w,'Đang xử lý','Đợi lượt đọc hoặc đồng bộ kết thúc trước khi đổi cấu hình.');return
    dialog=QDialog(w);dialog.setWindowTitle('Thiết lập máy và kiểm tra cấu hình');dialog.resize(680,620)
    layout=QVBoxLayout(dialog)
    label=QLabel('Dữ liệu cấu hình: '+str(w.root));label.setWordWrap(True);layout.addWidget(label)
    layout.addWidget(QLabel('Khóa Gemini — để trống để giữ khóa đang có'))
    key=QLineEdit();key.setEchoMode(QLineEdit.Password);key.setObjectName('setupGeminiKey');layout.addWidget(key)
    sheet=QLineEdit();sheet.setObjectName('setupSheetId')
    from receiving_sheets import SHEET_ID
    settings=w.root/'.receiving/runtime.json'
    try:existing=json.loads(settings.read_text(encoding='utf-8'))
    except (OSError,ValueError):existing={}
    sheet.setText(existing.get('sheet_id',SHEET_ID))
    layout.addWidget(QLabel('Mã Google Sheets (phần ID trong đường dẫn bảng)'));layout.addWidget(sheet)
    status=QPlainTextEdit();status.setReadOnly(True);status.setObjectName('setupDiagnostics')
    def refresh():
        report=config_check(w.root)
        status.setPlainText('\n'.join(('[OK] ' if v['ok'] else '[Cần kiểm tra] ')+name+': '+v.get('message',str(v.get('rows','Sẵn sàng'))) for name,v in report['checks'].items())+
                            '\nKiểm tra này không gửi yêu cầu qua mạng.')
    def guarded(action):
        try:action();refresh()
        except Exception:QMessageBox.warning(dialog,'Chưa lưu','Tệp không hợp lệ hoặc không ghi được. Kiểm tra định dạng và quyền truy cập.')
    def save():
        value=sheet.text().strip()
        if not re.fullmatch('[A-Za-z0-9_-]+',value):raise ValueError('Invalid sheet ID')
        if key.text().strip():atomic_bytes(w.root/'gemini_api_key.txt',key.text().strip().encode())
        atomic_bytes(settings,json.dumps({**existing,'sheet_id':value}).encode())
        key.clear();w.show_top_notice('Đã lưu cấu hình','Khóa và cấu hình được lưu riêng trên máy; chưa kết nối dịch vụ.')
    def import_key():
        path,_=QFileDialog.getOpenFileName(dialog,'Chọn khóa tài khoản dịch vụ Google','','JSON (*.json)')
        if not path:return
        content=Path(path).read_bytes();data=json.loads(content)
        from google.oauth2.service_account import Credentials
        Credentials.from_service_account_info(data,scopes=['https://www.googleapis.com/auth/spreadsheets'])
        atomic_bytes(w.root/'google-sheets-key.json',content)
    def import_catalog():
        path,_=QFileDialog.getOpenFileName(dialog,'Chọn danh mục gốc','','Excel macro (*.xlsm)')
        if not path:return
        from AutoWatcher import load_catalog_data
        from supplier_rules import read_rules
        cat,groups=load_catalog_data(Path(path));read_rules(w.root/'NhaCungCap.json',cat,groups)
        atomic_bytes(w.root/'DanhMuc.xlsm',Path(path).read_bytes())
        w.catalog=None;w._warehouse_cache=None
    def restore():
        path,_=QFileDialog.getOpenFileName(dialog,'Chọn bản dự phòng lịch sử nhận ảnh',str(w.root/'.receiving'),'JSON (*.json)')
        if not path:return
        if QMessageBox.question(dialog,'Khôi phục lịch sử','Khôi phục lịch sử nhận ảnh từ tệp đã chọn? Bản hiện tại được giữ lại. Tự đọc vẫn tắt.')!=QMessageBox.Yes:return
        w.inbox_toggle.setChecked(False);w.inbox.restore_from(path)
        w.inbox_status.setText(w.inbox.warning);w.show_top_notice('Lịch sử nhận ảnh',w.inbox.warning)
    def models():
        from rec_runtime import repair_models
        repair_models(w.root)
        w.location_failures.clear()
        w.show_top_notice('Model OCR','Đã kiểm tra và khôi phục model OCR từ bộ cài.')
    for text,action in [('Lưu khóa Gemini và mã Sheets',save),('Chọn khóa Google Sheets…',import_key),
                        ('Chọn DanhMuc.xlsm…',import_catalog),('Khôi phục lịch sử nhận ảnh…',restore),('Khôi phục model OCR từ bộ cài',models),
                        ('Kiểm tra cấu hình (không dùng mạng)',refresh)]:
        button=QPushButton(text);button.clicked.connect(lambda checked=False,a=action:guarded(a));layout.addWidget(button)
    layout.addWidget(status)
    close=QPushButton('Đóng');close.clicked.connect(dialog.accept);layout.addWidget(close)
    refresh();dialog.exec()
