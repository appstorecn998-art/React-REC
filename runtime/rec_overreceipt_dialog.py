"""Explicit approval of indivisible excess; recorded with the comparison decision."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QDialogButtonBox,QMessageBox
from receiving_overreceipt import approve
from receiving_units import exact_text


def show(parent,row,item,delivery,entry,ordered,received,on_apply,previous=0):
    dialog=QDialog(parent);dialog.setWindowTitle('Duyệt nhận dư · Yêu cầu bổ sung PR');dialog.resize(560,350)
    layout=QVBoxLayout(dialog)
    from fractions import Fraction
    total=Fraction(str(received))+Fraction(str(previous))
    text=QLabel(str(item.get('item_name',''))+'\nPR: '+exact_text(ordered)+' · Thực nhận: '+exact_text(received)+' · Đã nhận trước: '+exact_text(previous)+' · Tổng dư: '+exact_text(total-Fraction(str(ordered)))+' '+str(item.get('unit','')))
    text.setWordWrap(True);layout.addWidget(text)
    old=entry.get('overreceipt_approval') or {}
    layout.addWidget(QLabel('Người xác nhận nhận dư'))
    person=QLineEdit(old.get('person',''));person.setObjectName('overreceiptPerson');layout.addWidget(person)
    layout.addWidget(QLabel('Lý do'))
    reason=QPlainTextEdit(old.get('reason','Hàng nguyên khối, không thể chia đúng lượng đặt'));reason.setObjectName('overreceiptReason');layout.addWidget(reason)
    note=QLabel('Giữ nguyên lượng PR và thực nhận. Khi ghi sổ và đồng bộ Google Sheets, dòng này sẽ hiện “Chờ bộ phận bổ sung PR” kèm lượng dư và lý do.');note.setWordWrap(True);layout.addWidget(note)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Save).setText('Duyệt nhận dư');layout.addWidget(box)
    remove=box.addButton('Bỏ duyệt',QDialogButtonBox.ActionRole);remove.setEnabled(bool(old))
    def accept():
        try:rule=approve(row,item,delivery,entry,ordered,received,person.text(),reason.toPlainText(),previous)
        except ValueError as exc:QMessageBox.warning(dialog,'Chưa duyệt',str(exc));return
        on_apply(rule);dialog.accept()
    box.accepted.connect(accept);box.rejected.connect(dialog.reject)
    remove.clicked.connect(lambda:(on_apply(None),dialog.accept()))
    dialog.exec()
