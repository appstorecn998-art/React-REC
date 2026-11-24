"""Screen 10, read from served preview.html: table left, source image right."""
from pathlib import Path
from receiving_image_archive import image_name, source_digest
from PySide6.QtCore import Qt,QEvent,QRectF,QPointF
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QLabel,QPushButton,QDialogButtonBox,QComboBox,QGridLayout,QSplitter,QStyledItemDelegate,QStyle
from rec_pr_surface import flat_page
from PySide6.QtGui import QPainter,QColor,QPen,QPolygonF

def arrange_images(dialog,listing,panel,preview,use_saved,buttons,count,owners,w=None):
    table=QTableWidget(listing.count(),3);table.setObjectName('prImagesTable')
    table.setHorizontalHeaderLabels(['Ghép','Tên ảnh PR','Đã liên kết với phiếu']);table.verticalHeader().hide();table.setShowGrid(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Fixed);table.setColumnWidth(0,58);table.setItemDelegateForColumn(0,PRCheckboxDelegate(table))
    for i in range(listing.count()):
        source=listing.item(i);path=Path(source.data(Qt.UserRole))
        cell=QTableWidgetItem();cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable);cell.setCheckState(source.checkState());cell.setToolTip('Bấm ô này để tích / bỏ tích ghép ảnh PR');table.setItem(i,0,cell)
        table.setItem(i,1,QTableWidgetItem(path.name));table.setItem(i,2,QTableWidgetItem(''));table.setRowHeight(i,49)
    def states():
        from PySide6.QtGui import QImageReader
        buttons.button(QDialogButtonBox.Save).setEnabled(all(QImageReader(str(listing.item(i).data(Qt.UserRole))).canRead() for i in range(listing.count()) if listing.item(i).checkState()==Qt.Checked))
        table.blockSignals(True)
        for i in range(listing.count()):
            source=listing.item(i);links=owners.get(image_name(source.data(Qt.UserRole)),[])
            table.item(i,0).setCheckState(source.checkState())
            text='Đã ghép: '+', '.join(links) if links else 'Chưa ghép phiếu nào'
            table.item(i,2).setText(text);table.item(i,2).setToolTip(text)
        callback=getattr(dialog,'refresh_pr_picker_summary',None)
        if callback:callback()
        table.blockSignals(False)
    table.itemChanged.connect(lambda cell:listing.item(cell.row()).setCheckState(cell.checkState()) if cell.column()==0 else None)
    listing.itemChanged.connect(lambda _:states());table.currentCellChanged.connect(lambda row,*_:listing.setCurrentRow(row))
    listing.currentRowChanged.connect(lambda row:table.setCurrentCell(row,0));states()
    body=QWidget();outer=QVBoxLayout(body);outer.setContentsMargins(0,0,0,0);outer.setSpacing(12)
    heading=QLabel('Ghép ảnh PR vào phiếu '+str(getattr(w,'current_sheet','')));heading.setStyleSheet('font-size:21px;font-weight:600;color:#26324b;');outer.addWidget(heading)
    guide=QLabel('Bấm dòng để xem ảnh. Tích ô Ghép để chọn ảnh thuộc đúng PR; có thể chọn nhiều trang của cùng một PR.');guide.setWordWrap(True);outer.addWidget(guide)
    columns=QSplitter(Qt.Horizontal);columns.setChildrenCollapsible(False);outer.addWidget(columns,1)
    left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,0,0);lv.addWidget(table,1)
    search=__import__('PySide6.QtWidgets',fromlist=['QLineEdit']).QLineEdit();search.setPlaceholderText('Tìm tên ảnh PR…');lv.insertWidget(0,search)
    mode=QComboBox();mode.setObjectName('prImageFilter');mode.addItems(['Tất cả ảnh','Ảnh đã tích chọn','Ảnh chưa ghép','Ảnh đã ghép']);lv.insertWidget(1,mode)
    selected_summary=QLabel();selected_summary.setObjectName('prPickerChosenSummary');selected_summary.setWordWrap(True);lv.addWidget(selected_summary)
    count.setStyleSheet('font-weight:600;color:#5548c3;');lv.insertWidget(0,count);count.show()
    tools=QGridLayout();use_saved.setText('Chọn PR đã có trong thư viện');tools.addWidget(use_saved,0,0,1,2)
    remove=QPushButton('Ẩn ảnh khỏi danh sách');remove.setObjectName('deletePRImage');remove.setStyleSheet('color:#b91c1c;border:1px solid #fecaca;');tools.addWidget(remove,1,0)
    restore=QPushButton('Hiện lại ảnh đã ẩn');tools.addWidget(restore,1,1);lv.addLayout(tools);columns.addWidget(left)
    removed=set();digest_cache={}
    def removed_path():return Path(w.folder)/'hidden-pr-images.json'
    if w is not None:
        import json
        try:removed.update(json.loads(removed_path().read_text(encoding='utf-8')))
        except FileNotFoundError:pass
    def key(row):
        from receiving_service import digest
        path=Path(listing.item(row).data(Qt.UserRole));stat=path.stat();stamp=(str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        if stamp not in digest_cache:digest_cache[stamp]=digest(path)
        return digest_cache[stamp]
    def filter_rows(*_):
        from rec_receipt_search import normalize
        query=normalize(search.text())
        for i in range(listing.count()):
            links=owners.get(image_name(listing.item(i).data(Qt.UserRole)),[])
            try:hidden=bool(removed) and key(i) in removed and not links
            except OSError:hidden=False
            checked=listing.item(i).checkState()==Qt.Checked
            include=mode.currentIndex()==0 or mode.currentIndex()==1 and checked or mode.currentIndex()==2 and not links or mode.currentIndex()==3 and bool(links)
            table.setRowHidden(i,hidden or not include or query not in normalize(table.item(i,1).text()))
            if hidden and listing.item(i).checkState()==Qt.Checked:listing.item(i).setCheckState(Qt.Unchecked)
        restore.setEnabled(bool(removed))
        current=listing.currentRow()
        if current<0 or table.isRowHidden(current):
            listing.setCurrentRow(next((i for i in range(table.rowCount()) if not table.isRowHidden(i)),-1))
        if listing.currentRow()<0:preview.clear_image('Không có ảnh phù hợp với bộ lọc')
    def delete_image():
        from PySide6.QtWidgets import QMessageBox
        from receiving_service import atomic_json
        row=listing.currentRow()
        if w is None or row<0 or w.busy:return
        path=listing.item(row).data(Qt.UserRole);links=owners.get(image_name(path),[])
        if links:
            QMessageBox.information(dialog,'PR đang được sử dụng','Ảnh đã ghép được giữ trong danh sách để tránh mất dấu. Phiếu đang dùng: '+', '.join(links));return
        try:
            token=key(row);updated=removed|{token};atomic_json(removed_path(),sorted(updated));removed.update(updated)
            listing.item(row).setCheckState(Qt.Unchecked);filter_rows();next_row=next((i for i in range(table.rowCount()) if not table.isRowHidden(i)),-1);listing.setCurrentRow(next_row)
            if next_row<0:preview.scene().clear()
        except (OSError,ValueError) as exc:QMessageBox.warning(dialog,'Chưa xóa được',str(exc))
    def restore_images():
        from receiving_service import atomic_json
        from PySide6.QtWidgets import QMessageBox
        if w is None:return
        try:atomic_json(removed_path(),[]);removed.clear();filter_rows()
        except OSError as exc:QMessageBox.warning(dialog,'Chưa khôi phục được',str(exc))
    remove.clicked.connect(delete_image);restore.clicked.connect(restore_images);search.textChanged.connect(filter_rows);mode.currentIndexChanged.connect(filter_rows)
    filter_rows()
    # Preserve source preview and zoom callbacks, replacing only their presentation.
    right=panel.layout()
    while right.count():
        item=right.takeAt(0)
        if item.widget():item.widget().hide()
        elif item.layout():
            while item.layout().count():
                child=item.layout().takeAt(0)
                if child.widget():child.widget().hide()
    viewing=QLabel();viewing.setObjectName('prPickerViewing');viewing.setWordWrap(True);right.addWidget(viewing)
    toggle=QPushButton();toggle.setObjectName('prPickerToggle');right.addWidget(toggle)
    right.addWidget(preview,1);preview.show();preview.setMinimumHeight(300);preview.setMaximumHeight(16777215)
    right.setStretch(2,1)
    from PySide6.QtGui import QBrush,QColor
    preview.setBackgroundBrush(QBrush(QColor('#fffcf5')))
    preview.setStyleSheet('background:#fffcf5;border:1px solid #e8e2d9;border-radius:5px;')
    bar=QHBoxLayout();page_label=QLabel();previous=QPushButton('Trước');following=QPushButton('Sau')
    bar.addWidget(page_label);bar.addStretch();
    for title,callback in [('−',lambda:preview.zoom_at(1/1.2)),('+',lambda:preview.zoom_at(1.2)),('Vừa khung',preview.fit_image)]:
        zoom=QPushButton(title);zoom.clicked.connect(callback);bar.addWidget(zoom)
    bar.addWidget(previous);bar.addWidget(following);right.addLayout(bar)
    message=QLabel();message.setWordWrap(True);right.addWidget(message)
    def page_info(*_):
        row=listing.currentRow();page_label.setText(f'Ảnh {row+1 if row>=0 else 0} / {listing.count()}')
        source=listing.item(row) if row>=0 else None;checked=source is not None and source.checkState()==Qt.Checked
        viewing.setText('Đang xem: '+Path(source.data(Qt.UserRole)).name+(' · Đã tích để ghép' if checked else ' · Chưa tích để ghép') if source else 'Chưa có ảnh để xem');toggle.setText('Bỏ tích ảnh đang xem' if checked else 'Tích ghép ảnh đang xem');toggle.setEnabled(source is not None)
        previous.setEnabled(row>0);following.setEnabled(0<=row<listing.count()-1)
        text=''
        if row<0:text='Chưa có ảnh PR. Chọn PR đã lưu hoặc thêm ảnh tại Tiếp nhận ảnh.'
        else:
            from PySide6.QtGui import QImageReader
            path=Path(listing.item(row).data(Qt.UserRole))
            if not QImageReader(str(path)).canRead():text='Ảnh nguồn không tồn tại hoặc không đọc được. Kiểm tra lại trước khi lưu ghép PR.'
        message.setText(text);message.setVisible(bool(text));message.setStyleSheet('color:#a8374f;background:#fff3f5;padding:12px;border-radius:7px;')
    def move(direction):
        row=listing.currentRow()+direction
        while 0<=row<table.rowCount():
            if not table.isRowHidden(row):listing.setCurrentRow(row);return
            row+=direction
    previous.clicked.connect(lambda:move(-1));following.clicked.connect(lambda:move(1))
    listing.currentRowChanged.connect(page_info);page_info()
    def toggle_current():
        source=listing.currentItem()
        if source:source.setCheckState(Qt.Unchecked if source.checkState()==Qt.Checked else Qt.Checked)
    toggle.clicked.connect(toggle_current)
    def update_summary():
        names=[Path(listing.item(i).data(Qt.UserRole)).name for i in range(listing.count()) if listing.item(i).checkState()==Qt.Checked]
        selected_summary.setText('Sẽ ghép: '+', '.join(names[:4])+(' và '+str(len(names)-4)+' ảnh khác' if len(names)>4 else '') if names else 'Chưa tích ảnh nào. Lưu với 0 ảnh sẽ gỡ liên kết PR hiện tại.')
        count.setText('Đã chọn '+str(len(names))+' / '+str(listing.count())+' ảnh PR')
        selected_summary.setToolTip('\n'.join(names));page_info()
        if mode.currentIndex()==1:filter_rows()
    dialog.refresh_pr_picker_summary=update_summary;update_summary()
    columns.addWidget(panel);columns.setSizes([500,900]);panel.show()
    notice=QLabel('Chỉ các ảnh đã tích mới được lưu ghép. Ảnh đang xem chưa chắc đã được chọn. Ẩn ảnh chỉ đưa ra khỏi danh sách; ảnh nguồn vẫn được giữ.')
    flat_page(dialog,'Chọn bộ ảnh PR','Xem từng trang trước khi ghép vào phiếu giao',body,notice,buttons)
    listing.hide();table.setCurrentCell(listing.currentRow(),0)
    dialog.setMinimumSize(1000,680);dialog.setStyleSheet(dialog.styleSheet()+' QTableWidget#prImagesTable {background:white;color:#334155;selection-background-color:#eeebff;} QHeaderView::section {background:#f1f5f9;color:#475569;padding:10px;font-weight:600;} QPushButton,QLineEdit,QComboBox {min-height:34px;} QLabel#prPickerViewing {font-size:14px;font-weight:600;color:#334155;} QLabel#prPickerChosenSummary {background:#f5f3ff;color:#65548a;border-radius:7px;padding:10px;} QPushButton#prPickerToggle {background:#edf4ff;border:1px solid #c9dcff;color:#1665c1;}')


class PRCheckboxDelegate(QStyledItemDelegate):
 """High-contrast checkboxes independent of inherited application indicators."""
 def paint(self,painter,option,index):
  painter.save();painter.setRenderHint(QPainter.Antialiasing)
  painter.fillRect(option.rect,QColor('#f5f3ff' if option.state & QStyle.State_Selected else 'white'))
  rect=QRectF(0,0,22,22);rect.moveCenter(QRectF(option.rect).center())
  checked=index.data(Qt.CheckStateRole) in (Qt.Checked,Qt.Checked.value)
  painter.setPen(QPen(QColor('#1765eb' if checked else '#64748b'),1.8));painter.setBrush(QColor('#1765eb' if checked else 'white'));painter.drawRoundedRect(rect,4,4)
  if checked:
   painter.setPen(QPen(QColor('white'),2.4,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
   painter.drawPolyline(QPolygonF([QPointF(rect.left()+5,rect.top()+11),QPointF(rect.left()+9,rect.top()+15),QPointF(rect.left()+17,rect.top()+7)]))
  painter.restore()
 def editorEvent(self,event,model,option,index):
  if not (index.flags() & Qt.ItemIsEnabled and index.flags() & Qt.ItemIsUserCheckable):return False
  if event.type()==QEvent.MouseButtonRelease and event.button()==Qt.LeftButton:
   if option.rect.contains(event.position().toPoint()):
    model.setData(index,Qt.Unchecked.value if index.data(Qt.CheckStateRole) in (Qt.Checked,Qt.Checked.value) else Qt.Checked.value,Qt.CheckStateRole)
   return True
  if event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonDblClick) and event.button()==Qt.LeftButton:return True
  if event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Space,Qt.Key_Select):
   if not event.isAutoRepeat():model.setData(index,Qt.Unchecked.value if index.data(Qt.CheckStateRole) in (Qt.Checked,Qt.Checked.value) else Qt.Checked.value,Qt.CheckStateRole)
   return True
  return False
