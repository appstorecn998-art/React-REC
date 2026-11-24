"""Publisher-only editor for existing reader department assignments."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QComboBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QPushButton, QDialogButtonBox, QMessageBox)
from rec_cloud_window import Task


class AccessDialog(QDialog):
    def __init__(self, cloud, accounts):
        super().__init__(cloud)
        self.cloud = cloud
        self.client = getattr(cloud, 'client', None) or getattr(cloud, '_cloud_client', None)
        self.accounts = accounts
        self.running = False
        self.setWindowTitle('REC · Phân quyền tài khoản')
        self.resize(480, 430)
        box = QVBoxLayout(self)
        box.addWidget(QLabel('Tài khoản khách'))
        self.account = QComboBox()
        for account in accounts:
            self.account.addItem(account['username'] + (' · Đã khóa' if account['disabled'] else ''), account['username'])
        box.addWidget(self.account)
        help_text = QLabel('Chọn bộ phận từ danh mục REC. Bỏ chọn tất cả để thu hồi quyền xem. KC là bộ phận bếp (Kitchen).')
        help_text.setWordWrap(True); box.addWidget(help_text)
        self.departments = QPlainTextEdit(); self.departments.hide()
        self.choices = QListWidget(); box.addWidget(self.choices)
        self.catalog = {}
        owner = getattr(cloud, 'owner', cloud)
        if owner is not None:
            from warehouse_directory import load_warehouse_directory
            for code, (name, department) in load_warehouse_directory(owner.root/'DanhMuc.xlsm').items():
                if department.strip(): self.catalog.setdefault(department.casefold(), (department, []))[1].append(name)
        self.status = QLabel(); self.status.setWordWrap(True); box.addWidget(self.status)
        self.save = QPushButton('Lưu phân quyền'); box.addWidget(self.save)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(self.reject); box.addWidget(buttons)
        self.account.currentIndexChanged.connect(self.selected)
        self.save.clicked.connect(self.persist)
        self.selected()

    def selected(self):
        index = self.account.currentIndex()
        allowed = self.accounts[index]['departments'] if index >= 0 else []
        selected = {d.casefold() for d in allowed}
        self.choices.clear()
        catalog = dict(self.catalog)
        for department in allowed: catalog.setdefault(department.casefold(), (department, []))
        for key, (department, warehouses) in sorted(catalog.items()):
            label = department + (' · '+', '.join(warehouses) if warehouses else ' · Ngoài danh mục')
            item = QListWidgetItem(label); item.setData(Qt.UserRole, department); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked if key in selected else Qt.Unchecked); self.choices.addItem(item)
        self.departments.setPlainText('\n'.join(allowed))
        self.save.setEnabled(index >= 0 and not self.running)

    def persist(self):
        if self.running or self.account.currentIndex() < 0: return
        username = self.account.currentData()
        departments = [self.choices.item(i).data(Qt.UserRole) for i in range(self.choices.count()) if self.choices.item(i).checkState() == Qt.Checked]
        if len(departments) > 100 or any(len(d) > 200 for d in departments):
            self.status.setText('Tối đa 100 bộ phận; mỗi tên tối đa 200 ký tự.'); return
        if QMessageBox.question(self, 'Xác nhận phân quyền', 'Cập nhật quyền xem của '+username+':\n'+(', '.join(departments) or 'Không xem bộ phận nào'), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        self.running = True; self.save.setEnabled(False); self.account.setEnabled(False); self.choices.setEnabled(False)
        self.status.setText('Đang lưu phân quyền…')
        client = self.client
        job = Task(lambda progress: client.request('PUT', '/access', dict(username=username, departments=departments)))
        self.job = job
        def ready(result):
            self.accounts[self.account.currentIndex()]['departments'] = result['departments']
            self.departments.setPlainText('\n'.join(result['departments']))
            self.status.setText('Đã lưu. Quyền áp dụng ở lần tải dữ liệu/ảnh tiếp theo của khách.')
        def finished():
            self.running = False; self.save.setEnabled(True); self.account.setEnabled(True); self.choices.setEnabled(True); self.job = None
        job.signals.result.connect(ready); job.signals.error.connect(self.status.setText); job.signals.finished.connect(finished)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(job)

    def reject(self):
        if not self.running: super().reject()

    def closeEvent(self, event):
        if self.running: event.ignore()
        else: super().closeEvent(event)


def show(owner):
    """Open access management directly, reusing the application's login."""
    client = getattr(owner, '_cloud_client', None)
    if not client or not client.token or client.role != 'publisher':
        QMessageBox.information(owner, 'Phân quyền', 'Phiên quản lý đã hết hạn. Đăng nhập lại REC để quản lý quyền.'); return
    dialog = AccessDialog(owner, [])
    dialog.running = True
    dialog.status.setText('Đang tải tài khoản khách…')
    dialog.account.setEnabled(False); dialog.save.setEnabled(False)
    job = Task(lambda progress: client.request('GET', '/access'))
    dialog.job = job
    def ready(payload):
        dialog.accounts = payload['accounts']; dialog.account.blockSignals(True); dialog.account.clear()
        for account in dialog.accounts:
            dialog.account.addItem(account['username'] + (' · Đã khóa' if account['disabled'] else ''), account['username'])
        dialog.account.blockSignals(False); dialog.selected()
        dialog.status.setText('Chọn tài khoản và các bộ phận được phép xem.' if dialog.accounts else 'Chưa có tài khoản khách.')
    def finished():
        dialog.running = False; dialog.account.setEnabled(True); dialog.save.setEnabled(bool(dialog.accounts)); dialog.job = None
    job.signals.result.connect(ready); job.signals.error.connect(dialog.status.setText); job.signals.finished.connect(finished)
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().start(job)
    dialog.exec()
    return dialog
