"""Design29 adapter retaining preview-first Sheets service boundaries."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLineEdit,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QPushButton,QMenu,QHBoxLayout,QScrollArea,QFrame
from rec_pr_surface import flat_page

def build(w,page):
    QVBoxLayout(page);content=QWidget();content.setObjectName('sheetsContent');v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18)
    heading=QLabel('Đồng bộ Google Sheets');heading.setStyleSheet('font-size:22px;font-weight:600;color:#26324b;');v.addWidget(heading)
    intro=QLabel('Đưa dữ liệu từ sổ nhận hàng trong REC lên Google Sheets.');intro.setWordWrap(True);v.addWidget(intro)
    steps=QLabel('1. Tải bản xem trước   →   2. Kiểm tra thay đổi   →   3. Xác nhận đồng bộ');steps.setWordWrap(True);steps.setStyleSheet('font-weight:600;color:#6054d8;padding:8px 0;');v.addWidget(steps)
    banner=QLabel('Bắt đầu bằng nút Tải / làm mới xem trước bên dưới. REC sẽ kiểm tra sổ nhận hàng và đọc Google Sheets để tìm các thay đổi. Chỉ cập nhật Sheets sau khi bạn xác nhận.');banner.setWordWrap(True);banner.setStyleSheet('background:#f7f5ff;color:#746d9c;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;');v.addWidget(banner)
    overview=QTableWidget(3,3);overview.setObjectName('sheetsSources');overview.setHorizontalHeaderLabels(['Loại dữ liệu','Số lượng / thay đổi','Trạng thái'])
    for i,values in enumerate([('Dữ liệu từ sổ nhận hàng','Chưa kiểm tra','Chờ tải xem trước'),('Dữ liệu cần kiểm tra lại','Chưa kiểm tra','Chờ tải xem trước'),('Dòng và ghi chú nhập tay trên Sheets','Được giữ theo quy tắc đồng bộ','Không tự ghi đè')]):
        for j,text in enumerate(values):overview.setItem(i,j,QTableWidgetItem(text))
        overview.setRowHeight(i,42)
    overview.setFixedHeight(174);v.addWidget(overview)
    grid=QGridLayout();grid.setHorizontalSpacing(18)
    target=QLineEdit();target.setReadOnly(True);last=QLineEdit();last.setReadOnly(True)
    try:config=json.loads((w.root/'.receiving/runtime.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):config={}
    target.setText('Google Sheets · '+str(config.get('sheet_id') or 'Theo cấu hình REC'))
    last.setText(getattr(w,'sheets_last_status','Chưa có thông tin đồng bộ trong phiên này'))
    for col,(text,field) in enumerate([('Bảng đích',target),('Lần đồng bộ gần nhất',last)]):
        wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);label=QLabel(text);label.setStyleSheet('color:#7b869a;font-size:11px;');column.addWidget(label);column.addWidget(field);grid.addWidget(wrap,0,col);grid.setColumnStretch(col,1)
    v.addLayout(grid)
    page.summary=QLabel('Chưa có dữ liệu xem trước');page.summary.setWordWrap(True);page.summary.setStyleSheet('font-size:16px;font-weight:600;color:#334155;');v.addWidget(page.summary);page.status=QLabel('Bước 1: Bấm Tải / làm mới xem trước. Thao tác này chỉ đọc dữ liệu, chưa ghi lên Google Sheets.');page.status.setWordWrap(True);v.addWidget(page.status)
    page.table=QTableWidget(0,6);page.table.setObjectName('sheetsPreview');page.table.setHorizontalHeaderLabels(['Tab / Nhà cung cấp','Mặt hàng','ĐVT','Còn thiếu','Ghi chú','Thao tác']);v.addWidget(page.table)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);page.save=box.button(QDialogButtonBox.Save);page.save.setText('3. Xác nhận đồng bộ');page.save.setEnabled(False);page.save.setToolTip('Chỉ bật sau khi tải thành công bản xem trước có thay đổi.');box.button(QDialogButtonBox.Cancel).setText('Về sổ nhận hàng')
    page.reload=QPushButton('1. Tải / làm mới xem trước');page.reload.setObjectName('sheetsLoadPreview');page.reload.setMinimumHeight(40)
    page.reload.setStyleSheet('background:#6054d8;color:white;border:1px solid #6054d8;border-radius:8px;padding:8px 18px;font-weight:600;')
    results=QPushButton('Xem kết quả đồng bộ');results.clicked.connect(lambda:__import__('rec_sync_results_page').show(w))
    actions=QHBoxLayout();actions.addWidget(page.reload);actions.addWidget(results);actions.addStretch();v.insertLayout(4,actions)
    detail_heading=QLabel('2. Các thay đổi sẽ gửi lên Sheets');detail_heading.setStyleSheet('font-size:16px;font-weight:600;color:#334155;');v.insertWidget(v.indexOf(page.table),detail_heading)
    box.accepted.connect(lambda:page.submit() if page.submit else None);box.rejected.connect(w.show_shortage_ledger);page.reload.clicked.connect(lambda:__import__('rec_sheets_page').show_page(w,True))
    notice=QLabel('Xác nhận chỉ gửi các thay đổi đã xem trước. Dòng nhập tay và ghi chú được giữ theo quy tắc đồng bộ hiện có.')
    flat_page(page,'Xem trước Google Sheets','Chọn dữ liệu → xem thay đổi → xác nhận đồng bộ',content,notice,box);notice.show()
    page.setStyleSheet(page.styleSheet()+'QWidget#sheetsPage,QWidget#sheetsContent,QScrollArea {background:white;} QLabel {color:#53617a;} QPushButton#sheetsLoadPreview:disabled {background:#e9e6f7;color:#8b83ab;border-color:#e9e6f7;}');page.layout().removeWidget(content)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setWidget(content);page.layout().insertWidget(0,scroll,1)
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Xem trước Google Sheets':label.setText('Xuất & đồng bộ / Xem trước Google Sheets')
    for table in [overview,page.table]:
        table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
    page.table.setMinimumHeight(160);page.table.setMaximumHeight(300)
    def snapshot(summary,records):
        good=sum(bool(r.get('active') and r.get('valid')) for r in records);bad=sum(bool(r.get('active') and not r.get('valid')) for r in records)
        overview.item(0,1).setText(str(good)+' lần nhận đã xác minh');overview.item(0,2).setText('Sẵn sàng xem trước' if good else 'Không có lần nhận hợp lệ')
        overview.item(1,1).setText(str(bad)+' lần nhận cần rà');overview.item(1,2).setText('Cần rà' if bad else 'Không có nguồn lỗi')
    def planned(preview):
        overview.item(0,1).setText(str(len(preview['changes']))+' thay đổi · '+str(sum(p.get('create',False) for p in preview.get('parts',[])))+' tab mới');overview.item(0,2).setText('Sẵn sàng' if preview['changes'] else 'Không có thay đổi')
        from PySide6.QtGui import QColor
        overview.item(0,2).setForeground(QColor('#178255' if preview['changes'] else '#7e8ba1'));overview.item(1,2).setForeground(QColor('#b07c1b' if preview.get('skipped') else '#7e8ba1'));overview.item(2,2).setForeground(QColor('#7e8ba1'))
        overview.item(1,1).setText(str(preview.get('skipped',0))+' dòng chưa đủ điều kiện');overview.item(1,2).setText('Cần rà' if preview.get('skipped') else 'Không có dòng bị bỏ qua')
    from PySide6.QtWidgets import QProgressBar
    page.sync_progress=QProgressBar();page.sync_progress.setRange(0,0);page.sync_progress.setTextVisible(False);page.sync_progress.setFixedHeight(5);page.sync_progress.hide();v.insertWidget(v.indexOf(page.status)+1,page.sync_progress)
    page.status.setStyleSheet('color:#5143bd;background:#f7f5ff;border-radius:7px;padding:10px;font-size:13px;')
    def progress_status(text):
        page.status.setText(text);last.setText(text)
        running=text.startswith('Đang')
        page.sync_progress.setVisible(running)
    page.set_sync_progress=progress_status
    page.show_snapshot=snapshot;page.show_plan=planned
