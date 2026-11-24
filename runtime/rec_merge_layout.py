"""Table presentation for the existing manual merge controller."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QDialogButtonBox

def arrange_merge(dialog,items,panes,preview_box,search,hint,chosen,buttons):
    layout=dialog.layout()
    # Keep the original list as the selection model for the existing save path.
    items.hide();hint.hide()
    table=QTableWidget(items.count(),4);table.setObjectName('mergePagesTable')
    table.setHorizontalHeaderLabels(['Chọn','Ảnh','Nhận diện','Vai trò'])
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    table.verticalHeader().hide();table.setShowGrid(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Fixed);table.setColumnWidth(0,70)
    for i in range(items.count()):
        source=items.item(i);parts=source.text().split('\n',1)
        check=QTableWidgetItem();check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable);check.setCheckState(source.checkState());table.setItem(i,0,check)
        for j,value in enumerate([Path(source.data(Qt.UserRole)).name,parts[1] if len(parts)>1 else 'Cần đối chiếu chứng từ','Chưa chọn'],1):
            cell=QTableWidgetItem(value);cell.setToolTip(value);table.setItem(i,j,cell)
        table.setRowHeight(i,52)
    panes.insertWidget(0,table);preview_box.hide()
    def roles():
        selected=[i for i in range(items.count()) if items.item(i).checkState()==Qt.Checked]
        for i in range(items.count()):
            table.item(i,3).setText(('Trang đầu' if i==selected[0] else 'Trang tiếp') if i in selected else 'Không ghép')
    def change(cell):
        if cell.column()==0:
            items.item(cell.row()).setCheckState(cell.checkState());roles()
    table.itemChanged.connect(change)
    def sync(source):
        table.blockSignals(True);table.item(items.row(source),0).setCheckState(source.checkState());table.blockSignals(False);roles()
    items.itemChanged.connect(sync)
    table.currentCellChanged.connect(lambda row,*_:items.setCurrentRow(row))
    search.textChanged.connect(lambda text:[table.setRowHidden(i,items.item(i).isHidden()) for i in range(items.count())])
    notice=layout.itemAt(1).widget()
    notice.setText('Việc ghép ảnh phải do bạn chọn. Không gộp những dòng trùng tên trên chứng từ.')
    buttons.button(QDialogButtonBox.Save).setText('Ghép các trang đã chọn')
    buttons.button(QDialogButtonBox.Save).setMinimumWidth(200)
    items.itemChanged.connect(lambda _:buttons.button(QDialogButtonBox.Save).setText('Ghép các trang đã chọn'))
    # Secondary tools remain available in the table context menu.
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget,QVBoxLayout
    tools=QWidget();tool_layout=QVBoxLayout(tools);tool_layout.setContentsMargins(0,0,0,0);tool_layout.addWidget(search)
    search.show();tools.hide()
    table.setContextMenuPolicy(Qt.ActionsContextMenu)
    find=QAction('Tìm tên ảnh / NCC',table);find.setCheckable(True);find.toggled.connect(tools.setVisible);table.addAction(find)
    view=QAction('Xem ảnh đối chiếu',table);view.setCheckable(True);view.toggled.connect(preview_box.setVisible);table.addAction(view)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    def widths():
        available=max(table.viewport().width(),500)
        for col,ratio in enumerate([.145,.19,.30,.365]):table.setColumnWidth(col,int(available*ratio))
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0,widths)
    table.horizontalHeader().setFixedHeight(42)
    for row in range(table.rowCount()):table.setRowHeight(row,49)
    roles()
    from rec_dialog_surface import surface
    surface(dialog,'Ghép các trang của một phiếu','Chỉ ghép những ảnh thuộc cùng một chứng từ',panes,notice,buttons)
    # Place optional search above the table without occupying space by default.
    card_layout=panes.parentWidget().layout();card_layout.insertWidget(card_layout.indexOf(panes),tools)
    panes.show();table.show();items.hide();preview_box.hide()
