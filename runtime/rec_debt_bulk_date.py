"""Explicit atomic date edits in the debt workspace."""
from datetime import datetime
from pathlib import Path
import re,os,tempfile,shutil
from openpyxl import load_workbook
from receiving_service import parse_value,digest
from multi_delivery import output_lock

def parse_date(value):
    value=value.strip()
    if re.fullmatch(r'\d{1,2}/\d{1,2}',value):value+='/2026'
    return parse_value('Ngày nhận hàng xác nhận',value)

def apply(report,expected,selection,field,value):
    if field not in ('Ngày nhận hàng xác nhận','Ngày giao hàng'):raise ValueError('Chọn loại ngày cần đổi.')
    value=parse_date(value)
    if not value or not selection or not any(selection.values()):raise ValueError('Chọn phiếu/dòng và nhập ngày.')
    report=Path(report)
    with output_lock(report):
        if digest(report)!=expected:raise ValueError('Báo cáo đã đổi. Tải lại trước khi đổi ngày.')
        book=load_workbook(report);tmp=None;count=0
        try:
            for name,rows in selection.items():
                sheet=book[name];headers={str(c.value or '').strip():c.column for c in sheet[1]}
                if field not in headers:raise ValueError('Phiếu '+name+' thiếu cột '+field)
                for row in set(rows):
                    if row<2 or row>sheet.max_row or not sheet.cell(row,headers['Tên hàng trên phiếu (Ảnh)']).value:raise ValueError('Dòng đã đổi. Tải lại trước khi lưu.')
                    cell=sheet.cell(row,headers[field]);cell.value=value;cell.data_type='s';count+=1
            fd,tmp=tempfile.mkstemp(dir=report.parent,suffix='.xlsx');os.close(fd);book.save(tmp)
            if digest(report)!=expected:raise ValueError('Báo cáo đổi trong khi lưu. Chưa ghi ngày mới.')
            backup=report.parent/'.autowatcher-backups'/('bulk-date-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True);shutil.copy2(report,backup/report.name);os.replace(tmp,report)
            return count
        finally:
            book.close()
            if tmp:Path(tmp).unlink(missing_ok=True)

def show(w):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QComboBox,QLineEdit,QLabel,QListWidget,QListWidgetItem,QCheckBox,QDialogButtonBox,QMessageBox
    from receiving_qt import Worker
    if w.saving or not w.report or not w.receipts.currentData():return
    dialog=QDialog(w);dialog.setWindowTitle('Đổi ngày hàng loạt');dialog.resize(700,570);layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
    field=QComboBox();field.addItems(['Ngày nhận hàng xác nhận','Ngày giao hàng']);form.addRow('Đổi cột',field)
    value=QLineEdit();value.setPlaceholderText('dd/mm — mặc định năm 2026, ví dụ 03/11');form.addRow('Ngày / tháng',value)
    mode=QComboBox();mode.addItem('Các phiếu chọn bên dưới','sheets');selected=[w.model.source_row(i.row()) for i in w.table.selectionModel().selectedRows()]
    if selected:mode.addItem('Chỉ các dòng đang chọn trong phiếu hiện tại','rows')
    form.addRow('Phạm vi',mode)
    all_items=QCheckBox('Chọn tất cả phiếu trong nhóm ngày');layout.addWidget(all_items)
    listing=QListWidget();listing.setObjectName('bulkDateReceipts');layout.addWidget(listing,1)
    for i in range(w.receipts.count()):
        name=w.receipts.itemData(i);item=QListWidgetItem(w.receipts.itemText(i));item.setData(Qt.UserRole,name);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if name==w.receipts.currentData() else Qt.Unchecked);listing.addItem(item)
    all_items.toggled.connect(lambda checked:[listing.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked) for i in range(listing.count())])
    def scope():listing.setEnabled(mode.currentData()=='sheets');all_items.setEnabled(mode.currentData()=='sheets')
    mode.currentIndexChanged.connect(scope)
    note=QLabel('Chỉ đổi cột ngày đã chọn; không chuyển thư mục nhóm ngày hay sửa ngày trong ảnh gốc.');note.setWordWrap(True);layout.addWidget(note)
    error=QLabel();layout.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('Áp dụng ngày');layout.addWidget(buttons)
    chosen={}
    def accept():
        try:
            parsed=parse_date(value.text())
            if not parsed:raise ValueError('Nhập ngày/tháng, ví dụ 03/11.')
            selection={w.receipts.currentData():selected} if mode.currentData()=='rows' else {listing.item(i).data(Qt.UserRole):[r for r,_ in w.data[listing.item(i).data(Qt.UserRole)]] for i in range(listing.count()) if listing.item(i).checkState()==Qt.Checked}
            count=sum(map(len,selection.values()))
            if not count:raise ValueError('Chọn ít nhất một phiếu hoặc dòng.')
            if QMessageBox.question(dialog,'Xác nhận đổi ngày',f'{field.currentText()} → {parsed}\\nÁp dụng {count} dòng trong {len(selection)} phiếu?')!=QMessageBox.Yes:return
            chosen.update(selection=selection,value=parsed,field=field.currentText());dialog.accept()
        except ValueError as exc:error.setText(str(exc))
    buttons.accepted.connect(accept);buttons.rejected.connect(dialog.reject)
    report,expected,day=w.report,w.expected,w.day
    if dialog.exec()!=QDialog.Accepted:return
    w.set_busy(True,'Đang đổi ngày hàng loạt…');task=Worker(apply,report,expected,chosen['selection'],chosen['field'],chosen['value'])
    def done(count):w.load_day(day);w.page.feedback(f'Đã đổi {chosen["field"]} thành {chosen["value"]} cho {count} dòng.','success')
    task.signals.result.connect(done);task.signals.error.connect(lambda message:w.page.feedback('Chưa đổi được ngày: '+message,'error'));task.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(task)
