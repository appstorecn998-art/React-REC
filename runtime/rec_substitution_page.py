from datetime import datetime
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QLineEdit,QFormLayout,QDialogButtonBox
from rec_pr_action_modal import show_modal,close_modal
from receiving_service import digest
from receiving_substitution import approve,revoke

def open_page(w,item,delivery,row,entry,on_apply):
    page=QWidget();page.setObjectName('substitutionPage');layout=QVBoxLayout(page)
    title=QLabel('Xác nhận PR sai tên / hàng thay thế');title.setStyleSheet('font-size:18px;font-weight:600;color:#27334a;');layout.addWidget(title)
    context=QLabel('PR gốc: '+str(item.get('item_name') or '')+'\nHàng thực giao: '+str(delivery.get('Tên hàng trên phiếu (Ảnh)') or ''));context.setWordWrap(True);layout.addWidget(context)
    guide=QLabel('Dùng khi Purchasing xác nhận PR ghi nhầm tên/quy cách, hoặc chấp nhận hàng thay thế. Ghi rõ tên và quy cách đúng trong lý do; giá khớp chỉ là một thông tin để kiểm tra.');guide.setWordWrap(True);layout.addWidget(guide)
    old=entry.get('substitution_approval') or {};form=QFormLayout();layout.addLayout(form)
    department=QLineEdit(old.get('department',''));purchase=QLineEdit(old.get('purchase',''));day=QLineEdit(old.get('date',w.day.isoformat()));reason=QLineEdit(old.get('reason',''))
    for label,field,name in [('Bộ phận / người xác nhận',department,'substitutionDepartment'),('Purchase xác nhận',purchase,'substitutionPurchase'),('Ngày duyệt (YYYY-MM-DD)',day,'substitutionDate'),('Căn cứ PR ghi sai / lý do thay thế',reason,'substitutionReason')]:
        field.setObjectName(name);field.setMinimumHeight(36);form.addRow(label,field)
    notice=QLabel('Xác nhận chỉ áp dụng cho dòng này. Giữ PR gốc và hàng thực giao; giá, lượng và đơn vị tiếp tục được kiểm tra riêng. Không nhớ thay thế cho lần sau.');notice.setWordWrap(True);layout.addWidget(notice)
    from rec_approval_evidence import EvidencePanel,attach
    from receiving_evidence import with_history,journal
    evidence=EvidencePanel(w,with_history(w,'substitution',row,item,delivery,old));layout.addWidget(evidence)
    status=QLabel();status.setWordWrap(True);status.setStyleSheet('color:#b91c1c;');layout.addWidget(status)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xác nhận cho dòng PR này');box.button(QDialogButtonBox.Cancel).setText('Hủy');remove=box.addButton('Bỏ duyệt thay thế',QDialogButtonBox.ActionRole);remove.setEnabled(bool(old) and old.get('action')!='revoke');layout.addWidget(box)
    expected=w.source_hash;sheet=w.current_sheet;panel=w.pr_panel;state={}
    def refresh():
        state.clear()
        try:state['rule']=approve(row,item,delivery,entry,department.text(),purchase.text(),day.text(),reason.text());status.clear()
        except ValueError as exc:status.setText(str(exc))
        save.setEnabled(bool(state))
    for edit in (department,purchase,day,reason):edit.textChanged.connect(refresh)
    def current():
        if w.current_sheet!=sheet or w.pr_panel is not panel or digest(w.report)!=expected:status.setText('Nguồn đã đổi. Mở lại đối chiếu.');return False
        return True
    def accept():
        refresh()
        if state and current():
            try:
                rule=attach(state['rule'],evidence.persist(),old);journal(w,'substitution',row,item,delivery,rule);on_apply(rule);close_modal(page)
            except (OSError,ValueError,KeyError) as exc:status.setText('Chưa lưu ảnh/xác nhận: '+str(exc))
    def remove_rule():
        if current():
            try:journal(w,'substitution',row,item,delivery,old,'revoke');on_apply(revoke(entry));close_modal(page)
            except (OSError,ValueError,KeyError) as exc:status.setText(str(exc))
    save.clicked.connect(accept);box.rejected.connect(lambda:close_modal(page));remove.clicked.connect(remove_rule);refresh();show_modal(w,page)
    return page
