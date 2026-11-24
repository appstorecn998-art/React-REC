"""Design26: explicit source-row deletion with original mutation/backup service."""
import uuid,json
from datetime import datetime
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QDialogButtonBox
from rec_dialog_surface import surface
from receiving_service import digest,mutate_invoice,atomic_json

def show(w):
    if w.busy or not w.report or not w._leave_pr():return
    index=w.table.currentIndex()
    if not index.isValid():return
    row=w.table.model().source_row(index.row());values=dict(w.table.model().row_values(index.row()))
    report,expected,sheet=w.report,w.source_hash,w.current_sheet
    old=getattr(w,'delete_row_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('deleteRowPage');QVBoxLayout(page);w.delete_row_page=page
    target=QLineEdit(f"{sheet} · Dòng {row-1} · {values.get('Tên hàng trên phiếu (Ảnh)','')}");target.setReadOnly(True)
    reason=QLineEdit();reason.setObjectName('deleteRowReason')
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18)
    for i,(text,control) in enumerate([('Đối tượng',target),('Người / bộ phận và lý do',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);label=QLabel(text);label.setStyleSheet('font-size:11px;color:#7b869a;');v.addWidget(label);v.addWidget(control);grid.addWidget(wrap,0,i);grid.setColumnStretch(i,1);control.setFixedHeight(40);control.setStyleSheet('background:white;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;color:#526079;')
    warning=QLabel('Kiểm tra đúng dòng. Xóa dòng có thể làm kết quả đối chiếu và xác nhận nguồn không còn hợp lệ.');warning.setWordWrap(True);warning.setFixedHeight(62);warning.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;')
    status=QLabel();status.setObjectName('deleteRowStatus');status.setWordWrap(True)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận xóa dòng');box.button(QDialogButtonBox.Cancel).setText('Hủy')
    surface(page,'Xóa dòng trên phiếu','Thao tác cần quyết định rõ ràng',warning,status,box,extras=form)
    card=form.parentWidget().layout();card.removeWidget(warning);card.insertWidget(1,warning)
    page.setStyleSheet(page.styleSheet()+'QWidget#deleteRowPage {background:white;}')
    save.setStyleSheet('QPushButton {background:#b73d51;color:white;border:1px solid #b73d51;border-radius:6px;padding:0;min-height:34px;max-height:34px;font-weight:600;} QPushButton:disabled {background:#ecd4da;border-color:#ecd4da;color:#b7949c;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Xóa dòng trên phiếu':label.setText('Xác nhận / Xóa dòng trên phiếu')
    page.layout().setStretch(page.layout().count()-1,0);page.layout().addStretch()
    last=len(w.data_by_sheet.get(sheet,[]))<=1
    def validate():
        save.setEnabled(bool(reason.text().strip()) and not last)
        status.setVisible(last or not reason.text().strip())
        status.setText('Không xóa dòng cuối cùng của phiếu để tránh mất liên kết chứng từ.' if last else 'Nhập người/bộ phận và lý do trước khi xác nhận.' if not reason.text().strip() else 'Báo cáo được sao lưu trước khi xóa. Lượng đã ghi sổ không tự thay đổi; cần kiểm tra lại nguồn.')
    reason.textChanged.connect(validate);validate()
    def back():w.main_pages.setCurrentWidget(w.receipt_page)
    def confirm():
        if w.busy or not save.isEnabled():return
        try:
            if w.report!=report or w.current_sheet!=sheet or digest(report)!=expected:raise ValueError('Phiếu đã đổi. Tải lại và chọn đúng dòng trước khi xóa.')
            text=reason.text().strip();audit=report.parent/'.receiving'/'row-deletion-audit'/(uuid.uuid4().hex+'.json')
            def operation():
                event=dict(report=str(report),sheet=sheet,source_row=row,old_values=values,reason=text,time=datetime.now().astimezone().isoformat(),before_hash=expected,status='requested')
                event=json.loads(json.dumps(event,default=str))
                atomic_json(audit,event)
                try:mutate_invoice(report,expected,sheet,'delete',[row])
                except Exception as exc:
                    atomic_json(audit,dict(event,status='failed',error=str(exc)));raise
                atomic_json(audit,dict(event,status='deleted',after_hash=digest(report)))
            w.write_in_background(operation);save.setEnabled(False);back()
        except (OSError,ValueError) as exc:status.show();status.setText('Chưa xóa: '+str(exc))
    box.accepted.connect(confirm);box.rejected.connect(back);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
