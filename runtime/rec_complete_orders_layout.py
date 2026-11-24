"""Completed PRs: require every line verified, exactly received, with no closure."""
from fractions import Fraction
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton
from receiving_units import exact_text

def install(w,host,page,tabs,heading,heading_note,overview,footer,order_choice,supplier_choice,show_complete,item_filter,source,inspect):
    layout=QVBoxLayout(page);layout.setContentsMargins(6,8,6,12);layout.setSpacing(16);page.setObjectName('completeOrdersPage')
    page.setStyleSheet('''QWidget#completeOrdersPage {background:white;font-family:"Segoe UI";color:#53617a;font-size:12px;}
    QTableWidget {background:white;border:0;outline:0;color:#53617a;}
    QTableWidget::item {padding:10px;border:0;border-bottom:1px solid #edf0f5;}
    QHeaderView::section {background:white;color:#96a0b1;font-size:11px;font-weight:400;padding:10px;border:0;border-bottom:1px solid #e9edf4;}
    QLineEdit,QComboBox {background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;min-height:36px;max-height:36px;}
    QPushButton {background:white;color:#59657a;border:1px solid #e0e4ee;border-radius:7px;padding:0 12px;min-height:34px;max-height:34px;}
    QPushButton:disabled {color:#b2b7c4;border-color:#edf0f5;}
    ''')
    arrow=Path(__file__).with_name('design-combo-arrow.svg').as_posix()
    page.setStyleSheet(page.styleSheet()+f'QComboBox::drop-down {{border:0;width:24px;}} QComboBox::down-arrow {{image:url("{arrow}");width:10px;height:6px;}}')
    toolbar=QHBoxLayout();search=QLineEdit();search.setPlaceholderText('Tìm PR / NCC');search.setObjectName('completeSearch');supplier=QComboBox();supplier.setObjectName('completeSupplier');supplier.setMinimumWidth(230);toolbar.addWidget(search,1);toolbar.addWidget(supplier);layout.addLayout(toolbar)
    table=QTableWidget(0,5);table.setObjectName('completeOrdersTable');table.setHorizontalHeaderLabels(['PR','Mặt hàng','Đặt','Đã nhận','Còn thiếu']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44);layout.addWidget(table)
    message=QLabel();message.setObjectName('completeMessage');message.setWordWrap(True);layout.addWidget(message)
    notice=QLabel('PR đã chốt hủy phần còn thiếu không được xếp như nhận đủ. Nguồn chưa xác minh được chuyển vào Cần xử lý.');notice.setWordWrap(True);notice.setStyleSheet('background:#f7f5ff;border:1px solid #e8e3ff;border-radius:9px;color:#746d9c;padding:14px 16px;font-size:12px;');layout.addWidget(notice)
    buttons=QHBoxLayout();buttons.addStretch();history=QPushButton('Lịch sử lần nhận');check=QPushButton('Kiểm tra nguồn');buttons.addWidget(history);buttons.addWidget(check);layout.addLayout(buttons);layout.addStretch()
    state={'all':[],'visible':[],'records':[]}
    def selection(*_):
        enabled=0<=table.currentRow()<len(state['visible']);history.setEnabled(enabled);check.setEnabled(enabled)
    table.itemSelectionChanged.connect(selection)
    def fill(*_):
        from rec_table_state import begin,end
        refresh_state=begin(table,[(r['order_id'],r['index']) for r in state['visible']])
        query=search.text().strip().casefold();wanted=supplier.currentData();rows=[r for r in state['all'] if (wanted is None or r['supplier']==wanted) and (not query or query in (r['pr']+' '+r['supplier']).casefold())];state['visible']=rows
        table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            fmt=lambda value:exact_text(Fraction(str(value))).replace('.',',')+' '+row['unit']
            for col,text in enumerate([row['pr'],row['name'],fmt(row['ordered']),fmt(row['received']),fmt(row['remaining'])]):
                cell=QTableWidgetItem(text);cell.setToolTip(row['supplier']+' · '+text);table.setItem(i,col,cell)
            table.setRowHeight(i,51)
        table.setFixedHeight(min(470,44+51*max(1,len(rows))+2));message.setText('Không có PR đã nhận đủ phù hợp.' if not rows else '');end(table,[(r['order_id'],r['index']) for r in rows],refresh_state);selection()
    def render(summary,catalog,suppliers,records):
        groups={}
        for row in summary:groups.setdefault(row['order_id'],[]).append(row)
        try:
            from receiving_pr_library import load
            metadata=load(w.pr_library_directory())
        except (OSError,ValueError):metadata={}
        eligible=[]
        for oid,rows in groups.items():
            lines=catalog.get(oid,(None,None,[]))[2]
            if not lines or len(rows)!=len(lines) or {r['index'] for r in rows}!=set(range(len(lines))):continue
            if any(r['remaining'] is None or Fraction(str(r['remaining']))!=0 or r.get('reason') or Fraction(str(r['received']))!=Fraction(str(r['ordered'])) for r in rows):continue
            meta=metadata.get(oid,{});title=meta.get('number') or 'Chưa rõ số PR'
            eligible.extend(dict(row,supplier=suppliers.get(oid,'Chưa rõ NCC'),pr=title) for row in rows)
        state.update(all=eligible,records=list(records));previous=supplier.currentData();supplier.blockSignals(True);supplier.clear();supplier.addItem('Tất cả NCC',None)
        for name in sorted({r['supplier'] for r in eligible}):supplier.addItem(name,name)
        index=supplier.findData(previous);supplier.setCurrentIndex(max(0,index));supplier.blockSignals(False);fill()
    search.textChanged.connect(fill);supplier.currentIndexChanged.connect(fill)
    def selected():
        i=table.currentRow();return state['visible'][i] if 0<=i<len(state['visible']) else None
    def show_history():
        row=selected()
        if row is None:return
        matches=[(i,r) for i,r in enumerate(state['records']) if r['order_id']==row['order_id'] and r.get('active')]
        for i in range(tabs.count()):
            if tabs.tabText(i)=='Lịch sử giao hàng':
                tabs.setCurrentIndex(i);view=tabs.currentWidget().findChild(QTableWidget,'historyDesignTable')
                if view and matches:view.setCurrentCell(matches[0][0],0)
                break
    def show_source():
        row=selected()
        if row is None:return
        matches=[r for r in state['records'] if r['order_id']==row['order_id'] and r.get('active') and Fraction(str(r.get('allocations',{}).get(str(row['index']),'0')))>0]
        if not matches:message.setText('Không có lần nhận có lượng dương của đúng mặt hàng này.');return
        if len(matches)>1:show_history();return
        from rec_receipt_source_page import show
        show(w,matches[0])
    history.clicked.connect(show_history);check.clicked.connect(show_source)
    def switched(*_):
        if tabs.currentWidget() is page:
            tabs.tabBar().hide();heading.hide();heading_note.hide();overview.hide()
            for i in range(footer.count()):
                widget=footer.itemAt(i).widget()
                if widget:widget.hide()
    tabs.currentChanged.connect(switched);host.render_complete=render;fill()
