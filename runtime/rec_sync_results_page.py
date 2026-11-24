"""Design30: read-only outbox inspection, retry only when pending work exists."""
import sqlite3,json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox
from rec_pr_surface import flat_page

def read_events(path):
    if not Path(path).exists():return []
    conn=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        return [dict(id=i,receipt_id=rid,revision=rev,state=state,time=time,error=error,sheet=json.loads(raw).get('sheet',rid)) for i,rid,rev,state,time,error,raw in conn.execute("SELECT s.id,s.receipt_id,s.revision,s.state,s.created,s.error,r.payload FROM sync_outbox s LEFT JOIN receipts r ON r.id=s.receipt_id ORDER BY s.created DESC").fetchall() for raw in [raw or '{}']]
    finally:conn.close()

def show(w,manual_result=None):
    page=getattr(w,'sync_results_page',None)
    if page is not None:
        if manual_result is not None:page.manual_result=manual_result
        page.refresh_events();w.main_pages.setCurrentWidget(page);return page
    page=QWidget();page.setObjectName('syncResultsPage');QVBoxLayout(page);w.sync_results_page=page;page.manual_result=manual_result
    table=QTableWidget(0,3);table.setObjectName('syncResultsTable');table.setHorizontalHeaderLabels(['Sự kiện','Trạng thái','Xử lý']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(16)
    warning=QLabel();warning.setObjectName('syncPendingBanner');warning.setWordWrap(True);warning.hide();warning.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;');v.addWidget(warning);v.addWidget(table);status=QLabel();status.setObjectName('syncResultsStatus');status.setWordWrap(True);v.addWidget(status)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);retry=box.button(QDialogButtonBox.Save);retry.setText('Thử lại đồng bộ');box.button(QDialogButtonBox.Cancel).setText('Kiểm tra cấu hình');box.rejected.connect(lambda:w.fluent_nav.set_current('Cài đặt'))
    back=box.addButton('Trở lại',QDialogButtonBox.ActionRole);back.clicked.connect(lambda:w.show_shortage_ledger() if not w.busy else None)
    notice=QLabel('Thử lại chỉ xử lý sự kiện chưa hoàn tất. Không tự ghi lại số lượng vào ledger. Không lặp vô hạn.')
    flat_page(page,'Kết quả đồng bộ và thử lại','Đã ghi sổ không có nghĩa là đã gửi thành công lên Sheets',content,notice,box);notice.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;font-size:12px;');page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#syncResultsPage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Kết quả đồng bộ và thử lại':label.setText('Xuất & đồng bộ / Kết quả đồng bộ và thử lại')
    def refresh():
        try:events=read_events(w.ledger_path())
        except (OSError,ValueError,sqlite3.Error) as exc:status.setText('Chưa đọc được trạng thái đồng bộ: '+str(exc));retry.setEnabled(False);return
        table.setRowCount(len(events));pending=0
        for i,event in enumerate(events):
            synced=event['state']=='synced';pending+=not synced
            values=[event['sheet']+' · revision '+str(event['revision']),'• Đã đồng bộ' if synced else '• Chờ / lỗi','Giữ kết quả' if synced else event['error'] or 'Kiểm tra kết nối rồi thử lại']
            for j,text in enumerate(values):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,j,cell)
            table.item(i,1).setForeground(QColor('#178255' if synced else '#b07c1b'));table.setRowHeight(i,57)
        table.setFixedHeight(min(450,44+57*max(1,len(events))+2));warning.setVisible(bool(pending));warning.setText('Sheets chưa đồng bộ\nSổ đã lưu trên máy; còn sự kiện chờ gửi hoặc gặp lỗi. Kiểm tra kết nối rồi thử lại, không ghi lại lượng vào sổ.');content.setFixedHeight(table.height()+75+(100 if pending else 0));retry.setEnabled(bool(pending) and not getattr(w,'sheets_sync_running',False) and not w.busy)
        status.setText((page.manual_result+'\n' if page.manual_result else '')+(getattr(w,'sheets_last_status','')+'\n' if getattr(w,'sheets_last_status','') else '')+(f'{pending} sự kiện đang chờ.' if events else 'Chưa có sự kiện đồng bộ trong sổ.'))
    def submit():
        refresh()
        if not retry.isEnabled():return
        retry.setEnabled(False);__import__('rec_auto_sheets').start(w);refresh()
    box.accepted.connect(submit);page.refresh_events=refresh;refresh();w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
