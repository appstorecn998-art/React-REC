"""History screen: original receipts/revisions, no quantity aggregation across PRs."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton

def install(w,host,page,tabs,source,heading,heading_note,overview,footer,inspect,remove_original,reopen_original,update_original):
    layout=QVBoxLayout(page);layout.setContentsMargins(6,8,6,12);layout.setSpacing(16);page.setObjectName('historyDesignPage')
    page.setStyleSheet('''QWidget#historyDesignPage {background:white;font-family:"Segoe UI";font-size:12px;color:#53617a;}
    QTableWidget {background:white;border:0;outline:0;color:#53617a;}
    QTableWidget::item {border:0;border-bottom:1px solid #edf0f5;padding:10px;}
    QHeaderView::section {background:white;border:0;border-bottom:1px solid #e9edf4;color:#96a0b1;padding:10px;font-size:11px;font-weight:400;}
    QPushButton {background:white;border:1px solid #e0e4ee;border-radius:7px;padding:0 12px;min-height:34px;max-height:34px;color:#59657a;}
    ''')
    table=QTableWidget(0,5);table.setObjectName('historyDesignTable');table.setHorizontalHeaderLabels(['Ngày nhận','Phiếu','PR','Món đã nhận','']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44);layout.addWidget(table)
    notice=QLabel('Sửa hoặc gỡ một lần nhận phải qua xác nhận và giữ lịch sử. Chỉ các lần nhận còn hiệu lực và nguồn đã xác minh được tính vào tổng.');notice.setWordWrap(True);notice.setStyleSheet('background:#f7f5ff;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;color:#746d9c;font-size:12px;');layout.addWidget(notice)
    upper=QHBoxLayout();upper.addStretch();reopen_button=QPushButton('PR đã ngừng chờ / mở lại');upper.addWidget(reopen_button);layout.addLayout(upper)
    lower=QHBoxLayout();lower.addStretch();remove=QPushButton('Gỡ lần nhận');update=QPushButton('Xem trước cập nhật');update.setStyleSheet('background:#6054d8;color:white;border:1px solid #6054d8;font-weight:600;');lower.addWidget(remove);lower.addWidget(update);layout.addLayout(lower)
    message=QLabel();message.setWordWrap(True);message.setObjectName('historyDesignMessage');layout.addWidget(message);layout.addStretch()
    state={'records':[]}
    def selected(row,*_):
        if row>=0:source.setCurrentCell(row,0)
        records=state['records'];remove.setEnabled(0<=row<len(records) and records[row].get('active',False))
    table.currentCellChanged.connect(selected)
    def inspect_row(row):
        if 0<=row<len(state['records']):source.setCurrentCell(row,0);inspect()
    table.cellDoubleClicked.connect(lambda row,*_:inspect_row(row))
    remove.clicked.connect(remove_original.click);update.clicked.connect(update_original.click)
    def reopen():
        row=table.currentRow()
        if not 0<=row<len(state['records']):message.setText('Chọn một lần nhận để xác định đúng PR.');return
        oid=state['records'][row]['order_id']
        # Navigate to the existing PR controller before its confirmation flow.
        from PySide6.QtWidgets import QComboBox,QCheckBox
        order=host.findChild(QComboBox,'ledgerOrderFilter');supplier=host.findChild(QComboBox,'ledgerSupplier')
        target=host.findChild(QWidget,'shortageDesignPage')
        if target is None:message.setText('Mở Chờ giao bù để chọn PR cần mở lại.');return
        tabs.setCurrentWidget(target)
        complete=next((x for x in host.findChildren(QCheckBox) if x.text()=='Hiện PR hoàn tất'),None)
        if complete:complete.setChecked(True)
        item_filter=host.findChild(QComboBox,'ledgerItemFilter')
        if item_filter:item_filter.setCurrentIndex(item_filter.findData('all'))
        found=False
        for i in range(supplier.count()):
            supplier.setCurrentIndex(i);index=order.findData(oid)
            if index>=0:order.setCurrentIndex(index);found=True;break
        if found:
            totals=host.findChild(QTableWidget,'ledgerShortages')
            if totals.rowCount():totals.setCurrentCell(0,0);reopen_original.click()
        else:message.setText('Không tìm thấy PR trong dữ liệu vừa tải. Làm mới sổ rồi kiểm tra lại.')
    # Keep the button binding separate from the function with the same purpose.
    reopen_button.clicked.connect(reopen)
    def render(records,catalog):
        from rec_table_state import begin,end
        refresh_state=begin(table,[r.get('receipt_id') or (r['report'],r['sheet']) for r in state['records']])
        state['records']=list(records);table.blockSignals(True);table.setRowCount(len(records))
        try:
            from receiving_pr_library import load
            metadata=load(w.pr_library_directory())
        except (OSError,ValueError):metadata={}
        from receiving_ledger_display import received_items
        from datetime import date
        for i,record in enumerate(records):
            oid=record['order_id'];order=catalog.get(oid,(oid,'',[]));products=received_items(record,order[2]);description='; '.join(name+': '+quantity.replace('.',',')+' '+unit for name,quantity,unit in products) or 'Không nhận thêm hàng'
            status='Đã gỡ' if not record['active'] else 'Cần kiểm tra lại nguồn' if not record['valid'] else ''
            pr=metadata.get(oid,{}).get('number') or 'Chưa rõ số PR'
            texts=[date.fromisoformat(record['day']).strftime('%d/%m/%Y'),record['sheet']+(' · '+status if status else ''),pr,description]
            for col,text in enumerate(texts):cell=QTableWidgetItem(text);cell.setToolTip(text+'\n'+str(record.get('supplier_name',''))+'\n'+str(record.get('report','')));table.setItem(i,col,cell)
            if status:table.item(i,1).setForeground(QColor('#a8374f' if record['active'] else '#7e8ba1'))
            button=QPushButton('Kiểm tra');button.setFixedSize(90,34);button.clicked.connect(lambda checked=False,row=i:inspect_row(row));table.setCellWidget(i,4,button);table.setRowHeight(i,62)
        table.setFixedHeight(min(470,44+62*max(1,len(records))+2));remove.setEnabled(False)
        end(table,[r.get('receipt_id') or (r['report'],r['sheet']) for r in records],refresh_state);selected(table.currentRow())
        message.setText('Chưa có lịch sử giao hàng.' if not records else '')
    host.render_history=render
    def tab_changed(*_):
        if tabs.currentWidget() is page:
            tabs.tabBar().hide();heading.hide();heading_note.hide();overview.hide()
            for i in range(footer.count()):
                widget=footer.itemAt(i).widget()
                if widget:widget.hide()
    tabs.currentChanged.connect(tab_changed)
