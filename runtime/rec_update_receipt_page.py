"""Update preview for an existing receipt revision; never creates an extra receipt."""
import json
from fractions import Fraction
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox
from rec_pr_surface import flat_page
from receiving_units import exact_text
from receiving_service import digest
import receiving_ledger as ledger

def open_page(w,path,oid,rid,revision,title,lines,payload,on_confirm):
    old=getattr(w,'update_receipt_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('updateReceiptPage');QVBoxLayout(page);w.update_receipt_page=page
    _,history=ledger.summary(path,lambda p:w._ledger_valid(p,{}))
    selected=next((r for r in history if r['receipt_id']==rid),None)
    from receiving_cumulative import context
    prior,uncertain,_=context(path,oid,rid,lambda p:w._ledger_valid(p,{}))
    # Unknown historical baseline is distinct from an invalid receipt source.
    canonical=ledger.resolve_order(path,oid)
    invalid_others=[r for r in history if r['order_id']==canonical and r['receipt_id']!=rid and r['active'] and not r['valid']]
    old_alloc=selected.get('allocations',{}) if selected else {};comparable=bool(selected and selected['order_id']==canonical and selected['revision']==revision)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18)
    table=QTableWidget(len(lines),6);table.setObjectName('updateReceiptPreview');table.setHorizontalHeaderLabels(['Mặt hàng','Các lần nhận khác đã ghi','Lần nhận cũ','Lần nhận mới','Tổng mới','Còn thiếu']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
    changes=[]
    for i,line in enumerate(lines):
        new=Fraction(payload['allocations'][str(i)]);old_qty=Fraction(old_alloc.get(str(i),'0'));before=prior.get(i,Fraction(0));total=before+new;remaining=Fraction(line['ordered'])-total;unit=line['unit']
        fmt=lambda q:exact_text(q).replace('.',',')+' '+unit
        known=i not in uncertain and comparable
        values=[line['name'],fmt(before) if known else 'Chưa xác minh',fmt(old_qty) if comparable else 'PR cũ khác PR đang chọn',fmt(new),fmt(total) if known else 'Chưa xác minh',fmt(remaining) if known else 'Chưa xác minh']
        for col,text in enumerate(values):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,col,cell)
        table.setRowHeight(i,57);delta=new-old_qty
        if delta and comparable:changes.append(line['name']+': '+('+' if delta>0 else '')+fmt(delta))
    table.setFixedHeight(min(450,44+57*max(1,len(lines))+2));v.addWidget(table)
    notice=QLabel(('Chênh lệch '+('; '.join(changes) or '0')+'. ')+'Thay thế revision đang chọn, không cộng thêm một lần nhận trùng. Giữ phiên bản cũ và tạo sự kiện đồng bộ mới.');notice.setWordWrap(True);notice.setStyleSheet('background:#f7f5ff;color:#746d9c;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;font-size:12px;');v.addWidget(notice)
    form=QGridLayout();form.setHorizontalSpacing(18);source=QLineEdit(payload['sheet']+' · '+payload['day']+' · '+title);source.setReadOnly(True);reason=QLineEdit();reason.setObjectName('updateReceiptReason')
    for col,(label,control) in enumerate([('Phiếu nguồn',source),('Lý do cập nhật',reason)]):
        wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);column.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('color:#7b869a;font-size:11px;');column.addWidget(caption);column.addWidget(control);form.addWidget(wrap,0,col);form.setColumnStretch(col,1)
    v.addLayout(form)
    status=QLabel();status.setObjectName('updateReceiptStatus');status.setWordWrap(True);v.addWidget(status)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận cập nhật lần nhận');box.button(QDialogButtonBox.Cancel).setText('Hủy')
    bottom=QLabel('Cập nhật lần nhận không đồng nghĩa đã đồng bộ Sheets. Kết quả đồng bộ được báo riêng.')
    flat_page(page,'Cập nhật lần nhận đã ghi sổ',payload['sheet']+' · '+title+' · revision '+str(revision)+' → '+str(revision+1),content,bottom,box)
    save.setFixedWidth(save.fontMetrics().horizontalAdvance(save.text())+54);save.setStyleSheet(save.styleSheet()+' QPushButton {padding:0px;}');box.setFixedWidth(sum(b.width() for b in box.buttons())+24)
    bottom.hide();page.setStyleSheet(page.styleSheet()+'QWidget#updateReceiptPage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Cập nhật lần nhận đã ghi sổ':label.setText('Sổ nhận hàng / Cập nhật lần nhận đã ghi sổ')
    page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch()
    expected_ledger=digest(path);expected_report=w.source_hash;sheet=w.current_sheet;expected_payload=json.loads(json.dumps(payload,default=str))
    valid=not invalid_others and comparable
    def validate():
        save.setEnabled(valid and bool(reason.text().strip()))
        if not comparable:status.setText('Lần nhận hoặc PR đã đổi. Mở lại đúng PR của lần nhận trước khi cập nhật.')
        elif invalid_others:status.setText('Lần nhận khác của PR còn nguồn chưa xác minh. Rà nguồn trước khi cập nhật.')
        elif not reason.text().strip():status.setText('Nhập lý do cập nhật lần nhận.')
        elif uncertain:status.setText('Chỉ cập nhật lần nhận này. Tổng lịch sử chưa xác minh; chưa kết luận tổng nhận hoặc thiếu/dư.')
        else:status.clear()
    reason.textChanged.connect(validate);validate()
    def back():w.show_shortage_ledger()
    def accept():
        if w.busy or not save.isEnabled():return
        try:
            if w.ledger_path()!=path or digest(path)!=expected_ledger or ledger.receipt_revision(path,rid)!=revision:raise ValueError('Sổ hoặc revision đã thay đổi. Mở lại trước khi cập nhật.')
            if w.current_sheet!=sheet or digest(w.report)!=expected_report:raise ValueError('Phiếu nguồn đã thay đổi. Tải lại và đối chiếu trước khi cập nhật.')
            if json.loads(json.dumps(payload,default=str))!=expected_payload:raise ValueError('Kết quả đối chiếu đã đổi. Mở lại bản xem trước.')
            _,latest=ledger.summary(path,lambda p:w._ledger_valid(p,{}))
            if any(r['order_id']==canonical and r['receipt_id']!=rid and r['active'] and not r['valid'] for r in latest):raise ValueError('Nguồn lần nhận khác đã đổi. Mở lại trước khi cập nhật.')
            payload['update_reason']=reason.text().strip()
            on_confirm()
            save.setEnabled(False)
        except (OSError,ValueError) as exc:status.setText('Chưa cập nhật: '+str(exc))
    box.accepted.connect(accept);box.rejected.connect(back);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
