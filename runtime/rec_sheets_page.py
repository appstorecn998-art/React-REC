"""Integrated preview-first Sheets page; navigation never writes remotely."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QAbstractItemView,QFrame
from fluent_blue import Button,Alert

def show_page(w,load=False):
    page=getattr(w,'sheets_page',None)
    if page is None:
        page=QWidget();page.setObjectName('sheetsPage');page.running=bool(getattr(w,'sheets_sync_running',False));page.submit=None
        from rec_sheets_design import build
        build(w,page)
        from rec_loading_state import LoadingState
        page.loading_state=LoadingState('Google Sheets','Đang tải dữ liệu','Kiểm tra sổ nhận hàng và chuẩn bị dữ liệu xem trước.',retry=lambda:show_page(w,load=True))
        page.layout().insertWidget(0,page.loading_state);page.loading_state.hide()
        w.sheets_page=page;w.main_pages.addWidget(page)
    if load and not page.running and not w.busy and not getattr(w,'sheets_sync_running',False):
        from receiving_qt import Worker
        from receiving_ledger_loader import load as load_ledger
        from receiving_service import accounting_root
        source_path=w.ledger_path()
        page.running=True;page.reload.setEnabled(False);page.save.setEnabled(False);page.status.setText('Đang tải và xác minh sổ trước khi đọc Google Sheets…')
        page.loading_state.title.setText('Đang tải dữ liệu');page.loading_state.description.setText('Kiểm tra sổ nhận hàng và chuẩn bị dữ liệu xem trước.');page.loading_state.progress.setRange(0,0);page.loading_state.progress.show();page.loading_state.skeleton.show();page.loading_state.retry.hide();page.loading_state.show()
        task=Worker(load_ledger,source_path,accounting_root(w.destination),getattr(w,'portable_workspace',False))
        def ready(data):
            if w.ledger_path()!=source_path:
                failed('Thư mục dữ liệu đã đổi; làm mới lại.');return
            _,summary,records,suppliers,_=data
            page.show_snapshot(summary,records)
            page.running=False
            w.preview_shortages_sheets(page,summary,records,suppliers)
        def failed(message):
            page.running=False;page.reload.setEnabled(True);page.status.setText('Chưa tải được sổ: '+message);page.loading_state.fail(message)
        task.signals.result.connect(ready);task.signals.error.connect(failed);w._start_worker(task)
    w.main_pages.setCurrentWidget(page);w.fluent_nav.blockSignals(True);w.fluent_nav.set_current('Google Sheets');w.fluent_nav.blockSignals(False)
    return page
