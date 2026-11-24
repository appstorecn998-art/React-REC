"""Explicit receipt revoke confirmation; keeps ledger history and checks revision."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QDialogButtonBox
from PySide6.QtCore import Qt
from rec_dialog_surface import surface
from receiving_service import digest
import receiving_ledger as ledger

def open_page(w,payload,on_done):
    old=getattr(w,'revoke_receipt_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('revokeReceiptPage');QVBoxLayout(page);w.revoke_receipt_page=page
    target=QLineEdit(str(payload.get('sheet',''))+' · '+str(payload.get('day','')));target.setReadOnly(True)
    reason=QLineEdit();reason.setObjectName('revokeReason');reason.setPlaceholderText('Nhập người/bộ phận và lý do gỡ lần nhận')
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18);grid.setVerticalSpacing(18)
    for col,(label,control) in enumerate([('Đối tượng',target),('Người / bộ phận và lý do',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('font-size:11px;color:#7b869a;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,0,col);control.setFixedHeight(40);control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;font-size:13px;')
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    preview=QLabel('Lần nhận bị ngừng tính vào lượng đang nhận; lịch sử được giữ. Kiểm tra đúng phiếu và revision trước khi gỡ.')
    preview.setWordWrap(True);preview.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;font-size:12px;')
    notice=QLabel('Gỡ không xóa phiếu Excel và không xóa lịch sử. Lần nhận sẽ không còn được cộng vào tổng sau khi thao tác thành công.')
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận gỡ lần nhận');box.button(QDialogButtonBox.Cancel).setText('Hủy')
    surface(page,'Gỡ xác nhận lần nhận','Thao tác cần quyết định rõ ràng',preview,notice,box,extras=form)
    page.setStyleSheet(page.styleSheet()+'QWidget#revokeReceiptPage {background:white;} QPushButton#danger {background:#b73d51;color:white;border:1px solid #b73d51;font-weight:600;}')
    save.setObjectName('danger');save.setStyleSheet('QPushButton {background:#b73d51;color:white;border:1px solid #b73d51;border-radius:6px;min-height:34px;max-height:34px;padding:0;font-weight:600;} QPushButton:disabled {background:#ecd4da;border-color:#ecd4da;color:#b7949c;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Gỡ xác nhận lần nhận':label.setText('Xác nhận / Gỡ xác nhận lần nhận')
    page.layout().setStretch(page.layout().count()-1,0);page.layout().addStretch()
    ledger_path=w.ledger_path();state={'valid':False}
    def refresh():
        state['valid']=bool(reason.text().strip());save.setEnabled(state['valid'])
        if not state['valid']:notice.setText('Nhập rõ người/bộ phận và lý do để lưu căn cứ gỡ lần nhận.')
        else:notice.setText('Gỡ không xóa phiếu Excel và không xóa lịch sử. Lần nhận sẽ không còn được cộng vào tổng sau khi thao tác thành công.')
    reason.textChanged.connect(refresh);refresh()
    def back():on_done(False);w.main_pages.setCurrentWidget(w.receipt_page);w.review_tabs.setCurrentIndex(1)
    def accept():
        if not state['valid'] or w.busy:return
        if w.ledger_path()!=ledger_path:notice.setText('Sổ đang xem đã đổi. Mở lại lần nhận trước khi gỡ.');return
        try:
            ledger.revoke_receipt(ledger_path,payload['receipt_id'],payload['revision'],reason=reason.text())
            on_done(True);save.setEnabled(False);w.statusBar().showMessage('Đã gỡ lần nhận; lịch sử và căn cứ vẫn được giữ.')
            w.show_shortage_ledger();__import__('rec_auto_sheets').start(w)
        except (OSError,ValueError) as exc:notice.setText('Chưa gỡ được: '+str(exc))
    box.accepted.connect(accept);box.rejected.connect(back);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
