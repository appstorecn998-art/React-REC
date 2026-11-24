"""One compact form, independently scoped supplier and warehouse confirmation."""
import json
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,QComboBox,QPushButton,QMessageBox,QWidget
from rec_control_metrics import normalize

def show(w,focus='supplier'):
    if w.busy or not w.current_sheet or not w._leave_pr():return
    rows=w.data_by_sheet.get(w.current_sheet,[])
    try:directory=w.get_warehouses()
    except Exception as exc:QMessageBox.warning(w,'Không đọc được danh mục kho',str(exc));return
    from receiving_preferences import nickname
    d=QDialog(w);d.setObjectName('invoiceAssignment');d.setWindowTitle('Gán NCC và kho cho cả phiếu');d.resize(880,390)
    v=QVBoxLayout(d);v.setContentsMargins(24,24,24,24);v.setSpacing(22)
    title=QLabel('Gán NCC và kho cho cả phiếu');title.setStyleSheet('font-size:21px;font-weight:600;color:#25314b;');v.addWidget(title)
    grid=QGridLayout();grid.setHorizontalSpacing(24);grid.setVerticalSpacing(18);v.addLayout(grid)
    supplier=QComboBox();supplier.setEditable(True);supplier.setObjectName('invoiceSupplierName')
    current=sorted({str(x.get('Nhà cung cấp') or '').strip() for _,x in rows}-{''});names=set(current)
    try:names.update(x['name'] for x in json.loads((w.root/'NhaCungCap.json').read_text(encoding='utf-8-sig')).get('suppliers',[]) if x.get('name'))
    except (OSError,ValueError):pass
    supplier.addItems(sorted(names));supplier.setCurrentText(current[0] if len(current)==1 else '')
    short=QLineEdit();short.setObjectName('invoiceSupplierNickname')
    warehouse=QComboBox();warehouse.setObjectName('invoiceWarehouse');warehouse.addItem('Giữ nguyên / chưa chọn kho',None)
    for code,(name,dept) in directory.items():warehouse.addItem(f'{dept} · {name} · {code}',code)
    existing={str(x.get('Mã kho') or '') for _,x in rows}
    if len(existing)==1:
        index=warehouse.findData(next(iter(existing)))
        if index>=0:warehouse.setCurrentIndex(index)
    scope=QLineEdit(f'Tất cả {len(rows)} dòng của phiếu đang chọn');scope.setReadOnly(True)
    for i,(label,control) in enumerate([('Nhà cung cấp',supplier),('Tên hiển thị ngắn',short),('Bộ phận / kho',warehouse),('Phạm vi áp dụng',scope)]):
        wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);column.setSpacing(7)
        text=QLabel(label);text.setStyleSheet('color:#8a95a8;font-size:12px;');column.addWidget(text);column.addWidget(control);grid.addWidget(wrap,i//2,i%2)
        control.setMinimumHeight(36)
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    def short_for_supplier(*_):short.setText(nickname(w.root,supplier.currentText().strip()) if supplier.currentText().strip() else '')
    supplier.editTextChanged.connect(short_for_supplier);short_for_supplier()
    hint=QLabel('Hai xác nhận độc lập: gán NCC không đổi kho; gán kho không đổi NCC. Tên ngắn chỉ thay cách hiển thị. Sau đổi nguồn cần rà lại đối chiếu.');hint.setWordWrap(True);hint.setStyleSheet('background:#f7f5ff;color:#7968ad;border:1px solid #e7e0fb;border-radius:8px;padding:12px;');v.addWidget(hint)
    footer=QHBoxLayout();footer.addStretch();back=QPushButton('Trở lại');ncc=QPushButton('Xác nhận gán NCC');wh=QPushButton('Xác nhận gán kho');wh.setObjectName('primary')
    for button in [back,ncc,wh]:normalize(button);footer.addWidget(button)
    v.addLayout(footer);back.clicked.connect(d.reject)
    def valid(*_):ncc.setEnabled(bool(supplier.currentText().strip()));wh.setEnabled(warehouse.currentData() is not None)
    supplier.editTextChanged.connect(valid);warehouse.currentIndexChanged.connect(valid);valid()
    choice={}
    def accept(kind):
        choice.update(kind=kind,supplier=supplier.currentText().strip(),nickname=short.text(),warehouse=warehouse.currentData());d.accept()
    ncc.clicked.connect(lambda:accept('supplier'));wh.clicked.connect(lambda:accept('warehouse'))
    (warehouse if focus=='warehouse' else supplier).setFocus()
    if d.exec()!=QDialog.Accepted:return
    import receiving_service
    report,expected,sheet=w.report,w.source_hash,w.current_sheet;indices=[r for r,_ in rows]
    if choice['kind']=='supplier':
        def commit():
            result=receiving_service.mutate_invoice(report,expected,sheet,'supplier',indices,supplier_name=choice['supplier'])
            import receiving_preferences
            receiving_preferences.set_nickname(w.root,choice['supplier'],choice['nickname'])
            return result
    else:
        def commit():return receiving_service.mutate_invoice(report,expected,sheet,'warehouse',indices,choice['warehouse'],directory)
    w.write_in_background(commit)


