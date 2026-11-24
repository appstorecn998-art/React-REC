from rec_pr_action_modal import show_modal, close_modal

"""Screen 13 from served preview: four fields, exact preview and explicit approval."""

from fractions import Fraction

from PySide6.QtCore import Qt

from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QPlainTextEdit,QDialogButtonBox,QPushButton

from rec_dialog_surface import surface

from receiving_units import positive,exact_text,conversion



def open_page(w,item,delivery,row,existing,on_confirm,on_save_price=None):

    old=getattr(w,'unit_conversion_page',None)

    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()

    page=QWidget();page.setObjectName('unitConversionPage');QVBoxLayout(page)

    w.unit_conversion_page=page

    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18);grid.setVerticalSpacing(18)

    du=delivery.get('Đơn vị trên phiếu') or delivery.get('Đơn vị tính') or '[chưa có ĐVT giao]';pu=item.get('unit') or '[chưa có ĐVT PR]'

    qty=QLineEdit(str(delivery.get('Thực nhận') if delivery.get('Thực nhận') is not None else ''))

    price=QLineEdit(str(delivery.get('Đơn giá') if delivery.get('Đơn giá') is not None else ''))

    # Save price through the source receipt editor, never as an unsaved conversion override.

    for field in [qty]:field.setReadOnly(True);field.setToolTip('Số lấy từ dòng nhận hàng. Muốn sửa, dùng Sửa dòng nhận hàng.')

    factor=QLineEdit(str(existing.get('factor') or ''));factor.setPlaceholderText(f'Nhập số {pu} trong 1 {du}');factor.setObjectName('conversionFactor')

    reason=QPlainTextEdit(str(existing.get('reason') or 'Ncc xác nhận'));reason.setObjectName('conversionReason');reason.setFixedHeight(76)

    qty.setObjectName('conversionReceived');price.setObjectName('conversionDeliveryPrice')
    price.setReadOnly(on_save_price is None)
    price.setPlaceholderText('Nhập giá đúng trên phiếu; không thêm dấu phân cách nghìn')
    save_price=QPushButton('Lưu đơn giá vào phiếu');save_price.setObjectName('conversionSavePrice');save_price.setVisible(on_save_price is not None)
    grid.addWidget(save_price,3,0)
    original_price=price.text()


    for i,(label,control) in enumerate([(f'Thực nhận trên phiếu ({du})',qty),(f'1 {du} trên phiếu = bao nhiêu {pu} trên PR?',factor),(f'Đơn giá trên phiếu (đ/{du})',price),('Căn cứ quy đổi / quy cách bao bì',reason)]):

        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(7);v.setAlignment(Qt.AlignTop);caption=QLabel(label);caption.setStyleSheet('color:#7b869a;font-size:11px;');v.addWidget(caption);v.addWidget(control);grid.addWidget(wrap,i//2,i%2)

        control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:9px 11px;font-size:13px;')

        if isinstance(control,QLineEdit):control.setFixedHeight(40)

    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)

    preview=QLabel();preview.setObjectName('conversionPreview');preview.setWordWrap(True)

    notice=QLabel('Số lượng sau quy đổi = lượng nhận × hệ số; đơn giá sau quy đổi = giá giao ÷ hệ số. Chỉ áp dụng cho dòng PR đang đối chiếu, không sửa lượng hoặc giá trên phiếu gốc.')

    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=buttons.button(QDialogButtonBox.Save);save.setText('Xác nhận quy đổi');buttons.button(QDialogButtonBox.Cancel).setText('Hủy')

    surface(page,'Xác nhận quy đổi đơn vị','Chỉ áp dụng cho dòng PR đang đối chiếu',preview,notice,buttons,extras=form)

    page.setStyleSheet(page.styleSheet()+'QWidget#unitConversionPage {background:white;}')

    for label in page.findChildren(QLabel):

        if label.text()=='Rà soát / Xác nhận quy đổi đơn vị':label.setText('Duyệt ngoại lệ / Xác nhận quy đổi đơn vị')

    context=QLabel('Phiếu giao: '+str(delivery.get('Tên hàng trên phiếu (Ảnh)') or '')+f' · ĐVT giao: {du}'+ '\nPR: '+str(item.get('item_name') or '')+f' · Đặt {item.get("quantity", "—")} {pu}')

    context.setObjectName('conversionContext');context.setWordWrap(True)

    grid.addWidget(context,2,0,1,2)

    preview.setMinimumHeight(84)

    preview.setStyleSheet('background:#f7f5ff;color:#574bb8;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;font-size:12px;')

    page.layout().setStretch(page.layout().count()-1,0)

    normal=notice.styleSheet();state={}

    def refresh():

        state.clear()

        try:

            ratio=positive(factor.text());rule=conversion(row,item,delivery,factor.text(),reason.toPlainText())

            def source_number(text):

                if not text.strip():raise ValueError('Phiếu đang thiếu số thực nhận hoặc đơn giá. Nhập và lưu đơn giá vào phiếu trước khi quy đổi.')
                try:value=Fraction(text.strip().replace(',','.'))
                except (ValueError,ZeroDivisionError):raise ValueError('Nhập số hợp lệ, ví dụ 150000 hoặc 1500,5.')

                if value<0:raise ValueError('Lượng nhận và giá giao không được âm.')

                return value

            q=source_number(qty.text());p=source_number(price.text())

            fmt=lambda n:exact_text(n).replace('.',',')

            preview.setText(f'1 {du} = {fmt(ratio)} {pu}\nSau quy đổi: {fmt(q*ratio)} {pu} · Giá: {fmt(p/ratio)} / {pu}')

            if price.text()!=original_price:raise ValueError('Bấm Lưu đơn giá vào phiếu trước; mở lại Quy đổi ĐVT sau khi lưu xong.')
            state['rule']=rule;notice.setText('Quy đổi này chỉ lưu cho dòng đang đối chiếu. Lưu đối chiếu không ghi sổ và không sửa số liệu trên phiếu gốc.');notice.setStyleSheet(normal)

        except (ValueError,ZeroDivisionError) as exc:

            # A valid factor still gives a live preview before the basis is filled.

            try:

                ratio=positive(factor.text());q=Fraction(qty.text().replace(',','.'));p=Fraction(price.text().replace(',','.'))

                preview.setText(f'1 {du} = {exact_text(ratio)} {pu}\nSau quy đổi: {exact_text(q*ratio)} {pu} · Giá: {exact_text(p/ratio)} / {pu}')

            except (ValueError,ZeroDivisionError):preview.setText(f'Chiều quy đổi: 1 {du} trên phiếu → ? {pu} trên PR.\nVí dụ: 1 thùng có 12 hộp thì nhập 12; 1 gói 500 g tính theo KG thì nhập 0,5.')

            notice.setText(f'Nhập số {pu} tương ứng với 1 {du}; sau đó điền căn cứ để xác nhận.' if not factor.text().strip() else str(exc));notice.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:15px;font-size:12px;')

        save.setEnabled('rule' in state)

    def persist_price():
        from receiving_service import parse_value
        try:
            raw=price.text().strip().replace(',','.')
            if not raw:raise ValueError('Nhập đơn giá trên phiếu trước khi lưu.')
            value=parse_value('Đơn giá',raw)
            if on_save_price is not None and on_save_price(str(value)) is not False:close_modal(page)
        except (ValueError,OSError) as exc:notice.setText(str(exc));save.setEnabled(False)
    save_price.clicked.connect(persist_price)
    price.textChanged.connect(refresh);factor.textChanged.connect(refresh);reason.textChanged.connect(refresh);refresh()

    def back():close_modal(page)

    from rec_approval_evidence import EvidencePanel,attach
    from receiving_evidence import with_history,journal
    evidence=EvidencePanel(w,with_history(w,'conversion',row,item,delivery,existing));container=form.parentWidget().layout();container.insertWidget(container.indexOf(notice),evidence)

    def accept():

        refresh()

        if 'rule' not in state:return

        try:
            rule=attach(state['rule'],evidence.persist(),existing);journal(w,'conversion',row,item,delivery,rule);on_confirm(rule);back()
        except (OSError,ValueError,KeyError) as exc:notice.setText('Chưa lưu ảnh/xác nhận: '+str(exc))

    buttons.accepted.connect(accept);buttons.rejected.connect(back)

    show_modal(w,page)

    return page

