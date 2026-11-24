"""Screen20 Tất cả phiếu: source-backed compact register, original row actions retained."""
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton

def parse_date(text):
    raw=text.strip()
    if not raw:return ''
    for fmt in ['%Y-%m-%d','%d/%m/%Y']:
        try:return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:pass
    return 'invalid'

def search_text(record,catalog):
    parts=[record.get('supplier',''),record.get('sheet',''),record.get('day','')]
    for _,row in record.get('rows',[]):parts.extend(str(row.get(k) or '') for k in ['Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống','Mã vật tư'])
    receipt=record.get('record') or {};order=catalog.get(receipt.get('order_id'))
    if order:
        parts.append(str(order[1]));parts.extend(str(line.get('name') or '') for line in order[2])
    return ' '.join(parts).casefold()

def install(w,host,page,tabs,source,search,date_from,date_to,mode,old_note,heading,old_heading_note,overview,footer,inspect,audit):
    layout=page.layout()
    while layout.count():
        item=layout.takeAt(0)
        if item.widget():item.widget().hide()
    layout.setContentsMargins(6,8,6,12);layout.setSpacing(16)
    page.setObjectName('registerDesignPage')
    page.setStyleSheet('''QWidget#registerDesignPage {background:white;font-family:"Segoe UI";font-size:12px;color:#53617a;}
    QTableWidget#registerDesignTable {border:0;background:white;color:#53617a;outline:0;}
    QTableWidget#registerDesignTable::item {border:0;border-bottom:1px solid #edf0f5;padding:10px;}
    QHeaderView::section {background:white;border:0;border-bottom:1px solid #e9edf4;padding:10px;color:#96a0b1;font-size:11px;font-weight:400;}
    QPushButton,QComboBox {background:white;border:1px solid #e0e4ee;color:#59657a;border-radius:7px;padding:0 12px;min-height:34px;max-height:34px;}
    QLineEdit {background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;min-height:36px;max-height:36px;}
    ''')
    from rec_ledger_surface import LedgerTable,stats,SURFACE
    title=QLabel('Sổ nhận hàng');title.setStyleSheet('font-size:22px;font-weight:600;color:#24334b;');layout.addWidget(title)
    cards,counts=stats([('Phiếu hiển thị','#334155','#f1f5f9'),('Đã ghi sổ','#166534','#ecfdf5'),('Cần xử lý','#9a3412','#fff7ed'),('Không PR/PO','#7e22ce','#faf5ff')]);layout.addWidget(cards)
    page.setStyleSheet(page.styleSheet()+SURFACE)
    toolbar=QHBoxLayout();toolbar.setSpacing(10);search.setPlaceholderText('Tìm NCC / tên hàng');toolbar.addWidget(search,1);search.show()
    for edit,placeholder in [(date_from,'Từ ngày DD/MM/YYYY'),(date_to,'Đến ngày DD/MM/YYYY')]:edit.setPlaceholderText(placeholder);edit.setFixedWidth(180);toolbar.addWidget(edit);edit.show()
    mode.insertItem(1,'Cần xử lý','attention');toolbar.addWidget(mode);mode.show();layout.addLayout(toolbar)
    view=LedgerTable(0,5);view.column_weights=[.10,.27,.36,.15,.12];view.setObjectName('registerDesignTable');view.setHorizontalHeaderLabels(['Ngày','NCC / PR','Món nhận lần này','Trạng thái','']);view.verticalHeader().hide();view.setShowGrid(False);view.setWordWrap(True);view.setEditTriggers(QAbstractItemView.NoEditTriggers);view.setSelectionBehavior(QAbstractItemView.SelectRows);view.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed);view.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);view.horizontalHeader().setFixedHeight(44);layout.addWidget(view,1)
    message=QLabel();message.setObjectName('registerDesignMessage');message.setWordWrap(True);layout.addWidget(message)
    actions=QHBoxLayout();actions.addStretch();batch=QPushButton('Duyệt ghi sổ');batch.setObjectName('registerBatchApprove');batch.clicked.connect(w.refresh_all_pr);actions.addWidget(batch);audit_action=QPushButton('Rà soát dữ liệu');audit_action.clicked.connect(audit.click);actions.addWidget(audit_action);layout.addLayout(actions)
    batch.setStyleSheet('background:#6054d8;color:white;border:1px solid #6054d8;font-weight:600;')
    state={'rows':[]}
    def activate(index):
        if not 0<=index<len(state['rows']):return
        source.setCurrentCell(index,0);inspect()
    def render(rows,catalog):
        from rec_table_state import begin,end as finish_refresh
        key=lambda r:(r.get('report'),r.get('sheet'),r.get('day'))
        refresh_state=begin(view,[key(r) for r in state['rows']])
        start=parse_date(date_from.text());end=parse_date(date_to.text());invalid=start=='invalid' or end=='invalid' or bool(start and end and start>end)
        rows=[] if invalid else list(rows);state['rows']=rows;view.setRowCount(len(rows));view.setMinimumHeight(220)
        for label,value in zip(counts,[len(rows),sum(r['status']=='Đã ghi sổ' for r in rows),sum(r['status'] in ('Chưa ghi sổ','Cần kiểm tra lại') for r in rows),sum(r['status']=='Không có PR/PO' for r in rows)]):label.setText(str(value))
        try:
            from receiving_pr_library import load
            library_orders=load(w.pr_library_directory())
        except (OSError,ValueError):library_orders={}
        for i,r in enumerate(rows):
            receipt=r.get('record') or {};order=catalog.get(receipt.get('order_id'));supplier=r.get('supplier') or 'Chưa rõ NCC'
            if order:
                meta=library_orders.get(receipt.get('order_id'),{})
                supplier+=' · PR '+str(meta.get('number') or 'chưa rõ số')
            products=[]
            if order and receipt:
                from receiving_ledger_display import received_items
                products=[name+': '+qty+' '+unit for name,qty,unit in received_items(receipt,order[2])]
            elif r.get('rows'):
                for _,line in r['rows']:
                    quantity=line.get('Thực nhận');products.append(str(line.get('Tên hàng trên phiếu (Ảnh)') or line.get('Tên chuẩn hệ thống') or '')+': '+('Chưa xác định' if quantity is None else str(quantity).replace('.',',')+' '+str(line.get('Đơn vị trên phiếu') or line.get('Đơn vị tính') or '')))
            description='; '.join(products) or 'Chưa đủ dữ liệu món nhận · '+str(r.get('count',0))+' dòng'
            texts=[datetime.strptime(r['day'],'%Y-%m-%d').strftime('%d/%m/%Y'),supplier+'\n'+str(r.get('sheet') or ''),description,'• '+r['status']]
            for col,text in enumerate(texts):cell=QTableWidgetItem(text);cell.setToolTip(text);view.setItem(i,col,cell)
            color={'Đã ghi sổ':'#178255','Không có PR/PO':'#8a5ac0','Chưa ghi sổ':'#b07c1b','Cần kiểm tra lại':'#a8374f'}.get(r['status'],'#7e8ba1');view.item(i,3).setForeground(QColor(color))
            action=QPushButton('Chi tiết' if r['status']=='Đã ghi sổ' else 'Theo dõi' if r['status']=='Không có PR/PO' else 'Mở phiếu');action.setFixedSize(95,34);action.clicked.connect(lambda checked=False,index=i:activate(index));view.setCellWidget(i,4,action);view.setRowHeight(i,64)
        view.setTextElideMode(Qt.ElideNone);view.fit_content()
        finish_refresh(view,[key(r) for r in rows],refresh_state)
        message.setText('Ngày lọc không hợp lệ. Nhập DD/MM/YYYY; ngày bắt đầu không được sau ngày kết thúc.' if invalid else 'Không tìm thấy phiếu phù hợp. Đổi từ khóa, khoảng ngày hoặc trạng thái.' if not rows else '')
        message.setStyleSheet('color:#a56800;font-size:12px;')
    host.render_register=render
    host.register_load_state=message.setText
    view.cellDoubleClicked.connect(lambda row,*_:activate(row))
    def tab_changed(*_):
        showing=tabs.currentWidget() is page
        tabs.tabBar().setVisible(not showing)
        heading.setVisible(not showing);old_heading_note.setVisible(not showing);overview.setVisible(not showing)
        for i in range(footer.count()):
            widget=footer.itemAt(i).widget()
            if widget:widget.setVisible(not showing)
    tabs.currentChanged.connect(tab_changed);tab_changed();source.hide();old_note.hide()
