"""Compact PR-to-delivery assignment form with conflict validation."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QGridLayout,QWidget,QLabel,QLineEdit,QComboBox,QDialogButtonBox
from rec_dialog_surface import surface

def choose(parent,item,choice,rows,occupied):
    d=QDialog(parent);d.setObjectName('prMappingDialog');d.setWindowTitle('Gán dòng PR với dòng giao');QVBoxLayout(d)
    form=QWidget();grid=QGridLayout(form);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(18)
    name=str(item.get('item_name') or 'Hàng PR đang chọn')
    if item.get('source_line') is not None:name+=' · PR dòng '+str(item['source_line'])
    pr=QLineEdit(name);pr.setReadOnly(True);pr.setObjectName('mappingPRLine')
    selection=QComboBox();selection.setObjectName('mappingDeliveryLine')
    values=dict(rows)
    for i in range(choice.count()):
        value=choice.itemData(i)
        text='Chưa xác định' if value=='unknown' else 'Không giao trong phiếu này' if value is None else choice.itemText(i)
        if isinstance(value,int) and value in values:
            row=values[value];qty=row.get('Thực nhận');unit=row.get('Đơn vị trên phiếu') or row.get('Đơn vị tính') or ''
            text=f"Dòng {value-1} · {row.get('Tên hàng trên phiếu (Ảnh)','')}"+(f" · {str(qty).replace('.',',')} {unit}" if qty is not None else '')
        selection.addItem(text,value)
    selection.setCurrentIndex(choice.currentIndex())
    for col,(label,control) in enumerate([('Hàng PR đang chọn',pr),('Dòng giao được chọn',selection)]):
        caption=QLabel(label);caption.setStyleSheet('font-size:11px;color:#7b869a;');grid.addWidget(caption,0,col);grid.addWidget(control,1,col);grid.setColumnStretch(col,1)
        control.setFixedHeight(38);control.setStyleSheet('background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;font-size:13px;')
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('Áp dụng dòng đã chọn');buttons.button(QDialogButtonBox.Cancel).setText('Hủy');buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject)
    normal='Lưu cặp đã gán chỉ nhớ đúng NCC, tên và quy cách đã xác nhận; không suy rộng sang NCC khác.'
    notice=QLabel(normal)
    surface(d,'Gán dòng PR với dòng giao','Chọn rõ một dòng hoặc “Không giao trong phiếu này”',form,notice,buttons)
    for label in d.findChildren(QLabel):
        if label.text()=='Rà soát / Gán dòng PR với dòng giao':label.setText('PR & đối chiếu / Gán dòng PR với dòng giao')
    normal_style=notice.styleSheet()
    def validate(*_):
        conflict=selection.currentData() in occupied
        buttons.button(QDialogButtonBox.Save).setEnabled(not conflict)
        notice.setText('Dòng giao này đã được dùng cho một dòng PR khác. Bỏ gán ở dòng cũ trước khi chuyển sang dòng này.' if conflict else normal)
        notice.setStyleSheet('background:#fff3f5;color:#a8374f;border:1px solid #f1d7df;border-radius:9px;padding:15px;font-size:12px;' if conflict else normal_style)
    selection.currentIndexChanged.connect(validate);validate();d.resize(880,min(620,d.layout().totalHeightForWidth(880) if d.layout().hasHeightForWidth() else d.sizeHint().height()))
    return selection.currentIndex() if d.exec()==QDialog.Accepted else None
