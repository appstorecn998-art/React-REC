"""REC cloud publisher/viewer UI; no local accounting mutation controls."""
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QDate
from PySide6.QtGui import QPixmap, QIcon, QPalette, QColor, QFontDatabase
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QTabWidget, QSplitter, QPlainTextEdit, QComboBox, QMessageBox, QScrollArea, QStackedWidget, QFrame, QDialog, QDialogButtonBox)
from receiving_cloud_client import CloudClient


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    progress = Signal(str)


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = Signals()

    def run(self):
        try:
            self.signals.result.emit(self.fn(self.signals.progress.emit))
        except Exception as error:
            # Domain messages only; raw exception text may contain local file paths.
            from receiving_cloud_client import CloudError
            self.signals.error.emit(str(error) if isinstance(error, CloudError) else 'Chưa hoàn tất thao tác. Kiểm tra dữ liệu nguồn và thử lại.')
        finally:
            self.signals.finished.emit()


class CloudWindow(QMainWindow):
    signed_in = Signal(object)

    def __init__(self, owner=None, preferences=None, client_factory=CloudClient, startup=False):
        super().__init__(owner); self.owner = owner; self.client_factory = client_factory; self.startup = startup
        if QApplication.style().objectName().lower() != 'fusion': QApplication.setStyle('Fusion')
        icon = QIcon(str(Path(__file__).with_name('rec-package-check.ico')))
        self.setWindowIcon(icon)
        palette = QPalette()
        for role, color in [(QPalette.Window, '#f7f8fc'), (QPalette.WindowText, '#334155'), (QPalette.Base, '#ffffff'), (QPalette.AlternateBase, '#f1f5f9'), (QPalette.Text, '#334155'), (QPalette.Button, '#ffffff'), (QPalette.ButtonText, '#334155'), (QPalette.Highlight, '#7357ed'), (QPalette.HighlightedText, '#ffffff')]:
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
            font = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/name
            if font.exists() and not QApplication.instance().property('recFontsLoaded'): QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setProperty('recFontsLoaded', True)
        self.client = None; self.data = None; self.revision = 0; self.busy = False; self.jobs = set(); self.generation = 0
        self.preferences = Path(preferences) if preferences else None
        self.setWindowTitle('REC · Dữ liệu chia sẻ'); self.resize(1200, 820)
        self.pages = QStackedWidget(); self.setCentralWidget(self.pages)
        self.login_page = QWidget(); self.login_page.setObjectName('loginPage'); self.pages.addWidget(self.login_page)
        host = QWidget(); self.pages.addWidget(host); layout = QVBoxLayout(host); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(12)
        title = QLabel('Dữ liệu REC được chia sẻ'); title.setStyleSheet('font-size:22px;font-weight:600;'); layout.addWidget(title)
        self.note = QLabel('Đăng nhập để xem dữ liệu. Chế độ xem không chỉnh sửa hoặc ghi sổ.'); self.note.setWordWrap(True); layout.addWidget(self.note)
        self.endpoint = QLineEdit('https://rec-cloud.appstoreusa998.workers.dev'); self.endpoint.setObjectName('cloudEndpoint')
        self.username = QLineEdit(); self.username.setPlaceholderText('Tên đăng nhập'); self.username.setObjectName('cloudUsername')
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password); self.password.setPlaceholderText('Mật khẩu'); self.password.setObjectName('cloudPassword')
        self.connect_button = QPushButton('Đăng nhập'); self.connect_button.setObjectName('loginPrimary')
        self.logout_button = QPushButton('Đăng xuất'); self.logout_button.setEnabled(False)
        account_row = QHBoxLayout(); self.account_label = QLabel(); account_row.addWidget(self.account_label); account_row.addStretch(); self.access_button = QPushButton('Phân quyền tài khoản'); account_row.addWidget(self.access_button); account_row.addWidget(self.logout_button); layout.addLayout(account_row)
        login_layout = QVBoxLayout(self.login_page); login_layout.setContentsMargins(24, 24, 24, 24); login_layout.addStretch()
        card = QFrame(); card.setObjectName('loginCard'); card.setFixedWidth(420)
        form = QVBoxLayout(card); form.setContentsMargins(36, 32, 36, 32); form.setSpacing(14)
        brand = QLabel('REC'); brand.setObjectName('loginBrand'); form.addWidget(brand)
        heading = QLabel('Đăng nhập'); heading.setObjectName('loginHeading'); form.addWidget(heading)
        subtitle = QLabel('Truy cập dữ liệu REC được chia sẻ.'); subtitle.setWordWrap(True); form.addWidget(subtitle)
        form.addSpacing(8)
        for label, field in [('Tên đăng nhập', self.username), ('Mật khẩu', self.password)]:
            form.addWidget(QLabel(label)); form.addWidget(field)
        form.addWidget(self.connect_button)
        self.login_status = QLabel(''); self.login_status.setWordWrap(True); self.login_status.setObjectName('loginStatus'); form.addWidget(self.login_status)
        self.connection_button = QPushButton('Cấu hình kết nối'); self.connection_button.setFlat(True); form.addWidget(self.connection_button)
        self.connection_settings = QWidget(); connection = QVBoxLayout(self.connection_settings); connection.setContentsMargins(0, 0, 0, 0); connection.addWidget(QLabel('Địa chỉ REC Cloud')); connection.addWidget(self.endpoint); form.addWidget(self.connection_settings); self.connection_settings.hide()
        self.connection_button.clicked.connect(lambda: self.connection_settings.setVisible(self.connection_settings.isHidden()))
        login_layout.addWidget(card, 0, Qt.AlignHCenter); login_layout.addStretch()
        self.status = QLabel('Chưa kết nối.'); self.status.setWordWrap(True); self.status.setObjectName('cloudStatus'); layout.addWidget(self.status)
        tools = QHBoxLayout(); self.reload_button = QPushButton('Tải dữ liệu mới'); self.reload_button.setEnabled(False); tools.addWidget(self.reload_button); self.receipt_day = QComboBox(); self.receipt_day.addItem('Tất cả ngày', ''); tools.addWidget(self.receipt_day); tools.addStretch()
        self.start = QDateEdit(); self.end = QDateEdit(); today = owner.day if owner else date.today()
        for editor, selected in ((self.start, date(today.year, today.month, 1)), (self.end, today)):
            editor.setCalendarPopup(True); editor.setDisplayFormat('dd/MM/yyyy'); editor.setDate(QDate(selected.year, selected.month, selected.day))
        self.publish_button = QPushButton('Xem trước và chia sẻ…'); self.publish_button.setObjectName('cloudPublish'); self.publish_button.setEnabled(False)
        self.publisher_controls = QWidget(); publishing = QHBoxLayout(self.publisher_controls); publishing.setContentsMargins(0, 0, 0, 0)
        for widget in (QLabel('Phiếu từ'), self.start, QLabel('đến'), self.end, self.publish_button): publishing.addWidget(widget)
        self.publisher_controls.setVisible(owner is not None); tools.addWidget(self.publisher_controls); layout.addLayout(tools)
        self.empty_state = QLabel('Chưa có phiếu được chia sẻ cho tài khoản này.\nPhiếu chỉ xuất hiện sau khi đã kiểm tra, chọn đúng bộ phận và đồng bộ thành công.'); self.empty_state.setObjectName('cloudEmpty'); self.empty_state.setAlignment(Qt.AlignCenter); self.empty_state.setWordWrap(True); self.empty_state.hide(); layout.addWidget(self.empty_state, 1)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.tables = {}; self.items = {}; self.tab_details = {}; self.image_lists = {}; self.previews = {}; self.image_areas = {}; self.image_buttons = {}; self.image_rows = {}
        for key, label, headers in [('orders', 'Thư viện PR', ['Số PR', 'Ngày PR', 'Nhà cung cấp', 'Bộ phận']),
                                    ('receipts', 'Phiếu giao', ['Ngày lưu', 'Phiếu', 'Số PR', 'Trạng thái']),
                                    ('summary', 'Lũy kế toàn bộ sổ', ['Mặt hàng', 'ĐVT', 'Lượng đặt', 'Đã nhận xác minh', 'Còn thiếu', 'Trạng thái'])]:
            page = QWidget(); box = QVBoxLayout(page); split = QSplitter(Qt.Horizontal); box.addWidget(split, 1)
            left = QWidget(); left_box = QVBoxLayout(left); left_box.setContentsMargins(0,0,0,0); split.addWidget(left)
            right = QWidget(); right_box = QVBoxLayout(right); right_box.setContentsMargins(0,0,0,0); split.addWidget(right); split.setSizes([660, 460])
            table = QTableWidget(0, len(headers)); table.setObjectName('cloudTable_'+key); table.setHorizontalHeaderLabels(headers)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); table.verticalHeader().hide(); left_box.addWidget(table, 3)
            details = QPlainTextEdit(); details.setReadOnly(True); details.setPlaceholderText('Chọn một dòng để xem chi tiết.'); left_box.addWidget(details, 1)
            self.tables[key] = table; self.tab_details[key] = details; self.items[key] = []
            if key != 'summary':
                row = QHBoxLayout(); choices = QComboBox(); choices.setMinimumWidth(160); open_image = QPushButton('Xem ảnh'); row.addWidget(choices); row.addWidget(open_image); row.addStretch(); right_box.addLayout(row); self.image_buttons[key] = open_image; self.image_rows[key] = right
                preview = QLabel('Chọn ảnh để xem'); preview.setAlignment(Qt.AlignCenter); preview.setMinimumHeight(200)
                area = QScrollArea(); area.setWidgetResizable(True); area.setWidget(preview); right_box.addWidget(area, 1); self.image_areas[key] = area; area.hide(); open_image.setEnabled(False)
                self.image_lists[key] = choices; self.previews[key] = preview
                open_image.clicked.connect(lambda checked=False, key=key: self.open_image(key))
            table.itemSelectionChanged.connect(lambda key=key: self.selected(key)); self.tabs.addTab(page, label)
        self.setStyleSheet('QLabel#cloudEmpty {background:white;border:1px solid #e2e8f0;border-radius:12px;padding:40px;color:#64748b;font-size:16px;} QWidget#loginPage {background:#f7f8fc;} QLineEdit {background:#ffffff;color:#334155;selection-background-color:#7357ed;selection-color:white;} QLineEdit:disabled {background:#f1f5f9;color:#64748b;} QPushButton:disabled {color:#94a3b8;} QFrame#loginCard {background:white;border:1px solid #e2e8f0;border-radius:16px;} QLabel#loginBrand {color:#7357ed;font-size:18px;font-weight:700;} QLabel#loginHeading {font-size:28px;font-weight:600;} QPushButton#loginPrimary {background:#7357ed;color:white;border:0;border-radius:6px;min-height:42px;} QLabel#loginStatus {color:#b45309;} QLineEdit {padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;} QWidget {background:#f7f8fc;} QLabel {background:transparent;} QTableWidget,QPlainTextEdit,QScrollArea,QScrollArea > QWidget > QWidget {background:white;color:#334155;border:1px solid #e2e8f0;border-radius:6px;} QTableWidget::item:selected {background:#ede9fe;color:#334155;} QTabWidget::pane {background:white;border:1px solid #e2e8f0;border-radius:6px;} QTabBar::tab {background:#f1f5f9;padding:10px 18px;border:0;} QTabBar::tab:selected {background:white;color:#6d50e8;border-bottom:2px solid #7357ed;} QPushButton,QComboBox,QDateEdit {background:white;color:#334155;border:1px solid #dbe2ef;border-radius:6px;padding:4px 10px;} QPushButton:hover {background:#f1efff;} QComboBox QAbstractItemView {background:white;color:#334155;selection-background-color:#ede9fe;} QSplitter::handle {background:#f7f8fc;} QWidget {font-family:"Segoe UI";font-size:13px;color:#334155;} QLineEdit,QPushButton,QComboBox,QDateEdit {min-height:32px;} QHeaderView::section {background:#f1f5f9;padding:8px;border:0;}')
        self.access_button.clicked.connect(self.open_access)
        self.receipt_day.currentIndexChanged.connect(lambda: self.show_dataset(self.current_payload) if getattr(self, 'current_payload', None) else None)
        self.connect_button.clicked.connect(self.login); self.password.returnPressed.connect(self.login)
        self.logout_button.clicked.connect(self.logout); self.reload_button.clicked.connect(self.reload); self.publish_button.clicked.connect(self.prepare)
        if self.preferences and self.preferences.exists():
            try:
                preferences = json.loads(self.preferences.read_text(encoding='utf-8')); self.endpoint.setText(str(preferences.get('endpoint') or 'https://rec-cloud.appstoreusa998.workers.dev')); self.username.setText(str(preferences.get('username', '')))
            except (OSError, ValueError, TypeError): pass
        self.controls(); self.username.setFocus()

    def open_access(self):
        if self.busy or not self.client or self.client.role != 'publisher': return
        def ready(payload):
            from PySide6.QtCore import QTimer
            from rec_cloud_access import AccessDialog
            QTimer.singleShot(0, lambda: AccessDialog(self, payload['accounts']).exec())
        self.run_task(lambda progress: self.client.request('GET', '/access'), ready)

    def set_status(self, message):
        self.status.setText(message); self.login_status.setText(message)

    def controls(self):
        authenticated = bool(self.client and self.client.token)
        self.pages.setCurrentIndex(1 if authenticated and not (self.startup and self.client.role == 'publisher') else 0)
        if authenticated:
            self.tabs.setTabVisible(0, self.client.role == 'publisher'); self.tabs.setTabVisible(2, self.client.role == 'publisher')
            self.account_label.setText(str(self.client.username or '') + (' · Chỉ xem' if self.client.role == 'reader' else ' · Người chia sẻ'))
        self.setWindowTitle('REC · Dữ liệu chia sẻ' if authenticated else 'REC · Đăng nhập')
        self.access_button.setVisible(authenticated and self.client.role == 'publisher')
        self.access_button.setEnabled(authenticated and not self.busy)
        self.receipt_day.setVisible(authenticated and self.client.role == 'reader')
        self.publisher_controls.setVisible(authenticated and self.client.role == 'publisher' and self.owner is not None)
        self.connection_button.setEnabled(not self.busy)
        for widget in (self.endpoint, self.username, self.password, self.connect_button): widget.setEnabled(not self.busy and not authenticated)
        self.logout_button.setEnabled(not self.busy and authenticated); self.reload_button.setEnabled(not self.busy and authenticated)
        self.publish_button.setEnabled(not self.busy and authenticated and self.client.role == 'publisher' and self.owner is not None)
        for table in self.tables.values(): table.setEnabled(not self.busy)
        self.start.setEnabled(not self.busy); self.end.setEnabled(not self.busy)

    def run_task(self, fn, ready):
        if self.busy: return
        self.busy = True; self.controls(); generation = self.generation
        task = Task(fn); self.jobs.add(task)
        task.signals.progress.connect(lambda message: self.set_status(message) if generation == self.generation else None)
        task.signals.result.connect(lambda value: ready(value) if generation == self.generation else None)
        def failed(message):
            if generation == self.generation:
                self.set_status(message)
                if self.client and not self.client.token: self.clear_data()
        def finished():
            self.jobs.discard(task); self.busy = False; self.controls()
        task.signals.error.connect(failed); task.signals.finished.connect(finished); QThreadPool.globalInstance().start(task)

    def login(self):
        if self.busy: return
        username = self.username.text().strip(); password = self.password.text(); self.logout()
        try: client = self.client_factory(self.endpoint.text())
        except ValueError as error: self.set_status(str(error)); return
        if not username or not password: self.set_status('Nhập tên đăng nhập và mật khẩu.'); return
        self.client = client; self.set_status('Đang xác thực tài khoản…'); self.password.clear()
        def work(progress):
            from receiving_cloud_client import CloudError
            client.login(username, password)
            if self.startup: return None
            progress('Đăng nhập thành công. Đang tải dữ liệu chia sẻ…')
            try: return client.dataset()
            except CloudError as error:
                if error.status == 404: return None
                raise
        def ready(payload):
            if payload is not None: self.show_dataset(payload)
            else: self.set_status(('Đăng nhập thành công. Đang mở REC…' if client.role == 'publisher' else 'Đăng nhập thành công. Đang tải dữ liệu…') if self.startup else 'Chưa có bản dữ liệu được chia sẻ.')
            if self.preferences:
                from rec_cloud_paths import atomic_bytes
                atomic_bytes(self.preferences, json.dumps({'endpoint': client.endpoint, 'username': username}).encode())
            if self.owner is not None: self.owner._cloud_client = client
            self.signed_in.emit(client)
        self.run_task(work, ready)

    def clear_data(self):
        self.data = None; self.revision = 0; self.current_payload = None
        for key, table in self.tables.items():
            self.items[key] = []; table.setRowCount(0); self.tab_details[key].clear()
        for choices in self.image_lists.values(): choices.clear()
        for preview in self.previews.values(): preview.clear(); preview.setText('Chọn ảnh để xem')

    def logout(self):
        if self.busy: return
        self.generation += 1
        if self.client: self.client.logout()
        self.client = None; self.password.clear(); self.clear_data(); self.note.setText('Dữ liệu REC được chia sẻ.'); self.set_status(''); self.controls(); self.username.setFocus()

    def reload(self):
        if not self.client or not self.client.token or self.busy: return
        client = self.client; self.set_status('Đang tải dữ liệu mới…'); self.run_task(lambda progress: client.dataset(), self.show_dataset)

    def show_dataset(self, payload):
        selected_day = self.receipt_day.currentData() or ''
        self.clear_data(); self.current_payload = payload; self.data = payload['dataset']; self.revision = payload['revision']
        self.receipt_day.blockSignals(True); self.receipt_day.clear(); self.receipt_day.addItem('Tất cả ngày', '')
        for day in sorted({r['day'] for r in self.data['receipts']}, reverse=True): self.receipt_day.addItem(date.fromisoformat(day).strftime('%d/%m/%Y'), day)
        index = self.receipt_day.findData(selected_day); self.receipt_day.setCurrentIndex(max(0, index)); self.receipt_day.blockSignals(False)
        scope = self.data['scope']; self.note.setText('Phiếu giao: '+scope['start']+' → '+scope['end']+('. Chỉ hiển thị phiếu được cấp quyền theo bộ phận.' if self.client and self.client.role == 'reader' else '. PR và lũy kế: toàn bộ sổ đã chia sẻ. Dữ liệu chỉ đọc.'))
        status = 'Bản '+str(self.revision)+' · Cập nhật '+str(payload.get('published_at') or 'chưa rõ')+' · '+str(payload.get('published_by') or '')
        if self.client and self.client.role == 'reader' and not self.data['receipts']:
            status += ' · Chưa có phiếu đã xác nhận thuộc bộ phận được cấp quyền.'
        if self.data.get('warnings'): status += ' · Có '+str(len(self.data['warnings']))+' lưu ý nguồn; xem chi tiết bên dưới.'
        self.set_status(status); self.status.setToolTip('\n'.join(self.data.get('warnings', [])))
        for key, table in self.tables.items():
            self.items[key] = [r for r in self.data[key] if not self.receipt_day.currentData() or r['day'] == self.receipt_day.currentData()] if key == 'receipts' else self.data[key]; table.setRowCount(len(self.items[key]))
            for number, item in enumerate(self.items[key]):
                if key == 'orders': values = [item.get(k, '') for k in ('number', 'date', 'supplier', 'department')]
                elif key == 'receipts': values = [item['day'], item['label'], item.get('pr_error') or ', '.join(item['pr_numbers']) or 'Chưa rõ số PR', {'verified': 'Đã ghi · Nguồn hợp lệ', 'needs_review': 'Đã ghi · Cần rà nguồn', 'not_posted': 'Chưa ghi sổ'}[item['posting']]]
                else: values = [item.get(k) for k in ('name', 'unit', 'ordered', 'received', 'remaining', 'status')]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem('Chưa xác minh' if value is None else str(value)); cell.setToolTip(cell.text()); table.setItem(number, column, cell)
            table.resizeRowsToContents()
        empty = bool(self.client and self.client.role == 'reader' and not self.items['receipts'])
        self.empty_state.setVisible(empty); self.tabs.setVisible(not empty)
        if self.items['receipts'] and self.client and self.client.role == 'reader': self.tables['receipts'].selectRow(0)
        self.controls()

    def selected(self, key):
        row = self.tables[key].currentRow()
        if not 0 <= row < len(self.items[key]): return
        item = self.items[key][row]
        if key == 'receipts':
            text = '\n\n'.join('Dòng '+str(line['row'])+'\n'+'\n'.join(str(k)+': '+str(v) for k, v in line['values'].items()) for line in item['rows'])
        elif key == 'orders':
            labels = {'item_name': 'Mặt hàng', 'catalog_code': 'Mã hàng', 'quantity': 'Lượng đặt', 'unit_price': 'Đơn giá PR', 'unit': 'ĐVT', 'specification': 'Quy cách'}
            text = '\n\n'.join('\n'.join(labels.get(k, k)+': '+str(v) for k, v in line.items()) for line in item['items'])
        else:
            labels = {'order_id': 'Mã quản lý PR', 'index': 'Dòng PR', 'name': 'Mặt hàng', 'code': 'Mã hàng', 'unit': 'ĐVT', 'ordered': 'Lượng đặt', 'requested': 'Lượng yêu cầu', 'price': 'Đơn giá PR', 'received': 'Đã nhận xác minh', 'recorded_received': 'Tổng khai báo', 'remaining': 'Còn thiếu', 'cancelled': 'Đã ngừng giao', 'reason': 'Lý do', 'status': 'Trạng thái', 'opening_received': 'Nhận trước khi dùng REC', 'opening_before': 'Mốc nhận trước', 'source_unverified': 'Nguồn cần rà', 'item_stopped': 'Đã ngừng món', 'physical_remaining': 'Còn thiếu thực tế', 'stop_reason': 'Lý do ngừng', 'stop_time': 'Ngày ngừng'}
            text = '\n'.join(labels.get(k, k)+': '+('Chưa xác minh' if v is None else str(v)) for k, v in item.items())
        self.tab_details[key].setPlainText(text)
        if key in self.image_lists:
            self.image_areas[key].hide(); self.image_buttons[key].setEnabled(bool(item.get('images')))
            choices = self.image_lists[key]; choices.clear(); self.previews[key].clear(); self.previews[key].setText('Chọn ảnh để xem')
            for number, hash_ in enumerate(item.get('images', []), 1): choices.addItem('Ảnh '+str(number), hash_)

    def open_image(self, key):
        if self.busy or not self.client or not self.client.token: return
        asset = self.image_lists[key].currentData()
        if not asset: return
        self.set_status('Đang tải ảnh…'); client = self.client
        def ready(content):
            pixmap = QPixmap()
            if not pixmap.loadFromData(content): self.set_status('Không đọc được ảnh.'); return
            # Original uploaded resolution; scroll to read small print, no extra recompression.
            self.image_areas[key].show(); self.previews[key].setPixmap(pixmap); self.previews[key].setMinimumSize(pixmap.size()); self.set_status('Ảnh đầy đủ độ phân giải đã chia sẻ.')
        self.run_task(lambda progress: client.image(asset), ready)

    def prepare(self):
        if self.busy or not self.owner or self.owner.busy or getattr(self.owner, 'sheets_sync_running', False):
            self.set_status('Đợi thao tác trên REC hoàn tất trước khi chia sẻ.'); return
        if getattr(getattr(self.owner, '_cloud_sync', None), 'running', False):
            self.set_status('Đang tự đồng bộ REC Cloud. Đợi hoàn tất trước khi chia sẻ thủ công.'); return
        if not self.owner._leave_pr(): return
        client = self.client; root = self.owner.root; destination = self.owner.destination
        start = self.start.date().toPython(); end = self.end.date().toPython()
        self.set_status('Đang chuẩn bị bản chia sẻ từ dữ liệu trên máy…')
        def work(progress):
            from receiving_cloud_snapshot import build_snapshot
            stage = tempfile.TemporaryDirectory(prefix='rec-cloud-')
            try:
                evidence = {}
                dataset, files = build_snapshot(root, destination, start, end, stage.name, evidence=evidence)
                return stage, dataset, files, evidence, client.state()['revision']
            except Exception: stage.cleanup(); raise
        def ready(value):
            stage, dataset, files, evidence, expected = value
            size = sum(item['size'] for item in dataset['assets'].values())/1_000_000
            message = f"Chia sẻ phiếu {start:%d/%m/%Y} → {end:%d/%m/%Y}:\n{len(dataset['receipts'])} phiếu · {len(dataset['orders'])} PR · {len(dataset['assets'])} ảnh ({size:.1f} MB).\nPR và lũy kế là toàn bộ sổ. Bản mới thay thế bản đang hiển thị trên cloud."
            if dataset['warnings']: message += '\nCó '+str(len(dataset['warnings']))+' lưu ý nguồn:\n'+'\n'.join(dataset['warnings'][:5])
            # Queue confirmation after Task.finished so a second task can start safely.
            from PySide6.QtCore import QTimer
            def confirm():
                if QMessageBox.question(self, 'Xác nhận chia sẻ', message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    stage.cleanup(); self.set_status('Chưa gửi dữ liệu lên cloud.'); return
                def publish(progress):
                    def unchanged():
                        from receiving_service import digest
                        from receiving_cloud_client import CloudError
                        if any((digest(p) if p.exists() else None) != sig for p, sig in evidence.items()):
                            raise CloudError('Nguồn hoặc xác nhận kiểm phiếu vừa đổi. Chuẩn bị lại bản chia sẻ.')
                    try: return client.publish(dataset, files, expected, progress, before_commit=unchanged)
                    finally: stage.cleanup()
                self.run_task(publish, lambda result: self.set_status('Đã chia sẻ bản '+str(result['revision'])+'. Người xem có thể bấm Tải dữ liệu mới.'))
            QTimer.singleShot(0, confirm)
        self.run_task(work, ready)

    def closeEvent(self, event):
        if self.busy:
            self.set_status('Đang xử lý. Đợi thao tác hoàn tất trước khi đóng.'); event.ignore(); return
        if self.owner is not None:
            # Closing a view must not invalidate the application's shared session.
            self.clear_data()
        else:
            self.logout()
        super().closeEvent(event)


def open_cloud(owner):
    window = getattr(owner, '_cloud_window', None)
    if window is None:
        window = CloudWindow(owner, owner.root/'.receiving'/'cloud-preferences.json'); owner._cloud_window = window
    client = getattr(owner, '_cloud_client', None)
    if client and client.token and window.client is not client:
        window.client = client
        window.endpoint.setText(client.endpoint)
        window.username.setText(client.username or '')
        window.controls()
    window.show(); window.raise_(); window.activateWindow()
    if window.client and window.client.token and not window.busy and window.data is None:
        window.reload()
    return window


def main():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    # Reader mode never initializes or migrates a publisher profile/catalog/credentials.
    from rec_cloud_paths import user_root
    window = CloudWindow(preferences=user_root()/'.receiving'/'cloud-reader-preferences.json'); window.show()
    return app.exec()
