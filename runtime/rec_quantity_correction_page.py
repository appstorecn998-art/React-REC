from rec_pr_action_modal import show_modal, close_modal
"""Screen 15: count-based receipt evidence with unchanged vendor/PR sources."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QDialogButtonBox
from rec_dialog_surface import surface
from receiving_quantity_correction import correction
from receiving_service import digest

def open_page(w,item,delivery,row,existing,on_apply):
    old_page=getattr(w,'quantity_correction_page',None)
    if old_page is not None:w.main_pages.removeWidget(old_page);old_page.deleteLater()
    page=QWidget();page.setObjectName('quantityCorrectionPage');QVBoxLayout(page);w.quantity_correction_page=page
    old=existing.get('receipt_correction') or {}
    count=QLineEdit(str(old.get('packs') or ''));count.setObjectName('actualPackCount')
    weight=QLineEdit(str(old.get('grams') or ''));weight.setObjectName('actualPackGrams')
    reason=QLineEdit(str(old.get('reason') or ''));reason.setObjectName('actualPackReason')
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18);grid.setVerticalSpacing(18)
    for i,(label,control) in enumerate([('Số gói thực nhận',count),('Khối lượng 1 gói (g)',weight),('Căn cứ / xác nhận sai',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('font-size:11px;color:#7b869a;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,i//2,i%2);control.setFixedHeight(40);control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;font-size:13px;')
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    preview=QLabel();preview.setObjectName('quantityCorrectionPreview');preview.setWordWrap(True);preview.setFixedHeight(60);preview.setStyleSheet('background:#f7f5ff;color:#574bb8;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;font-size:12px;font-weight:600;')
    notice=QLabel('Giữ nguyên phiếu NCC và PR. Xác nhận này chỉ sửa lượng dùng đối chiếu; giá và thành tiền vẫn phải kiểm tra.')
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận lượng thực nhận');box.button(QDialogButtonBox.Cancel).setText('Hủy');remove=box.addButton('Bỏ xác nhận cũ',QDialogButtonBox.ActionRole);remove.setEnabled(bool(old))
    surface(page,'NCC ghi sai lượng / đơn vị','Xác nhận lượng thực nhận bằng kiểm đếm',preview,notice,box,extras=form)
    page.setStyleSheet(page.styleSheet()+'QWidget#quantityCorrectionPage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / NCC ghi sai lượng / đơn vị':label.setText('Duyệt ngoại lệ / NCC ghi sai lượng / đơn vị')
    notice.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;font-size:12px;')
    box.removeButton(remove);footer=box.parentWidget().layout();footer.insertWidget(footer.indexOf(box),remove);remove.show();box.setFixedWidth(sum(b.width() for b in box.buttons())+12)
    page.layout().setStretch(page.layout().count()-1,0)
    from rec_approval_evidence import EvidencePanel,attach
    from receiving_evidence import with_history,journal
    evidence=EvidencePanel(w,with_history(w,'quantity',row,item,delivery,old));container=preview.parentWidget().layout();container.insertWidget(container.indexOf(preview)+1,evidence)
    expected=w.source_hash;sheet=w.current_sheet;panel=w.pr_panel;state={}
    def refresh():
        state.clear()
        try:
            value=correction(row,item,delivery,count.text(),weight.text(),reason.text() or 'Xem trước')
            preview.setText(f"Lượng thực nhận xác nhận: {value['packs']} × {value['grams']} g = {value['received']} {value['unit']}.".replace('.',','))
            if reason.text().strip():state['value']=correction(row,item,delivery,count.text(),weight.text(),reason.text())
            else:preview.setText(preview.text()+'\nGhi căn cứ kiểm đếm để xác nhận.')
        except ValueError as exc:preview.setText(str(exc))
        save.setEnabled('value' in state)
    for edit in [count,weight,reason]:edit.textChanged.connect(refresh)
    refresh()
    def back():close_modal(page)
    def current():
        if w.current_sheet!=sheet or w.pr_panel is not panel or digest(w.report)!=expected:
            preview.setText('Nguồn đã đổi. Mở lại đối chiếu trước khi xác nhận lượng thực nhận.');return False
        return True
    def accept():
        refresh()
        if 'value' in state and current():
            try:
                rule=attach(state['value'],evidence.persist(),old);journal(w,'quantity',row,item,delivery,rule);on_apply(rule);back()
            except (OSError,ValueError,KeyError) as exc:preview.setText('Chưa lưu ảnh/xác nhận: '+str(exc))
    def clear():
        if current():
            try:journal(w,'quantity',row,item,delivery,old,'revoke');on_apply(None);back()
            except (OSError,ValueError,KeyError) as exc:preview.setText(str(exc))
    box.accepted.connect(accept);box.rejected.connect(back);remove.clicked.connect(clear)
    show_modal(w,page)
    return page
