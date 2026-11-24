from rec_pr_action_modal import show_modal, close_modal
"""Screen16 Purchase approval, with immutable clipboard-image evidence per event."""
import hashlib
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt,QBuffer,QIODevice
from PySide6.QtGui import QImage,QPixmap,QShortcut,QKeySequence
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QPushButton,QHBoxLayout,QApplication
from rec_dialog_surface import surface
from receiving_price_approval import approve,revoke
from receiving_service import digest

def open_page(w,item,delivery,row,entry,suggested_price,on_apply):
    previous=getattr(w,'price_approval_page',None)
    if previous is not None:w.main_pages.removeWidget(previous);previous.deleteLater()
    page=QWidget();page.setObjectName('priceApprovalPage');QVBoxLayout(page);w.price_approval_page=page
    old=entry.get('price_approval') or {};history=old.get('history',[])
    original=QLineEdit(str(item.get('unit_price') or ''));original.setReadOnly(True)
    price=QLineEdit(str(suggested_price if suggested_price is not None else old.get('price','')));price.setObjectName('purchaseNewPrice')
    person=QLineEdit(old.get('person',''));person.setObjectName('purchaseApprover')
    day=QLineEdit(w.day.strftime('%d/%m/%Y'));day.setObjectName('purchasePriceDate');day.setPlaceholderText('DD/MM/YYYY')
    reason=QLineEdit(old.get('reason',''));reason.setObjectName('purchasePriceReason')
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18);grid.setVerticalSpacing(12)
    for i,(label,control) in enumerate([('Giá PR gốc / ĐVT PR',original),('Giá được duyệt / ĐVT PR',price),('Người Purchase xác nhận',person),('Ngày xác nhận',day),('Căn cứ / ghi chú',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('font-size:11px;color:#7b869a;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,i//2,i%2);control.setFixedHeight(40);control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;font-size:13px;')
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(14)
    from rec_approval_evidence import EvidencePanel,attach
    evidence_dir=w.reference_link_path().parent/'price-evidence'
    display_old=dict(old)
    if old.get('evidence') and not old.get('attachments'):
        ref=old['evidence'];name=ref.get('file','')
        if Path(name).name==name:display_old['attachments']=[dict(path=str((evidence_dir/name).resolve()),sha256=ref['sha256'],name=name)]
    from receiving_evidence import with_history,journal
    evidence=EvidencePanel(w,with_history(w,'price',row,item,delivery,display_old));v.addWidget(evidence)
    status=QLabel();status.setWordWrap(True);v.addWidget(status)
    table=QTableWidget(len(history),3);table.setObjectName('priceApprovalHistory');table.setHorizontalHeaderLabels(['Ngày','Thay đổi','Người / căn cứ']);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(40)
    for i,event in enumerate(history):
        change='Bỏ duyệt giá' if event.get('action')=='revoke' else str(event.get('previous_price',''))+' → '+str(event.get('price',''))
        texts=[event.get('date') or event.get('time',''),change,str(event.get('person',''))+' · '+str(event.get('reason',''))+(' · Có ảnh xác nhận (bấm đúp để xem)' if event.get('evidence') or event.get('attachments') else '')]
        for col,text in enumerate(texts):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,col,cell)
        table.setRowHeight(i,49)
    table.setFixedHeight(40+49*min(max(1,len(history)),3)+2);v.addWidget(table)
    if not history:table.hide()
    notice=QLabel('Không áp giá này cho PR khác. Bỏ duyệt phải được ghi vào lịch sử. Ảnh xác nhận được giữ cùng sự kiện duyệt giá.')
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận giá mới');box.button(QDialogButtonBox.Cancel).setText('Hủy');remove=box.addButton('Bỏ duyệt giá',QDialogButtonBox.ActionRole);remove.setEnabled(bool(old) and old.get('action')!='revoke')
    surface(page,'Purchase xác nhận giá mới','Giữ giá PR gốc, lưu riêng người và căn cứ duyệt',content,notice,box,extras=form)
    page.setStyleSheet(page.styleSheet()+'QWidget#priceApprovalPage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Purchase xác nhận giá mới':label.setText('Duyệt ngoại lệ / Purchase xác nhận giá mới')
    box.removeButton(remove);footer=box.parentWidget().layout();footer.insertWidget(footer.indexOf(box),remove);remove.show();box.setFixedWidth(sum(b.width() for b in box.buttons())+12)
    page.layout().setStretch(page.layout().count()-1,0)
    state={};expected=w.source_hash;sheet=w.current_sheet;panel=w.pr_panel
    def history_image(index,*_):
        event=history[index]
        if event.get('attachments'):evidence.show_history({'history':[event]});return
        ref=event.get('evidence')
        if not ref:status.setText('Sự kiện này chưa có ảnh xác nhận.');return
        name=ref.get('file','')
        if Path(name).name!=name:status.setText('Đường dẫn ảnh không hợp lệ.');return
        evidence.view(dict(path=str((evidence_dir/name).resolve()),sha256=ref['sha256']))
    table.cellDoubleClicked.connect(history_image)
    def date_iso():
        raw=day.text().strip()
        try:return datetime.strptime(raw,'%d/%m/%Y').date().isoformat()
        except ValueError:
            try:return datetime.strptime(raw,'%Y-%m-%d').date().isoformat()
            except ValueError:raise ValueError('Ngày xác nhận theo DD/MM/YYYY.')
    def refresh():
        state.clear()
        try:
            # Validation without manufacturing an approval event on every keypress.
            from receiving_units import positive
            positive(price.text());date_iso()
            if not person.text().strip() or not reason.text().strip():raise ValueError('Nhập người Purchase xác nhận và căn cứ thay đổi.')
            state['valid']=True;validation.setText('')
        except ValueError as exc:validation.setText(str(exc))
        save.setEnabled(bool(state))
    validation=QLabel();validation.setWordWrap(True);validation.setStyleSheet('color:#a56800;font-size:12px;');v.insertWidget(0,validation)
    for edit in [price,person,day,reason]:edit.textChanged.connect(refresh)
    refresh()
    def current():
        if w.current_sheet!=sheet or w.pr_panel is not panel or digest(w.report)!=expected:
            status.setText('Nguồn đã đổi. Mở lại đối chiếu trước khi duyệt giá.');return False
        return True
    def back():close_modal(page)
    def accept():
        refresh()
        if not state or not current():return
        try:
            rule=approve(row,item,delivery,entry,price.text(),person.text(),date_iso(),reason.text())
            rule=attach(rule,evidence.persist(),old)
            journal(w,'price',row,item,delivery,rule);on_apply(rule);back()
        except (OSError,ValueError,KeyError) as exc:status.setText('Chưa duyệt giá: '+str(exc))
    def clear_approval():
        if current():
            try:journal(w,'price',row,item,delivery,old,'revoke');on_apply(revoke(entry));back()
            except (OSError,ValueError,KeyError) as exc:status.setText(str(exc))
    box.accepted.connect(accept);box.rejected.connect(back);remove.clicked.connect(clear_approval)
    page.paste_purchase_evidence=evidence.paste
    show_modal(w,page)
    return page
