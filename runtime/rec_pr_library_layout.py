"""Screen 9/47: presentation adapter for the existing verified PR library."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QLabel,QGridLayout,QLineEdit,QComboBox,QCheckBox,QPushButton,QToolButton,QListView,QStyledItemDelegate,QFrame
from rec_pr_surface import flat_page

def arrange_library(dialog,search,split,listing,panel,save,note,buttons,fill):
    from rec_pr_classification import category,unclassified,UNKNOWN
    status=QComboBox();status.setObjectName('prStatusFilter');status.addItem('Tất cả trạng thái',None);status.addItem('Chưa nhận đủ',False);status.addItem('Đã nhận đủ',True)
    status.setMinimumHeight(36)
    supplier=QComboBox();supplier.setObjectName('prSupplierFilter')
    department=QComboBox();department.setObjectName('prDepartmentFilter')
    missing=QCheckBox('Chỉ PR chưa phân loại');missing.setObjectName('prUnclassifiedOnly')
    count=QLabel();count.setObjectName('prLibraryCount')
    def refresh_options():
        records=[e['record'] for e in dialog.pr_all_entries()]
        for combo,field,title in [(supplier,'supplier','Tất cả NCC'),(department,'department','Tất cả bộ phận')]:
            current=combo.currentData();combo.blockSignals(True);combo.clear();combo.addItem(title,None)
            values=sorted({category(r,field) for r in records},key=lambda v:(v!=UNKNOWN,v.casefold()))
            for value in values:combo.addItem(value,value)
            index=combo.findData(current);combo.setCurrentIndex(max(0,index));combo.blockSignals(False)
    refresh_options()
    for combo in (supplier,department):
        combo.setMinimumWidth(160);combo.setMinimumHeight(36)
    group_mode=QComboBox();group_mode.setObjectName('prBrowseBy');group_mode.addItem('Theo ngày PR','date');group_mode.addItem('Theo nhà cung cấp','supplier');group_mode.setMinimumHeight(36)
    group_picker=QComboBox();group_picker.setObjectName('prBrowseGroup');group_picker.setMinimumWidth(260);group_picker.setMinimumHeight(36)
    for combo in (group_mode,group_picker,department,status):
        view=QListView();combo.setView(view);combo.setItemDelegate(QStyledItemDelegate(view));combo.setMaxVisibleItems(10)
        view.setMaximumHeight(360);view.setUniformItemSizes(True);view.setFrameShape(QFrame.NoFrame);view.setSpacing(2)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setStyleSheet("""QListView {background:#ffffff;color:#40506c;border:1px solid #dddfea;border-radius:8px;padding:5px;outline:0;font-family:'Segoe UI';font-size:13px;}
            QListView::item {min-height:30px;padding:4px 10px;border:0;border-radius:5px;}
            QListView::item:hover {background:#f4f2ff;color:#5143bd;}
            QListView::item:selected {background:#ece8ff;color:#5143bd;}
            QScrollBar:vertical {background:#f8f9fc;width:8px;margin:4px 0;}
            QScrollBar::handle:vertical {background:#c8c8d8;min-height:28px;border-radius:4px;}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
            QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}""")
        container=view.parentWidget()
        if isinstance(container,QFrame):container.setFrameShape(QFrame.NoFrame);container.setMaximumHeight(370)
        combo.setStyleSheet('QComboBox {combobox-popup:0;background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 30px 0 10px;min-height:36px;} QComboBox:hover {border-color:#a69bdd;} QComboBox:on {border-color:#8a7bdc;}')
    def date_key(record):
        from datetime import datetime
        raw=''.join(str(record.get('date') or '').split())
        for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d'):
            try:return datetime.strptime(raw,fmt).date().isoformat()
            except ValueError:pass
        return 'Chưa rõ ngày'
    def group_key(record):
        return date_key(record) if group_mode.currentData()=='date' else category(record,'supplier')
    group_generation=[None]
    def refresh_groups(preserve=True):
        group_generation[0]=tuple(id(e['record']) for e in dialog.pr_all_entries())
        selected=group_picker.currentData() if preserve else None
        counts={}
        for entry in dialog.pr_all_entries():
            key=group_key(entry['record']);counts[key]=counts.get(key,0)+1
        if group_mode.currentData()=='date':
            keys=sorted((k for k in counts if k!='Chưa rõ ngày'),reverse=True)
            if 'Chưa rõ ngày' in counts:keys.append('Chưa rõ ngày')
        else:
            from supplier_rules import normalize_name
            keys=sorted(counts,key=lambda k:(k==UNKNOWN,normalize_name(k)))
        group_picker.blockSignals(True);group_picker.clear()
        for key in keys:
            label=key
            if group_mode.currentData()=='date':
                from datetime import date
                try:label=date.fromisoformat(key).strftime('%d/%m/%Y')
                except ValueError:pass
            group_picker.addItem(label+' · '+str(counts[key])+' PR',key)
        group_picker.setCurrentIndex(max(0,group_picker.findData(selected)));group_picker.blockSignals(False)
    refresh_groups(False)
    def matches(record):
        if group_generation[0]!=tuple(id(e['record']) for e in dialog.pr_all_entries()):refresh_groups()
        return group_key(record)==group_picker.currentData() and (not supplier.currentData() or category(record,'supplier')==supplier.currentData()) and (not department.currentData() or category(record,'department')==department.currentData()) and (not missing.isChecked() or unclassified(record)) and (status.currentData() is None or next((e['complete'] for e in dialog.pr_all_entries() if e['record'] is record),False)==status.currentData())
    dialog.pr_category_match=matches
    row_map={};reverse_map={};rebuilding=[False]

    table=QTableWidget(0,4);table.setObjectName('prLibraryTable');table.setToolTip('Bấm một lần để xem PR · Bấm đúp để mở phiếu giao liên quan')
    table.setHorizontalHeaderLabels(['Số PR','Nhà cung cấp','Ngày PR','Trạng thái'])
    table.setWordWrap(False);table.setTextElideMode(Qt.ElideRight);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for col,width in ((0,85),(2,105)):
        table.horizontalHeader().setSectionResizeMode(col,QHeaderView.Fixed);table.setColumnWidth(col,width)
    table.verticalHeader().setDefaultSectionSize(44)
    listing.hide();split.insertWidget(0,table);split.setSizes([780,0,470])
    source_notice=QLabel();source_notice.setWordWrap(True);source_notice.setStyleSheet('color:#a8374f;background:#fff3f5;border:1px solid #f4d7df;border-radius:7px;padding:12px;');source_notice.hide()
    def sync(*_):
        if rebuilding[0]:return
        rebuilding[0]=True
        vertical=table.verticalScrollBar().value();horizontal=table.horizontalScrollBar().value()
        refresh_options()
        refresh_groups()
        table.blockSignals(True);table.clearSpans();table.setRowCount(0);row_map.clear();reverse_map.clear()
        current_row=-1
        indices=list(range(listing.count()))
        from supplier_rules import normalize_name
        indices.sort(key=lambda i:normalize_name(category(listing.item(i).data(Qt.UserRole)['record'],'supplier')))
        indices.sort(key=lambda i:date_key(listing.item(i).data(Qt.UserRole)['record']) if date_key(listing.item(i).data(Qt.UserRole)['record'])!='Chưa rõ ngày' else '',reverse=True)
        for i in indices:
            entry=listing.item(i).data(Qt.UserRole);r=entry['record']
            row=table.rowCount();table.insertRow(row);row_map[row]=i;reverse_map[i]=row
            values=['PR '+(r.get('number') or 'Chưa rõ'),category(r,'supplier'),r.get('date') or 'Chưa rõ',entry['status']]
            detail=' · '.join(filter(None,[category(r,'department'),entry.get('duplicate_note'),entry.get('suggestion_reason')]))
            for col,text in enumerate(values):
                item=QTableWidgetItem(text);item.setToolTip(text+('\n'+detail if detail else ''));table.setItem(row,col,item)
                if col==3:item.setForeground(QColor('#007c5b' if entry['complete'] else '#a56800'))
            table.setRowHeight(row,44)
            if i==listing.currentRow():current_row=row
        table.setCurrentCell(current_row,0);table.verticalScrollBar().setValue(vertical);table.horizontalScrollBar().setValue(horizontal);table.blockSignals(False);rebuilding[0]=False
        count.setText(str(listing.count())+' / '+str(len(dialog.pr_all_entries()))+' PR · '+str(sum(unclassified(e['record']) for e in dialog.pr_all_entries()))+' chưa phân loại')
        save.setEnabled(listing.currentItem() is not None)
        entry=listing.currentItem().data(Qt.UserRole) if listing.currentItem() else None
        message=''
        if not entry:message='Không có PR phù hợp. Đổi từ khóa hoặc chọn ảnh PR mới.'
        else:
            import receiving_pr_library as library
            try:library.images_for(entry['record'])
            except (OSError,ValueError) as exc:message=str(exc)
        source_notice.setText(message);source_notice.setVisible(bool(message))
        getattr(dialog,'refresh_pr_details',lambda:None)()
    def selection_changed(*_):
        if rebuilding[0]:return
        # Selecting a PR changes only its highlight and preview, never the model.
        row=reverse_map.get(listing.currentRow(),-1)
        if table.currentRow()!=row:
            blocked=table.blockSignals(True);table.setCurrentCell(row,0);table.blockSignals(blocked)
        save.setEnabled(listing.currentItem() is not None)
        getattr(dialog,'refresh_pr_details',lambda:None)()
    listing.currentRowChanged.connect(selection_changed)
    def choose_row(row,*_):
        if rebuilding[0]:return
        index=row_map.get(row)
        if index is not None and listing.currentRow()!=index:listing.setCurrentRow(index)
    table.cellClicked.connect(choose_row)
    table.activated.connect(lambda index:choose_row(index.row()))
    table.currentCellChanged.connect(lambda row,*_:choose_row(row) if table.hasFocus() else None)
    dialog.sync_library_view=sync
    listing.setVisible(False)
    toolbar=QWidget();row=QHBoxLayout(toolbar);row.setContentsMargins(0,0,0,0);row.addWidget(search,1)
    search.setMinimumHeight(36);search.setClearButtonEnabled(True);search.setPlaceholderText('Tìm PR trong nhóm đang chọn…')
    supplier.hide();row.insertWidget(0,group_mode);row.insertWidget(1,group_picker);row.addWidget(status)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(10);
    heading=QLabel('Thư viện PR');heading.setStyleSheet('font-size:22px;font-weight:600;color:#26324b;');v.addWidget(heading)

    v.addWidget(toolbar)
    filters=QHBoxLayout();filters.addWidget(department);filters.addWidget(missing);filters.addStretch();filters.addWidget(count);v.addLayout(filters);v.addWidget(split,1)
    for control in [supplier,department,status]:control.currentIndexChanged.connect(lambda *_:fill())
    def change_group_mode(*_):
        refresh_groups(False);fill()
    group_mode.currentIndexChanged.connect(change_group_mode)
    group_picker.currentIndexChanged.connect(lambda *_:fill())
    missing.toggled.connect(fill)
    reset=QPushButton('Xóa lọc');reset.setObjectName('prClearFilters');filters.insertWidget(2,reset)
    def clear_filters():
        from PySide6.QtCore import QSignalBlocker
        controls=[search,supplier,department,status,missing];blocks=[QSignalBlocker(c) for c in controls]
        search.clear();supplier.setCurrentIndex(0);department.setCurrentIndex(0);status.setCurrentIndex(0);missing.setChecked(False)
        del blocks
        fill()
    reset.clicked.connect(clear_filters)
    note.hide();right=panel.layout();right.setContentsMargins(12,0,0,0);right.setSpacing(8)
    # The approved form is two columns with each label above its input.
    form=right.itemAt(2).layout()
    grid=QGridLayout();grid.setHorizontalSpacing(10);grid.setVerticalSpacing(8)
    for i,(field,label) in enumerate([('number','Số PR'),('supplier','NCC'),('date','Ngày PR'),('department','Bộ phận')]):
        edit=panel.findChild(QLineEdit,'prMeta_'+field);form.removeWidget(edit)
        wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);column.setSpacing(7)
        caption=QLabel(label);caption.setStyleSheet('font-size:11px;color:#7b869a;');column.addWidget(caption);column.addWidget(edit);grid.addWidget(wrap,i//2,i%2)
        edit.setFixedHeight(38)
        if field in ('supplier','department'):edit.setPlaceholderText('Chưa phân loại — nhập thông tin rồi lưu')
    while form.count():
        item=form.takeAt(0)
        if item.widget():item.widget().hide()
    right.removeItem(form)
    metadata=QWidget();metadata.setLayout(grid);metadata.hide()
    edit_toggle=QToolButton();edit_toggle.setObjectName('prEditMetadata');edit_toggle.setText('Sửa thông tin PR');edit_toggle.setCheckable(True);edit_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);edit_toggle.setArrowType(Qt.RightArrow)
    def toggle_metadata(opened):
        metadata.setVisible(opened);save.setVisible(opened);edit_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
    edit_toggle.toggled.connect(toggle_metadata)
    right.insertWidget(2,metadata);save.hide()
    pagebar=right.itemAt(1).layout()
    right.removeItem(pagebar);pagebar.setParent(None)
    pages=QWidget();pages.setLayout(pagebar);right.insertWidget(1,pages);pages.hide()
    preview=right.itemAt(0).widget();preview.setMinimumHeight(200)
    from PySide6.QtGui import QBrush
    preview.setBackgroundBrush(QBrush(QColor('#fffcf5')))
    preview.setStyleSheet('border:1px solid #e8e2d9;border-radius:5px;')
    right.insertWidget(0,source_notice)
    save.setSizePolicy(__import__('PySide6.QtWidgets',fromlist=['QSizePolicy']).QSizePolicy.Fixed,save.sizePolicy().verticalPolicy())
    save.setText('Lưu thông tin');save.setFixedHeight(36)
    right.removeWidget(save);grid.addWidget(save,2,0,1,2)
    tools=QHBoxLayout();tools.addStretch();tools.addWidget(edit_toggle)
    enlarge=next(pagebar.itemAt(i).widget() for i in range(pagebar.count()) if pagebar.itemAt(i).widget() and pagebar.itemAt(i).widget().objectName()=='enlargePRImage')
    pagebar.removeWidget(enlarge);tools.addWidget(enlarge);enlarge.show()
    assign=QPushButton('Ghép PR này vào phiếu…');assign.setObjectName('assignPRToReceipt')
    assign.setStyleSheet('QPushButton {background:#6054d8;color:white;border:1px solid #6054d8;border-radius:7px;min-height:36px;padding:0 12px;}')
    tools.addWidget(assign)
    def assign_selected():
        item=listing.currentItem()
        if not item:return
        owner=dialog.library_owner
        if not owner.current_sheet or not owner.report:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(dialog,'Chọn phiếu giao','Chọn phiếu giao cần ghép PR trước rồi mở lại thư viện.');return
        from rec_pr_assign_picker import show
        show(owner,selected_key=item.data(Qt.UserRole)['key'])
    assign.clicked.connect(assign_selected)
    right.insertLayout(0,tools)
    def open_receipt(row,*_):
        index=row_map.get(row)
        if index is None:return
        entry=listing.item(index).data(Qt.UserRole)
        __import__('rec_pr_receipts_page').show(dialog.library_owner,entry['key'],direct=True)
    table.cellDoubleClicked.connect(open_receipt)
    notice=QLabel('')
    buttons.button(QDialogButtonBox.Ok).hide();buttons.button(QDialogButtonBox.Cancel).hide()
    view=buttons.addButton('Xem các trang',QDialogButtonBox.ActionRole);view.clicked.connect(lambda:__import__('rec_pr_pages_page').show(dialog.library_owner,listing.currentItem().data(Qt.UserRole)['key']) if listing.currentItem() else None)
    buttons.button(QDialogButtonBox.Cancel).hide()
    flat_page(dialog,'Thư viện PR','Tìm PR cũ / đang giao dở trước khi nhận lần tiếp theo',content,notice,buttons)
    buttons.hide()
    buttons.parentWidget().hide()
    buttons.removeButton(view);tools.insertWidget(1,view)
    notice.hide();panel.show();split.setSizes([780,0,470]);split.setCollapsible(0,False);split.setCollapsible(2,False);dialog.setMinimumSize(0,0)
    details=QLabel();details.setObjectName('prSelectedDetails');details.setWordWrap(True);details.setStyleSheet('color:#64748b;padding:4px 0;');right.insertWidget(1,details)
    right.removeWidget(metadata);right.insertWidget(3,metadata)
    def show_details(*_):
        entry=listing.currentItem().data(Qt.UserRole) if listing.currentItem() else None
        view.setEnabled(entry is not None)
        assign.setEnabled(entry is not None and not getattr(dialog.library_owner,'busy',False))
        assign.setToolTip('Chọn phiếu đích và kiểm tra ảnh trong hộp xác nhận; chưa ghi liên kết khi chỉ chọn PR.')
        view.setVisible(bool(entry and len(entry['record'].get('images',{}))>1))
        if not entry:
            details.setText('Chọn PR để xem ảnh và thông tin');return
        r=entry['record'];details.setText('PR '+(r.get('number') or 'Chưa rõ')+' · '+category(r,'supplier')+'\n'+(r.get('date') or 'Chưa rõ ngày')+' · '+category(r,'department')+'\n'+entry['status']+('\n'+entry['duplicate_note'] if entry.get('duplicate_note') else '')+('\nGợi ý: '+entry['suggestion_reason'] if entry.get('suggestion_reason') else ''))
        if unclassified(r):edit_toggle.setChecked(True)
    dialog.refresh_pr_details=show_details
    listing.currentRowChanged.connect(show_details)
    fill();sync();show_details()
    dialog.setStyleSheet(dialog.styleSheet()+' QTableWidget#prLibraryTable::item {padding:6px 10px;}')
    for label in dialog.findChildren(QLabel):
        if label.text()=='Rà soát / Thư viện PR':label.setText('PR & đối chiếu / Thư viện PR')
