"""Screen23: explanatory source checks, exact receipt navigation and confirmed revoke."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QMessageBox
from rec_pr_surface import flat_page

def show(w,payload):
    if w.busy or not w._leave_pr():return
    if getattr(w,'portable_workspace',False):
        from rec_workspaces import ledger_source
        payload=ledger_source(w.destination)(payload)
    from receiving_qt import Worker
    from receiving_ledger_check import inspect
    w.set_busy(True,'Đang kiểm tra nguồn lần nhận…')
    job=Worker(inspect,payload)
    job.signals.result.connect(lambda result:build_page(w,payload,*result))
    job.signals.error.connect(lambda text:w.show_top_notice('Chưa kiểm tra được nguồn',text,variant='warning'))
    job.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(job)

def build_page(w,payload,checks,current_rows):
    old=getattr(w,'receipt_source_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    ledger_path=w.ledger_path()
    page=QWidget();page.setObjectName('receiptSourcePage');QVBoxLayout(page);w.receipt_source_page=page
    table=QTableWidget(len(checks),3);table.setObjectName('receiptSourceChecks');table.setHorizontalHeaderLabels(['Nguồn','Kiểm tra','Kết quả']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setFixedHeight(44)
    for i,(name,valid,reason) in enumerate(checks):
        category='Tên, mã, lượng, ĐVT' if 'Excel' in name else 'Chữ ký phiếu' if name=='Xác nhận kiểm tra' else 'Hash liên kết' if name=='Liên kết PR' else 'Hash nguồn' if name.startswith(('Ảnh phiếu','Ảnh PR')) else 'So với lần ghi sổ'
        for col,text in enumerate([name,category,('• Hợp lệ / không đổi' if valid else '• Cần cập nhật')+' · '+reason]):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,col,cell)
        table.item(i,2).setForeground(QColor('#178255' if valid else '#b07c1b'));table.setRowHeight(i,62)
    table.setFixedHeight(min(500,44+62*len(checks)+2))
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(14);v.addWidget(table)
    status=QLabel();status.setObjectName('receiptSourceStatus');status.setWordWrap(True);v.addWidget(status)
    bad=any(not valid for _,valid,_ in checks)
    notice=QLabel('Lượng đã ghi vẫn có lịch sử nhưng dòng bị ảnh hưởng chưa được xác minh. Không tự thay số lượng sổ theo Excel mới.' if bad else 'Nguồn hiện khớp với lần ghi sổ. Sửa hoặc gỡ lần nhận phải qua xác nhận và giữ lịch sử; thao tác xem không cộng thêm lượng nhận.')
    box=QDialogButtonBox(QDialogButtonBox.Save);open_button=box.button(QDialogButtonBox.Save);open_button.setText('Mở đúng phiếu để cập nhật');remove=box.addButton('Gỡ lần nhận',QDialogButtonBox.ActionRole);remove.setEnabled(bool(payload.get('active')))
    flat_page(page,'Kiểm tra nguồn lần nhận','Cho biết vì sao lượng đã ghi còn hợp lệ hoặc cần cập nhật',content,notice,box)
    page.setStyleSheet(page.styleSheet()+'QWidget#receiptSourcePage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Kiểm tra nguồn lần nhận':label.setText('Sổ nhận hàng / Kiểm tra nguồn lần nhận')
    notice.setStyleSheet('background:#fffaf0;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;color:#916c2b;font-size:12px;')
    open_button.setEnabled(bool(current_rows));page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch()
    def open_receipt():
        if w.busy or not w._leave_pr():return
        from receiving_qt import Worker
        from receiving_service import snapshot,day_images,sheet_signature
        def read():
            report=Path(payload['report']);h,data=snapshot(report)
            if not dict(data).get(payload['sheet']):raise ValueError('Phiếu không còn trong báo cáo. Chưa thể mở để cập nhật.')
            path=Path(payload['reviews_path']);reviews=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            return path.parent,report,h,data,day_images(report.parent),{n:sheet_signature(n,rows) for n,rows in data},reviews
        def ready(data):
            from datetime import date
            w.day=date.fromisoformat(payload['day']);w.date_edit.blockSignals(True);w.date_edit.setDate(QDate(w.day.year,w.day.month,w.day.day));w.date_edit.blockSignals(False)
            w._day_loaded(data);w.select_sheet(payload['sheet']);w.main_pages.setCurrentWidget(w.receipt_page)
            blocked=w.fluent_nav.blockSignals(True)
            try:w.fluent_nav.set_current('Kiểm tra phiếu')
            finally:w.fluent_nav.blockSignals(blocked)
            w.statusBar().showMessage('Đã mở đúng phiếu nguồn. Rà và ghi sổ để cập nhật lần nhận cũ; chưa cộng thêm lần nhận.')
        w.set_busy(True,'Đang tải đúng phiếu nguồn…');job=Worker(read);job.signals.result.connect(ready);job.signals.error.connect(lambda text:status.setText('Chưa mở được: '+text));job.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(job)
    def revoke():
        if w.busy or not payload.get('active'):return
        from rec_revoke_receipt_page import open_page
        open_page(w,payload,lambda changed: (remove.setEnabled(False) if changed else None))
    box.accepted.connect(open_receipt);remove.clicked.connect(revoke)
    w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
