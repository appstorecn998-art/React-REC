"""Read-only price details in a separate modal; leave the summary layout intact."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTableWidget,QTableWidgetItem,QLabel,QDialogButtonBox,QAbstractItemView
from PySide6.QtCore import Qt

def show(w,source,detail):
    d=QDialog(w);d.setWindowTitle('Chi tiết số lượng / giá');d.setObjectName('prPriceDetailModal');layout=QVBoxLayout(d)
    table=QTableWidget(source.rowCount(),source.columnCount());table.setObjectName('prPriceDetailTable')
    for col in range(source.columnCount()):
        header=source.horizontalHeaderItem(col)
        table.setHorizontalHeaderItem(col,QTableWidgetItem(header.text() if header else ''))
        table.setColumnWidth(col,max(100,source.columnWidth(col)))
    for row in range(source.rowCount()):
        for col in range(source.columnCount()):
            item=source.item(row,col)
            if item is not None:table.setItem(row,col,item.clone())
        table.setRowHeight(row,78)
    table.setColumnWidth(0,280);table.setColumnWidth(1,240)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(True);table.setTextElideMode(Qt.ElideNone);table.verticalHeader().hide();layout.addWidget(table,1)
    info=QLabel('Chọn dòng để xem đầy đủ kết quả và nguồn ảnh.');info.setWordWrap(True);info.setMinimumHeight(64);layout.addWidget(info)
    def select(row,col):
        source.setCurrentCell(row,0);source.cellClicked.emit(row,0);info.setText(detail.text())
    table.cellClicked.connect(select)
    box=QDialogButtonBox(QDialogButtonBox.Close);box.button(QDialogButtonBox.Close).setText('Đóng');box.rejected.connect(d.reject);layout.addWidget(box)
    d.resize(min(1150,w.width()-40),min(680,w.height()-40));d.exec()
