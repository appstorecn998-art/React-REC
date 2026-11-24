"""Reopen a closed PR, showing the original outstanding quantities explicitly."""
from fractions import Fraction
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox
from rec_dialog_surface import surface
from receiving_service import digest
from receiving_units import exact_text
import receiving_ledger as ledger

def open_page(w,order_id,title,rows):
    previous=getattr(w,'reopen_order_page',None)
    if previous is not None:w.main_pages.removeWidget(previous);previous.deleteLater()
    page=QWidget();page.setObjectName('reopenOrderPage');QVBoxLayout(page);w.reopen_order_page=page
    table=QTableWidget(1,3);table.setObjectName('reopenOrderPreview');table.setHorizontalHeaderLabels(['PR','Đã nhận','Phần tiếp tục chờ']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
    received=[];outstanding=[];unknown=False
    for row in rows:
        unit=row['unit'];fmt=lambda value:exact_text(Fraction(str(value))).replace('.',',')
        received.append(row['name']+': '+fmt(row['received'])+' '+unit)
        if row['remaining'] is None:unknown=True;outstanding.append(row['name']+': Chưa xác minh')
        else:outstanding.append(row['name']+': '+fmt(max(Fraction(0),Fraction(str(row['ordered']))-Fraction(str(row['received']))))+' '+unit)
    for i,text in enumerate([title,'; '.join(received),'; '.join(outstanding)]):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(0,i,cell)
    table.setRowHeight(0,75);table.setFixedHeight(121)
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18)
    person=QLineEdit();person.setObjectName('reopenReporter');reason=QLineEdit();reason.setObjectName('reopenReason')
    for col,(label,control) in enumerate([('Người / bộ phận yêu cầu',person),('Lý do mở lại',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('color:#7b869a;font-size:11px;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,0,col);grid.setColumnStretch(col,1);control.setFixedHeight(40);control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;font-size:13px;')
    notice=QLabel('Mở lại không tạo thêm lần nhận hoặc sửa số đã ghi.');notice.setObjectName('reopenOrderNotice')
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận mở lại PR');box.button(QDialogButtonBox.Cancel).setText('Hủy')
    surface(page,'Mở lại PR đã ngừng chờ','Tiếp tục theo dõi phần còn thiếu theo lượng đã nhận',table,notice,box,extras=form)
    card=form.parentWidget().layout();card.removeWidget(table);card.insertWidget(1,table)
    page.setStyleSheet(page.styleSheet()+'QWidget#reopenOrderPage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Mở lại PR đã ngừng chờ':label.setText('Xác nhận / Mở lại PR đã ngừng chờ')
    page.layout().setStretch(page.layout().count()-1,0);page.layout().addStretch();path=w.ledger_path();expected=digest(path)
    from rec_approval_evidence import EvidencePanel
    from receiving_evidence import audit_images
    evidence=EvidencePanel(w,audit_images(w.ledger_path(),order_id));container=form.parentWidget().layout();container.insertWidget(container.indexOf(form)+1,evidence)
    def validate():
        save.setEnabled(bool(person.text().strip() and reason.text().strip() and not unknown and rows and all(r.get('reason') for r in rows)))
        if unknown:notice.setText('Nguồn chưa xác minh. Kiểm tra các lần nhận trước khi mở lại PR.')
        elif not rows or not all(r.get('reason') for r in rows):notice.setText('PR chưa ngừng chờ hoặc không còn trong sổ. Mở lại dữ liệu trước khi xác nhận.')
    person.textChanged.connect(validate);reason.textChanged.connect(validate);validate()
    def back():w.show_shortage_ledger()
    def accept():
        if not save.isEnabled() or w.busy:return
        try:
            if w.ledger_path()!=path or digest(path)!=expected:raise ValueError('Sổ đã thay đổi. Tải lại PR trước khi mở lại.')
            summary,_=ledger.summary(path,lambda payload:w._ledger_valid(payload,{}),order_id=order_id);current=[r for r in summary if r['order_id']==order_id]
            if not current or any(r['remaining'] is None for r in current):raise ValueError('Nguồn chưa xác minh. Cập nhật nguồn trước khi mở lại.')
            if not all(r.get('reason') for r in current):raise ValueError('PR không còn ở trạng thái ngừng chờ.')
            ledger.close_order(path,order_id,person.text().strip()+': '+reason.text().strip(),reopen=True,attachments=evidence.persist())
            save.setEnabled(False);back();__import__('rec_auto_sheets').start(w)
        except (OSError,ValueError) as exc:notice.setText('Chưa mở lại: '+str(exc))
    box.accepted.connect(accept);box.rejected.connect(back);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
