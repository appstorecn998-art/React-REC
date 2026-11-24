"""One atomic workbook write for explicit receipt time selections."""
from pathlib import Path

def apply(report,expected,sheets,value):
    import os,tempfile,shutil
    from datetime import datetime
    from openpyxl import load_workbook
    from multi_delivery import output_lock
    from receiving_service import digest,parse_value
    value=parse_value('Thời gian chụp',value)
    if not value or not sheets:raise ValueError('Chọn phiếu và nhập giờ HH:mm.')
    report=Path(report)
    with output_lock(report):
        if digest(report)!=expected:raise ValueError('Báo cáo đã đổi. Tải lại trước khi đổi giờ.')
        book=load_workbook(report);temporary=None
        try:
            for name in set(sheets):
                sheet=book[name];headers={str(c.value or '').strip():c.column for c in sheet[1]}
                if 'Thời gian chụp' not in headers:raise ValueError('Phiếu '+name+' chưa có cột Thời gian chụp.')
                for row in range(2,sheet.max_row+1):
                    if not any(sheet.cell(row,col).value is not None for col in range(1,sheet.max_column+1)):continue
                    cell=sheet.cell(row,headers['Thời gian chụp']);cell.value=value;cell.data_type='s'
            fd,temporary=tempfile.mkstemp(dir=report.parent,suffix='.xlsx');os.close(fd);book.save(temporary)
            if digest(report)!=expected:raise ValueError('Báo cáo vừa thay đổi. Chưa ghi giờ mới.')
            backup=report.parent/'.autowatcher-backups'/('bulk-time-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True);shutil.copy2(report,backup/report.name)
            os.replace(temporary,report)
        finally:
            book.close()
            if temporary:Path(temporary).unlink(missing_ok=True)

def show(w):
    if w.busy or not w.report:return
    from PySide6.QtCore import Qt,QTime
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QTimeEdit,QListWidget,QListWidgetItem,QCheckBox,QDialogButtonBox,QMessageBox
    dialog=QDialog(w);dialog.setWindowTitle('Đổi giờ chụp hàng loạt');dialog.resize(580,550);layout=QVBoxLayout(dialog)
    caption=QLabel('Chọn các phiếu trong ngày cần đổi giờ. Áp dụng cho toàn bộ dòng hàng của mỗi phiếu, không sửa ảnh gốc.');caption.setWordWrap(True);layout.addWidget(caption)
    hour=QTimeEdit();hour.setDisplayFormat('HH:mm');hour.setTime(QTime.currentTime());layout.addWidget(hour)
    all_items=QCheckBox('Chọn tất cả phiếu trong ngày');layout.addWidget(all_items)
    listing=QListWidget();listing.setObjectName('bulkTimeReceipts');layout.addWidget(listing)
    for name in w.sheet_names:
        rows=w.data_by_sheet.get(name,[]);supplier=next((str(v.get('Nhà cung cấp')) for _,v in rows if v.get('Nhà cung cấp')),'')
        item=QListWidgetItem(name+' · '+supplier);item.setData(Qt.UserRole,name);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if name==w.current_sheet else Qt.Unchecked);listing.addItem(item)
    all_items.toggled.connect(lambda checked:[listing.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked) for i in range(listing.count())])
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Save).setText('Đổi giờ các phiếu đã chọn');layout.addWidget(box);box.accepted.connect(dialog.accept);box.rejected.connect(dialog.reject)
    report=w.report;expected=w.source_hash
    if dialog.exec()!=QDialog.Accepted:return
    sheets=[listing.item(i).data(Qt.UserRole) for i in range(listing.count()) if listing.item(i).checkState()==Qt.Checked]
    if not sheets:QMessageBox.information(w,'Chưa chọn phiếu','Chọn ít nhất một phiếu cần đổi giờ.');return
    if w.report!=report or w.source_hash!=expected:QMessageBox.warning(w,'Dữ liệu đã đổi','Tải lại danh sách trước khi đổi giờ.');return
    value=hour.time().toString('HH:mm')
    w.write_in_background(lambda:apply(report,expected,sheets,value))
