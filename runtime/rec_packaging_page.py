from rec_pr_action_modal import show_modal, close_modal
"""Screen 14: explicit package purchase approval, hosted in REC's main pages."""
import json,shutil
from datetime import datetime
from fractions import Fraction
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QCheckBox,QLayout
from receiving_packaging import approval
from receiving_units import exact_text,factor_for,positive
from receiving_service import atomic_json,digest
from rec_dialog_surface import surface

def open_page(w,item,delivery,row,entry,on_apply):
    old_page=getattr(w,'packaging_page',None)
    if old_page is not None:w.main_pages.removeWidget(old_page);old_page.deleteLater()
    page=QWidget();page.setObjectName('packagingPage');QVBoxLayout(page);w.packaging_page=page
    supplier=str(delivery.get('Nhà cung cấp') or '').strip();unit=str(item.get('unit') or '')
    old=entry.get('purchase_approval') or {};rules_path=w.root/'NhaCungCap.json'
    original=rules_path.read_bytes() if rules_path.exists() else b''
    try:rules=json.loads(original) if original else {}
    except (ValueError,TypeError):rules={}
    key={'supplier':supplier,**{k:item.get(k,'') for k in ['item_name','catalog_code','specification','unit']}}
    remembered=next((r for r in rules.get('packaging_rules',[]) if r.get('key')==key),{})
    name=QLineEdit(str(item.get('item_name') or ''));name.setReadOnly(True)
    from receiving_pr_quantity import effective as manual_ordered
    requested=QLineEdit(str(manual_ordered(item,entry) or '').replace('.',',')+' '+unit);requested.setReadOnly(True)
    pack=QLineEdit(str(old.get('pack_size',remembered.get('pack_size',''))));pack.setObjectName('purchasePackSize');pack.setPlaceholderText('Chỉ nhập số, ví dụ 1 hoặc 0,5 — đơn vị '+unit)
    reason=QLineEdit(str(old.get('reason') or ''));reason.setObjectName('purchasePackReason');reason.setPlaceholderText('Ví dụ: NCC xác nhận 1 kg/bịch; căn cứ mua theo gói')
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18);grid.setVerticalSpacing(18);grid.setSizeConstraint(QLayout.SetMinimumSize)
    for i,(label,control) in enumerate([('Tên hàng trên PR (chỉ xem)',name),('Lượng yêu cầu trên PR (chỉ xem)',requested),('Lượng trong 1 gói NCC ('+unit+')',pack),('Căn cứ / lý do',reason)]):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);caption=QLabel(label);caption.setStyleSheet('color:#7b869a;font-size:11px;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,i//2,i%2);control.setFixedHeight(40);control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;font-size:13px;')
    help_text=QLabel('Ô lượng 1 gói chỉ nhập số theo đơn vị PR. Ví dụ PR dùng KG: 1 kg/bịch → nhập 1; 500 g/bịch → nhập 0,5. Mô tả và xác nhận NCC ghi ở ô Căn cứ / lý do.');help_text.setObjectName('purchasePackHelp');help_text.setWordWrap(True);help_text.setStyleSheet('background:#f0f6ff;color:#315d93;border-radius:7px;padding:12px;');
    source_help=QLabel('PR ghi nhầm tên hoặc quy cách? Hủy cửa sổ này, chọn đúng dòng rồi dùng PR sai tên / hàng thay thế để ghi xác nhận của bộ phận và Purchasing. Tên PR gốc được giữ để đối chiếu.');source_help.setWordWrap(True);
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(16);v.addWidget(help_text);v.addWidget(source_help)
    table=QTableWidget(1,3);table.setObjectName('packagingPreview');table.setHorizontalHeaderLabels(['Yêu cầu gốc','Mua theo gói','Lượng tăng']);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionMode(QAbstractItemView.NoSelection);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44);table.setRowHeight(0,49);table.setFixedHeight(95);v.addWidget(table)
    cost=QLabel();cost.setObjectName('packagingCost');cost.setWordWrap(True);cost.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;font-size:12px;');v.addWidget(cost)
    from rec_approval_evidence import EvidencePanel,attach
    from receiving_evidence import with_history,journal
    evidence=EvidencePanel(w,with_history(w,'packaging',row,item,delivery,old));v.addWidget(evidence)
    remember=QCheckBox('Nhớ quy cách đúng NCC / mặt hàng này');remember.setObjectName('rememberPackaging');v.addWidget(remember)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=buttons.button(QDialogButtonBox.Save);save.setText('Xác nhận mua theo đóng gói');buttons.button(QDialogButtonBox.Cancel).setText('Hủy');remove=buttons.addButton('Bỏ duyệt cũ',QDialogButtonBox.ActionRole);remove.setEnabled(bool(old))
    notice=QLabel('Nhớ quy cách không tự duyệt lượng mua cho lần sau. PR gốc và số thực nhận trên phiếu được giữ nguyên.')
    surface(page,'Duyệt mua theo đóng gói NCC','Xem lượng mua và chi phí tăng trước khi đồng ý',content,notice,buttons,extras=form)
    page.setStyleSheet(page.styleSheet()+'QWidget#packagingPage {background:white;}')
    # Footer in the reference is Remove / Cancel / Confirm, with one warning banner.
    notice.hide()
    buttons.removeButton(remove)
    footer=buttons.parentWidget().layout();footer.insertWidget(footer.indexOf(buttons),remove);remove.show()
    buttons.setFixedWidth(sum(b.width() for b in buttons.buttons())+12)
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Duyệt mua theo đóng gói NCC':label.setText('Duyệt ngoại lệ / Duyệt mua theo đóng gói NCC')
    page.layout().setStretch(page.layout().count()-1,0)
    expected_report=w.source_hash;sheet=w.current_sheet;panel=w.pr_panel;state={}
    def refresh():
        state.clear()
        for i in range(3):table.setItem(0,i,QTableWidgetItem('—'))
        try:
            try:positive(pack.text())
            except ValueError:raise ValueError('Lượng trong 1 gói phải là số lớn hơn 0, theo '+unit+'. Chỉ nhập 1 hoặc 0,5 hoặc 1/2; không nhập kg/bịch hay câu mô tả. Ghi mô tả ở Căn cứ / lý do.')
            rule=approval(item,supplier,pack.text(),reason.text() or 'Xem trước',entry)
            qty=Fraction(rule['requested']);approved=Fraction(rule['approved']);size=Fraction(rule['pack_size']);extra=approved-qty
            texts=[exact_text(qty)+' '+unit,f'{int(approved/size)} gói = {exact_text(approved)} {unit}',exact_text(extra)+' '+unit]
            for i,text in enumerate(texts):table.item(0,i).setText(text.replace('.',','))
            import AutoWatcher as aw
            price=aw.parse_invoice_amount(delivery.get('Đơn giá'))
            factor,_=factor_for({0:entry},0,row,item,delivery)
            if factor is None:raise ValueError('Chưa xác nhận quy đổi đơn vị. Cần quy đổi giá giao về ĐVT PR trước khi duyệt chi phí tăng.')
            if entry.get('receipt_correction'):raise ValueError('Dòng có xác nhận NCC sai lượng/ĐVT; cần rà giá thực tế trước khi duyệt đóng gói.')
            if price is None or price<0:raise ValueError('Chưa có giá giao hợp lệ để tính chi phí tăng. Kiểm tra giá thực tế trước khi duyệt.')
            actual_price=Fraction(str(price))/factor;extra_cost=extra*actual_price
            cost.setText(f'Chi phí tăng: {exact_text(extra_cost)} · Giá giao quy về PR: {exact_text(actual_price)} / {unit}.\nTổng theo lượng mua: {exact_text(approved*actual_price)}. Chưa tự quy đổi VAT/chiết khấu. Nhớ quy cách không tự duyệt lần sau.')
            if not reason.text().strip():raise ValueError('Ghi căn cứ đóng gói và lý do duyệt. Chi phí xem trước: '+exact_text(extra_cost))
            state['rule']=approval(item,supplier,pack.text(),reason.text(),entry)
        except ValueError as exc:cost.setText(str(exc))
        save.setEnabled('rule' in state)
    pack.textChanged.connect(refresh);reason.textChanged.connect(refresh);refresh()
    def back():close_modal(page)
    def current():
        if w.current_sheet!=sheet or w.pr_panel is not panel or digest(w.report)!=expected_report:
            cost.setText('Nguồn phiếu đã đổi. Mở lại đối chiếu trước khi duyệt.');return False
        return True
    def accept():
        refresh()
        if 'rule' not in state or not current():return
        try:rule=attach(state['rule'],evidence.persist(),old);journal(w,'packaging',row,item,delivery,rule)
        except (OSError,ValueError,KeyError) as exc:cost.setText('Chưa lưu ảnh bằng chứng: '+str(exc));return
        if remember.isChecked():
            try:
                if (rules_path.read_bytes() if rules_path.exists() else b'')!=original:raise ValueError('Quy tắc NCC đã đổi. Mở lại trước khi lưu quy cách.')
                updated=json.loads(original) if original else {'suppliers':[]}
                updated['packaging_rules']=[r for r in updated.get('packaging_rules',[]) if r.get('key')!=key]+[dict(key=key,pack_size=state['rule']['pack_size'],reason=state['rule']['reason'],no_split=True)]
                if original:
                    backup=w.root/'.autowatcher-backups'/('packaging-rule-'+datetime.now().strftime('%Y%m%d%H%M%S%f'));backup.mkdir(parents=True);shutil.copy2(rules_path,backup/rules_path.name)
                atomic_json(rules_path,updated)
            except (OSError,ValueError) as exc:cost.setText('Chưa lưu quy cách: '+str(exc));return
        on_apply(rule);back()
    def clear():
        if current():
            try:journal(w,'packaging',row,item,delivery,old,'revoke');on_apply(None);back()
            except (OSError,ValueError,KeyError) as exc:cost.setText(str(exc))
    buttons.accepted.connect(accept);buttons.rejected.connect(back);remove.clicked.connect(clear)
    show_modal(w,page)
    return page
