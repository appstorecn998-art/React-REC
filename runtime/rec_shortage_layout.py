"""Chờ giao bù: one supplier and one PR, four source-backed quantity columns."""
from fractions import Fraction
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QSplitter,QInputDialog,QMessageBox,QScrollArea,QFrame,QSizePolicy

from rec_ledger_surface import LedgerTable
class ShortageItemsTable(LedgerTable):
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.setColumnWidth(0,max(280,self.viewport().width()-480))


def install(w,host,page,complete_page,tabs,supplier,show_complete,item_filter,order_choice,order_list,source,summary,heading,heading_note,overview,footer,inspect,stop):
    for hidden in [order_choice,order_list,source]:hidden.setParent(host);hidden.hide()
    layout=page.layout()
    while layout.count():
        node=layout.takeAt(0)
        if node.widget():node.widget().hide()
        elif node.layout():
            child=node.layout()
            while child.count():
                x=child.takeAt(0)
                if x.widget():x.widget().hide()
    layout.setContentsMargins(6,8,6,12);layout.setSpacing(16);page.setObjectName('shortageDesignPage')
    page.setStyleSheet('''QWidget#shortageDesignPage {background:white;font-family:"Segoe UI";font-size:12px;color:#53617a;}
    QTableWidget {background:white;border:0;outline:0;color:#53617a;}
    QTableWidget::item {border:0;border-bottom:1px solid #edf0f5;padding:10px;}
    QHeaderView::section {background:white;color:#96a0b1;border:0;border-bottom:1px solid #e9edf4;padding:10px;font-size:11px;font-weight:400;}
    QPushButton,QComboBox {background:white;border:1px solid #e0e4ee;border-radius:7px;padding:0 12px;min-height:34px;max-height:34px;color:#59657a;}
    ''')
    from rec_ledger_surface import LedgerTable,stats,SURFACE
    page.setStyleSheet(page.styleSheet()+SURFACE)
    title=QLabel('Chờ giao bù');title.setStyleSheet('font-size:22px;font-weight:600;color:#24334b;');layout.addWidget(title)
    subtitle=QLabel('Chọn NCC và PR để theo dõi giao bù · Số món thống kê theo PR đang chọn');subtitle.setWordWrap(True);layout.addWidget(subtitle)
    cards,counts=stats([('PR trong danh sách','#334155','#f1f5f9'),('Món còn thiếu','#9a3412','#fff7ed'),('Món cần rà','#b91c1c','#fef2f2'),('Món đã ngừng','#7e22ce','#faf5ff')]);layout.addWidget(cards)
    supplier_caption=QLabel();supplier_caption.setObjectName('shortageSupplierCaption');supplier_caption.setWordWrap(True);supplier_caption.setTextInteractionFlags(Qt.TextSelectableByMouse);supplier_caption.setStyleSheet('font-weight:600;font-size:14px;color:#334155;');layout.addWidget(supplier_caption)
    def supplier_changed(*_):supplier_caption.setText(supplier.currentText());supplier.setToolTip(supplier.currentText())
    supplier.currentTextChanged.connect(supplier_changed);supplier_changed()
    toolbar=QHBoxLayout();toolbar.setSpacing(10);supplier.setMinimumWidth(320);supplier.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed);supplier.view().setMinimumWidth(650);toolbar.addWidget(supplier,1);supplier.show();show_complete.setText('Hiện PR hoàn tất');toolbar.addWidget(show_complete);show_complete.show();item_filter.setMinimumWidth(205);toolbar.addWidget(item_filter);item_filter.show();toolbar.addStretch();layout.addLayout(toolbar)
    for key,text in [('all','Mặt hàng: Tất cả'),('short','Còn thiếu'),('complete','Đã đủ'),('over','Nhận dư'),('unknown','Nguồn cần cập nhật'),('stopped','Đã ngừng giao bù')]:item_filter.setItemText(item_filter.findData(key),text)
    split=QSplitter(Qt.Horizontal);layout.addWidget(split,1)
    orders=LedgerTable(0,2);orders.setObjectName('shortageOrdersTable');orders.setHorizontalHeaderLabels(['PR','Trạng thái']);split.addWidget(orders)
    right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(0,0,0,0);rv.setSpacing(14)
    totals=ShortageItemsTable(0,5);totals.setObjectName('shortageItemsTable');totals.setHorizontalHeaderLabels(['Mặt hàng','Đặt','Đã nhận','Còn thiếu thực tế','Theo dõi']);rv.addWidget(totals,1)
    actions=QHBoxLayout();actions.setContentsMargins(0,0,0,0);actions.setSpacing(8);receipts=QPushButton('Xem lần nhận');close=QPushButton('Ngừng cả PR…');completed=QPushButton('Xem PR đã đủ')
    stop_items=QPushButton('Ngừng giao bù…');stop_items.setObjectName('stopSelectedItems')
    reopen_items=QPushButton('Tiếp tục nhận…');reopen_items.setObjectName('reopenSelectedItems')
    for button in [receipts,stop_items,reopen_items,close,completed]:actions.addWidget(button)
    actions_host=QWidget();actions_host.setLayout(actions);actions_scroll=QScrollArea();actions_scroll.setWidget(actions_host);actions_scroll.setWidgetResizable(True);actions_scroll.setFrameShape(QFrame.NoFrame);actions_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);actions_scroll.setFixedHeight(58);rv.addWidget(actions_scroll)
    for button in [receipts,stop_items,reopen_items,close,completed]:
        button.ensurePolished();button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text())+38)
    stop_items.setToolTip('Ngừng giao bù các món đang chọn, có ghi lý do');reopen_items.setToolTip('Tiếp tục nhận các món đã ngừng đang chọn');close.setStyleSheet('color:#b91c1c;border:1px solid #fecaca;')
    split.addWidget(right);split.setChildrenCollapsible(False);split.setSizes([330,1000])
    for table in [orders,totals]:
        table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setTextElideMode(Qt.ElideNone);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
    totals.setSelectionMode(QAbstractItemView.ExtendedSelection)
    totals.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive);totals.setColumnWidth(0,360)
    for col,width in [(1,90),(2,100),(3,130),(4,160)]:totals.horizontalHeader().setSectionResizeMode(col,QHeaderView.Fixed);totals.setColumnWidth(col,width)
    message=QLabel();message.setObjectName('shortageDesignMessage');message.setWordWrap(True);layout.addWidget(message)
    notice=QLabel('Chọn một hoặc nhiều món (Ctrl/Shift) rồi Ngừng món đã chọn. Bấm đúp để xem lần nhận. Ngừng cả PR áp dụng cho toàn bộ đơn; số thực nhận luôn được giữ.');notice.setWordWrap(True);notice.setStyleSheet('background:#f7f5ff;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;color:#746d9c;font-size:12px;');layout.addWidget(notice)
    state={'rows':[],'group':[]}
    def render(rows,group=None):
        from rec_table_state import begin,end
        refresh_state=begin(totals,[(r['order_id'],r['index']) for r in state['rows']])
        state['group']=list(group if group is not None else rows)
        state['rows']=list(rows)
        group_rows=state['group']
        metrics=[order_list.count(),sum(r['remaining'] is not None and Fraction(r['remaining'])>0 and not r.get('item_stopped') and not r.get('reason') for r in group_rows),sum(r['remaining'] is None for r in group_rows),sum(bool(r.get('item_stopped') or r.get('reason')) for r in group_rows)]
        for label,value in zip(counts,metrics):label.setText(str(value))
        supplier_changed()
        orders.blockSignals(True);orders.setRowCount(order_list.count())
        try:
            from receiving_pr_library import load
            metadata=load(w.pr_library_directory())
        except (OSError,ValueError):metadata={}
        for i in range(order_list.count()):
            item=order_list.item(i);oid=item.data(Qt.UserRole);meta=metadata.get(oid,{})
            title='PR '+(meta.get('number') or 'Chưa rõ số')+('\n'+meta['date'] if meta.get('date') else '')+('\n'+meta['department'] if meta.get('department') else '')
            if not meta:title='PR chưa rõ số · '+str(i+1)
            status=item.text().split('\n')[1].split(' · ')[0] if '\n' in item.text() else ''
            for col,text in enumerate([title,'• '+status]):cell=QTableWidgetItem(text);cell.setToolTip(item.toolTip()+'\n'+item.text());orders.setItem(i,col,cell)
            orders.item(i,1).setForeground(item.foreground());orders.setRowHeight(i,51)
        if order_choice.currentIndex()>=0:orders.setCurrentCell(order_choice.currentIndex(),0)
        orders.blockSignals(False);totals.setRowCount(len(rows))
        for i,r in enumerate(rows):
            unit=str(r['unit']).strip().capitalize();unknown=r['remaining'] is None;remaining=None if unknown else Fraction(r['remaining'])
            values=[r['name'],str(r['ordered'])+' '+unit,('Đã ghi '+str(r.get('recorded_received',r['received']))+' '+unit+' · Chưa xác minh') if unknown else str(r['received'])+' '+unit,'Chưa xác minh' if unknown else 'Nhận dư '+str(-remaining)+' '+unit if remaining<0 else __import__('receiving_units').exact_text(remaining).replace('.',',')+' '+unit]
            if r.get('item_stopped'):values[3]=str(r.get('physical_remaining') or '—')+' '+unit
            values.append('Đã ngừng' if r.get('item_stopped') else 'Ngừng cả PR' if r.get('reason') else 'Nguồn cần rà' if unknown else 'Chờ giao bù' if remaining>0 else 'Đã đủ')
            for col,text in enumerate(values):cell=QTableWidgetItem(text);cell.setToolTip(r.get('status','')+(' · '+r['reason'] if r.get('reason') else ''));totals.setItem(i,col,cell)
            totals.item(i,3).setForeground(QColor('#b07c1b' if unknown or remaining>0 else '#8a5ac0' if remaining<0 else '#178255'));totals.setRowHeight(i,57)
        totals.resizeRowsToContents()
        for i in range(totals.rowCount()):totals.setRowHeight(i,max(57,totals.rowHeight(i)))
        end(totals,[(r['order_id'],r['index']) for r in rows],refresh_state)
        select_item(totals.currentRow());update_selection()
        orders.fit_content();totals.fit_content();split.setMinimumHeight(240)
        message.setText('Chưa có PR phù hợp. Đổi NCC hoặc bật Hiện PR hoàn tất.' if not order_list.count() else 'Không có mặt hàng khớp bộ lọc.' if not rows else '')
        receipts.setEnabled(bool(rows));close.setEnabled(bool(rows) and not any(r['remaining'] is None for r in rows));completed.setEnabled(bool(order_list.count()))
    def select_item(row,*_):
        if row>=0:source.setCurrentCell(row,0)
    orders.currentCellChanged.connect(lambda row,*_:order_choice.setCurrentIndex(row) if row>=0 else None);totals.currentCellChanged.connect(select_item)
    totals.cellDoubleClicked.connect(lambda row,*_:(source.setCurrentCell(row,0),inspect()))
    def selected():
        return [state['rows'][index.row()] for index in totals.selectionModel().selectedRows() if index.row()<len(state['rows'])]
    saving=[False]
    def update_selection():
        if saving[0]:return
        rows=selected()
        stop_items.setEnabled(bool(rows) and all(not r.get('item_stopped') and not r.get('reason') and r['remaining'] is not None and Fraction(r['remaining'])>0 for r in rows))
        reopen_items.setEnabled(bool(rows) and all(r.get('item_stopped') for r in rows))
    totals.itemSelectionChanged.connect(update_selection);update_selection()
    feedback=QLabel();feedback.setObjectName('itemClosureFeedback');feedback.setWordWrap(True);feedback.hide();layout.insertWidget(2,feedback)
    def show_feedback(text,error=False):
        feedback.setText(text);feedback.setStyleSheet('padding:10px 14px;border-radius:7px;background:'+('#fff1f2;color:#b42318;' if error else '#f0f8f4;color:#176548;'));feedback.show()
    def change_items(reopen=False):
        if saving[0]:return
        rows=selected()
        if not rows:return
        oid=rows[0]['order_id']
        if any(r['order_id']!=oid for r in rows):return
        title='Nhận tiếp món đã chọn' if reopen else 'Ngừng giao bù món đã chọn'
        names='\n'.join(r['name'] for r in rows)
        from PySide6.QtWidgets import QDialog,QPlainTextEdit,QDialogButtonBox
        from rec_approval_evidence import EvidencePanel
        from receiving_evidence import audit_images
        dialog=QDialog(w);dialog.setWindowTitle(title);layout=QVBoxLayout(dialog);label=QLabel(names+'\nNgười/bộ phận xác nhận và lý do:');label.setWordWrap(True);layout.addWidget(label)
        field=QPlainTextEdit();field.setMaximumHeight(90);layout.addWidget(field)
        history={'attachment_history':[]}
        for r in rows:history['attachment_history'].extend(audit_images(w.ledger_path(),'item:'+oid+':'+str(r['index'])).get('attachment_history',[]))
        evidence=EvidencePanel(w,history);layout.addWidget(evidence);box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(box);box.accepted.connect(dialog.accept);box.rejected.connect(dialog.reject);dialog.resize(750,530)
        if dialog.exec()!=QDialog.Accepted:return
        reason=field.toPlainText().strip()
        if not reason:
            show_feedback('Chưa lưu: cần nhập người/bộ phận xác nhận và lý do.',True);return
        from receiving_item_closure import set_items,line_key
        from receiving_qt import Worker
        from shiboken6 import isValid
        path=w.ledger_path();indices=[r['index'] for r in rows];expected={str(r['index']):line_key(r) for r in rows}
        try:attachments=evidence.persist()
        except (ValueError,OSError) as exc:
            show_feedback('Chưa lưu: '+str(exc),True);return
        saving[0]=True
        for control in (stop_items,reopen_items,close):control.setEnabled(False)
        show_feedback('Đang lưu quyết định cho '+str(len(rows))+' món…')
        def work():
            set_items(path,oid,indices,reason,reopen,expected=expected,attachments=attachments)
            return len(indices)
        def ready(count):
            if not isValid(page):return
            text=('Đã mở lại giao bù' if reopen else 'Đã ngừng giao bù')+' cho '+str(count)+' món. Số thực nhận giữ nguyên. Đang cập nhật bảng…'
            show_feedback(text)
            w.show_top_notice('Đã lưu quyết định giao bù',text)
            if w.ledger_path()==path:
                host.item_closure_refresh_done=lambda:show_feedback(('Đã mở lại giao bù' if reopen else 'Đã ngừng giao bù')+' cho '+str(count)+' món. Đã cập nhật bảng; số thực nhận giữ nguyên.') if isValid(page) else None
                w.ledger_refresh()
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0,lambda:__import__('rec_auto_sheets').start(w) if isValid(w) and w.ledger_path()==path else None)
        def failed(message):
            if isValid(page):show_feedback('Chưa lưu quyết định: '+message,True)
        def finished():
            saving[0]=False
            if isValid(page):
                update_selection();close.setEnabled(bool(state['rows']))
        task=Worker(work);task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished);w._start_worker(task)
    stop_items.clicked.connect(lambda:change_items(False));reopen_items.clicked.connect(lambda:change_items(True))
    def inspect_row():
        if totals.currentRow()<0 and totals.rowCount():totals.setCurrentCell(0,0)
        inspect()
    receipts.clicked.connect(inspect_row)
    def close_order():
        row=totals.currentRow()
        if row<0 and totals.rowCount():row=0;totals.setCurrentCell(0,0)
        if row<0 or row>=len(state['rows']):return
        selected=state['rows'][row];oid=selected['order_id']
        same=[r for r in state['group'] if r['order_id']==oid]
        from rec_close_order_page import open_page
        open_page(w,oid,selected.get('title') or oid,same,lambda changed:None)
    close.clicked.connect(close_order)
    def show_completed():tabs.setCurrentWidget(complete_page)
    completed.clicked.connect(show_completed)
    def page_changed(*_):
        active=tabs.currentWidget() in [page,complete_page]
        if active:
            tabs.tabBar().hide();heading.hide();heading_note.hide();overview.hide()
            for i in range(footer.count()):
                widget=footer.itemAt(i).widget()
                if widget:widget.hide()
    tabs.currentChanged.connect(page_changed);host.render_shortage=render
