"""Batch result display: navigation only, never retries or posts receipts."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QDialogButtonBox,QTabWidget
from rec_pr_surface import flat_page

def show_result(w,results,day,report):
    old=getattr(w,'batch_result_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('batchResultPage');QVBoxLayout(page);w.batch_result_page=page
    rows=list(results);ok=sum(status=='Đã ghi sổ' for _,status,_ in rows)
    from rec_ledger_surface import LedgerTable,stats,SURFACE
    table=LedgerTable(len(rows),3);table.setObjectName('batchResultTable');table.setHorizontalHeaderLabels(['Phiếu','Ghi sổ','Hành động']);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setWordWrap(True)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setFixedHeight(44)
    table.setMinimumHeight(180);table.setTextElideMode(Qt.ElideNone)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.addWidget(table,1);v.setSpacing(16)
    blocked=sum(status not in ('Đã ghi sổ','Không có PR/PO') for _,status,_ in rows)
    excluded=sum(status=='Không có PR/PO' for _,status,_ in rows)
    summary=QLabel(f'Đã ghi {ok} · Còn vướng {blocked} · Không PR/PO {excluded}');summary.setObjectName('batchCompletionSummary');summary.setParent(content);summary.hide()
    heading=QLabel('Kết quả cập nhật phiếu');heading.setStyleSheet('font-size:22px;font-weight:600;color:#24334b;');v.insertWidget(0,heading)
    from datetime import date as calendar_date
    stamp=QLabel('Ngày '+calendar_date.fromisoformat(str(day)).strftime('%d/%m/%Y')+' · Kết quả ghi sổ trên máy');v.insertWidget(1,stamp)
    cards,numbers=stats([('Đã ghi sổ','#166534','#ecfdf5'),('Cần xử lý','#9a3412','#fff7ed'),('Không PR/PO','#7e22ce','#faf5ff')]);v.insertWidget(2,cards)
    for label,value in zip(numbers,[ok,blocked,excluded]):label.setText(str(value))
    sync=QLabel(getattr(w,'sheets_last_status','Sheets: chưa bắt đầu đồng bộ đợt này'));sync.setWordWrap(True);sync.setObjectName('batchSheetsStatus');v.addWidget(sync)
    def update_sync(text):
        lower=text.casefold()
        if any(t in lower for t in ['lỗi','chưa xác nhận','thất bại','chưa đồng bộ']):color,bg='#9a3412','#fff7ed'
        elif 'đang' in lower:color,bg='#5b21b6','#f5f3ff'
        elif any(t in lower for t in ['thành công','đã đồng bộ']):color,bg='#166534','#ecfdf5'
        else:color,bg='#475569','#f1f5f9'
        sync.setText('Google Sheets\n'+text);sync.setStyleSheet('font-size:13px;color:'+color+';background:'+bg+';padding:14px;border-radius:8px;')
    page.update_sync_status=update_sync;update_sync(sync.text())
    message=QLabel();message.setWordWrap(True);message.setObjectName('batchResultActionStatus');v.addWidget(message)
    message.hide()
    def notify(text):
        message.setText(text);message.show()
    def history():
        if w.busy:notify('REC đang xử lý. Chờ hoàn tất rồi mở lịch sử.');return
        w.show_shortage_ledger()
        target=getattr(w,'ledger_page',None)
        if target:
            tabs=target.findChild(QTabWidget)
            if tabs:
                for i in range(tabs.count()):
                    if tabs.tabText(i)=='Lịch sử giao hàng':tabs.setCurrentIndex(i);break
    def reload_receipt(sheet):
        if w.busy:notify('REC đang xử lý. Chờ hoàn tất rồi tải lại.');return
        if not w._leave_pr():return
        if w.day.isoformat()!=day or w.report!=report:
            notify('Ngày đang xem đã đổi. Chọn lại ngày '+day+' trước khi mở phiếu '+sheet+'.');return
        from receiving_qt import Worker
        w.set_busy(True,'Đang tải lại nguồn của '+sheet+'…')
        job=Worker(w._load_day,w.day,w.destination,w.root)
        def loaded(payload):
            if w.day.isoformat()!=day or w.report!=report:
                notify('Ngày đang xem đã đổi trong lúc tải. Chưa chuyển phiếu.');return
            w._day_loaded(payload)
            if sheet not in w.data_by_sheet:notify('Phiếu '+sheet+' không còn trong báo cáo mới. Kiểm tra lịch sử trước khi duyệt lại.');return
            w.select_sheet(sheet);w.main_pages.setCurrentWidget(w.receipt_page)
            blocked=w.fluent_nav.blockSignals(True)
            try:w.fluent_nav.set_current('Kiểm tra phiếu')
            finally:w.fluent_nav.blockSignals(blocked)
            w.statusBar().showMessage('Đã tải lại phiếu '+sheet+'. Rà nguồn và đối chiếu PR trước khi duyệt lại; chưa ghi thêm lần nhận.')
        job.signals.result.connect(loaded);job.signals.error.connect(lambda text:notify('Chưa tải lại được: '+text));job.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(job)
    for i,(sheet,status,reason) in enumerate(rows):
        success=status=='Đã ghi sổ'
        suppliers=list(dict.fromkeys(str(v.get('Nhà cung cấp') or '').strip() for _,v in w.data_by_sheet.get(sheet,[]) if v.get('Nhà cung cấp')))
        cell=QTableWidgetItem((' / '.join(suppliers)+'\n' if suppliers else '')+sheet);font=cell.font();font.setWeight(QFont.DemiBold);cell.setFont(font);table.setItem(i,0,cell)
        text='• Đã ghi sổ' if success else '• '+(reason or status)
        cell=QTableWidgetItem(text);cell.setToolTip(status+(' · '+reason if reason else ''));cell.setForeground(QColor('#178255' if success else '#b07c1b'));table.setItem(i,1,cell)
        action=QPushButton('Xem lịch sử' if success else 'Tải lại và rà');action.setObjectName('batchHistory' if success else 'batchReloadReview');action.setFixedSize(112,34)
        action.clicked.connect(history if success else lambda checked=False,s=sheet:reload_receipt(s));table.setCellWidget(i,2,action);table.setRowHeight(i,55)
    notice=QLabel()
    if not rows:notice.setText('Không có kết quả phiếu để hiển thị. Mở sổ nhận hàng để kiểm tra lịch sử; chưa tự ghi thêm phiếu nào.')
    elif ok==len(rows):notice.setText(f'Đã ghi sổ {ok}/{len(rows)} phiếu. Không ghi lại các phiếu đã thành công. Kết quả đồng bộ Sheets được báo riêng.')
    else:notice.setText(f'Đã ghi sổ {ok}/{len(rows)} phiếu. Các phiếu còn lại cần tải lại và rà; kiểm tra lịch sử nếu thao tác đã lưu một phần. Kết quả đồng bộ Sheets được báo riêng.')
    box=QDialogButtonBox(QDialogButtonBox.Save);box.button(QDialogButtonBox.Save).setText('Về sổ nhận hàng');box.accepted.connect(lambda:w.show_shortage_ledger() if not w.busy else notify('REC đang xử lý. Chờ hoàn tất rồi mở sổ.'))
    subtitle='Đã ghi sổ toàn bộ · Không ghi lại phiếu đã thành công' if rows and ok==len(rows) else 'Thành công một phần · Không ghi lại phiếu đã thành công' if ok else 'Cần rà kết quả · Không tự ghi lại'
    flat_page(page,'Kết quả ghi sổ',subtitle,content,notice,box)
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Kết quả ghi sổ':label.setText('Sổ nhận hàng / Kết quả ghi sổ')
    page.setStyleSheet(page.styleSheet()+'QWidget#batchResultPage {background:white;}')
    notice.setStyleSheet('background:'+('#ecfdf5;color:#166534;' if not blocked else '#fff7ed;color:#9a3412;')+'border-radius:9px;padding:14px;font-size:12px;')
    page.setStyleSheet(page.styleSheet()+SURFACE);page.layout().setStretch(page.layout().indexOf(content),1);table.fit_content()
    w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
