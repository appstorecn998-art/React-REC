"""Close remaining shortage by department confirmation; history and received amounts remain."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QDialogButtonBox
from PySide6.QtCore import Qt
from rec_dialog_surface import surface
from receiving_service import digest
from fractions import Fraction
import receiving_ledger as ledger

def open_page(w,order_id,title,rows,on_done):
    old=getattr(w,'close_order_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('closeOrderPage');QVBoxLayout(page);w.close_order_page=page
    person=QLineEdit();person.setObjectName('closeReporter');person.setPlaceholderText('Bộ phận/người báo hủy')
    reason=QLineEdit();reason.setObjectName('closeReason');reason.setPlaceholderText('Lý do ngừng chờ giao')
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18)
    for col,(label,control) in enumerate([('Người / bộ phận báo hủy',person),('Lý do ngừng chờ',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('font-size:11px;color:#7b869a;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,0,col);control.setFixedHeight(40);control.setStyleSheet('background:white;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;color:#526079;')
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    preview=QLabel('Chốt hủy phần còn thiếu theo xác nhận bộ phận. Lịch sử vẫn giữ; đây không phải đã nhận đủ.');preview.setWordWrap(True);preview.setFixedHeight(60);preview.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;font-size:12px;')
    notice=QLabel('Chốt hủy phần còn thiếu theo xác nhận bộ phận. Lịch sử vẫn giữ; đây không phải đã nhận đủ.')
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận ngừng chờ');box.button(QDialogButtonBox.Cancel).setText('Hủy')
    subtitle=title+' · Còn thiếu '+', '.join(r['name']+' '+str(r['remaining'])+' '+r['unit'] for r in rows if r.get('remaining') is not None and Fraction(r['remaining'])>0)
    surface(page,'Ngừng chờ giao bù',subtitle,preview,notice,box,extras=form)
    card=form.parentWidget().layout();card.removeWidget(preview);card.insertWidget(1,preview);notice.hide()
    page.setStyleSheet(page.styleSheet()+'QWidget#closeOrderPage {background:white;} QPushButton#danger {background:#b73d51;color:white;border:1px solid #b73d51;font-weight:600;}');save.setObjectName('danger');save.setStyleSheet('QPushButton {background:#b73d51;color:white;border:1px solid #b73d51;border-radius:6px;min-height:34px;max-height:34px;padding:0;font-weight:600;} QPushButton:disabled {background:#ecd4da;border-color:#ecd4da;color:#b7949c;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Ngừng chờ giao bù':label.setText('Xác nhận / Ngừng chờ giao bù')
    page.layout().setStretch(page.layout().count()-1,0);page.layout().addStretch();state={'valid':False};path=w.ledger_path();expected=digest(path)
    from rec_approval_evidence import EvidencePanel
    from receiving_evidence import audit_images
    evidence=EvidencePanel(w,audit_images(w.ledger_path(),order_id));container=form.parentWidget().layout();container.insertWidget(container.indexOf(form)+1,evidence)
    def refresh():state['valid']=bool(person.text().strip() and reason.text().strip());save.setEnabled(state['valid'])
    person.textChanged.connect(refresh);reason.textChanged.connect(refresh);refresh()
    def back():on_done(False);w.show_shortage_ledger()
    def accept():
        if not state['valid'] or w.ledger_path()!=path:return
        try:
            if w.busy:raise ValueError('REC đang xử lý. Chờ hoàn tất rồi xác nhận.')
            if digest(path)!=expected:raise ValueError('Sổ đã thay đổi. Mở lại PR trước khi ngừng chờ.')
            summary,_=ledger.summary(path,lambda payload:w._ledger_valid(payload,{}),order_id=order_id)
            current=[r for r in summary if r['order_id']==order_id]
            if not current or any(r['remaining'] is None for r in current):raise ValueError('Nguồn chưa được xác minh. Kiểm tra lại trước khi chốt hủy.')
            if any(r.get('reason') for r in current):raise ValueError('PR đã ngừng chờ. Mở lại dữ liệu để kiểm tra.')
            if not any(Fraction(r['remaining'])>0 for r in current):raise ValueError('PR không còn lượng thiếu để chốt hủy.')
            ledger.close_order(path,order_id,person.text().strip()+': '+reason.text().strip(),attachments=evidence.persist())
            on_done(True);w.show_shortage_ledger()
            __import__('rec_auto_sheets').start(w)
        except (OSError,ValueError) as exc:preview.setText('Chưa ngừng chờ: '+str(exc))
    box.accepted.connect(accept);box.rejected.connect(back);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
