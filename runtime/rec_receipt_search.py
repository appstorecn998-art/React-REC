"""Read-only receipt search shared by current-day and date-range UI."""
import re
import unicodedata
from zipfile import BadZipFile
from datetime import timedelta

FIELDS=('Nhà cung cấp','Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống','Mã vật tư','Ảnh nguồn','Các ảnh cùng phiếu','Số PO','Số PR')
def normalize(value):
    text=unicodedata.normalize('NFD',str(value or '').casefold().replace('đ','d'))
    return ' '.join(re.findall(r'\w+', ''.join(c for c in text if not unicodedata.combining(c))))
def matches(query,sheet,rows,nickname=''):
    haystack=normalize(' '.join([str(sheet),nickname]+[str(v.get(k) or '') for _,v in rows for k in FIELDS]))
    return all(term in haystack for term in normalize(query).split())
def collect(root,destination,start,end,query):
    from receiving_service import paths,snapshot
    from rec_fluent_ui import short_supplier
    if start>end:raise ValueError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
    if (end-start).days>365:raise ValueError('Chọn tối đa 366 ngày mỗi lần tìm.')
    found=[];errors=[];day=start
    while day<=end:
        try:
            folder,report=paths(root,day,destination)
            if report.is_file():
                _,data=snapshot(report)
                for sheet,rows in data:
                    supplier=' / '.join(dict.fromkeys(str(v.get('Nhà cung cấp') or '').strip() for _,v in rows if v.get('Nhà cung cấp'))) or 'NCC chưa rõ'
                    nickname=short_supplier(supplier,root)
                    if matches(query,sheet,rows,nickname):
                        products=list(dict.fromkeys(str(v.get('Tên hàng trên phiếu (Ảnh)') or v.get('Tên chuẩn hệ thống') or '') for _,v in rows))
                        found.append(dict(day=day,sheet=sheet,supplier=nickname,products='; '.join(filter(None,products)),report=str(report)))
        except (OSError,ValueError,KeyError,BadZipFile) as exc:errors.append(f'{day:%d/%m/%Y}: {exc}')
        day+=timedelta(days=1)
    return sorted(found,key=lambda r:r['day'],reverse=True),errors

def show(w,query=''):
    from PySide6.QtCore import QDate,Qt
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QDateEdit,QPushButton,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMessageBox,QComboBox,QSplitter,QTextEdit,QGridLayout
    from receiving_qt import Worker
    from PySide6.QtWidgets import QWidget
    existing=getattr(w,'receipt_history_page',None)
    if existing is not None:
        w.main_pages.setCurrentWidget(existing);return existing
    dialog=QWidget();dialog.setObjectName('receiptHistoryPage');w.receipt_history_page=dialog
    layout=QVBoxLayout(dialog);layout.setContentsMargins(20,20,20,20);layout.setSpacing(14)
    title=QLabel('Tra cứu phiếu giao hàng');title.setStyleSheet('font-size:22px;font-weight:600;color:#24334b;');layout.addWidget(title)
    layout.addWidget(QLabel('Tìm phiếu theo ngày lưu · Bao gồm phiếu chưa ghi sổ · Không thay đổi dữ liệu'))
    bar=QGridLayout();bar.setHorizontalSpacing(10);bar.setVerticalSpacing(10);layout.addLayout(bar)
    search=QLineEdit(query);search.setPlaceholderText('NCC, tên hàng, mã hàng hoặc tên ảnh (có/không dấu)');search.setObjectName('receiptHistorySearch');bar.addWidget(search,0,0,1,6)
    end=QDate(w.day.year,w.day.month,w.day.day);start_edit=QDateEdit(end.addDays(-29));end_edit=QDateEdit(end)
    for col,label,edit in [(0,'Từ ngày',start_edit),(2,'Đến ngày',end_edit)]:
        bar.addWidget(QLabel(label),1,col);edit.setCalendarPopup(True);edit.setDisplayFormat('dd/MM/yyyy');edit.setObjectName('receiptHistoryStart' if col==0 else 'receiptHistoryEnd');bar.addWidget(edit,1,col+1)
    run=QPushButton('Tìm kiếm');run.setObjectName('receiptHistoryRun');bar.addWidget(run,1,4);bar.setColumnStretch(5,1)
    note=QLabel('Mặc định 30 ngày đến ngày đang xem. Ngày lọc là ngày lưu phiếu, gồm cả phiếu chưa ghi sổ.');note.setWordWrap(True);layout.addWidget(note)
    shortcuts=QHBoxLayout();layout.addLayout(shortcuts)
    for text,days in [('Ngày đang xem',0),('7 ngày',6),('30 ngày',29)]:
        button=QPushButton(text);shortcuts.addWidget(button)
        def period(_=False,days=days):
            if state['loading']:return
            anchor=QDate(w.day.year,w.day.month,w.day.day);start_edit.setDate(anchor.addDays(-days));end_edit.setDate(anchor);load()
        button.clicked.connect(period)
    shortcuts.addStretch()
    supplier=QComboBox();supplier.setObjectName('receiptHistorySupplier');supplier.addItem('Tất cả nhà cung cấp',None)
    sort=QComboBox();sort.setObjectName('receiptHistorySort');sort.addItem('Ngày mới nhất','date');sort.addItem('Theo nhà cung cấp','supplier')
    shortcuts.addWidget(supplier,1);shortcuts.addWidget(sort)
    split=QSplitter(Qt.Horizontal);layout.addWidget(split,1)
    table=QTableWidget(0,4);table.setObjectName('receiptHistoryResults');table.setHorizontalHeaderLabels(['Ngày lưu','Nhà cung cấp','Phiếu / ảnh','Mặt hàng']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(False);table.verticalHeader().setDefaultSectionSize(48);split.addWidget(table)
    detail_panel=QWidget();detail_layout=QVBoxLayout(detail_panel);detail_layout.setContentsMargins(16,0,0,0)
    detail_title=QLabel('Chi tiết phiếu đã chọn');detail_title.setStyleSheet('font-size:16px;font-weight:600;');detail_layout.addWidget(detail_title)
    detail=QTextEdit();detail.setObjectName('receiptHistoryDetail');detail.setReadOnly(True);detail.setPlaceholderText('Chọn một phiếu để xem đầy đủ tên mặt hàng.');detail_layout.addWidget(detail,1);split.addWidget(detail_panel);split.setSizes([1000,400]);split.setStretchFactor(0,3);split.setStretchFactor(1,1)
    footer=QHBoxLayout();footer.addWidget(QLabel('Chọn phiếu để xem chi tiết · Bấm đúp để mở phiếu'));footer.addStretch()
    open_button=QPushButton('Mở phiếu đã chọn');open_button.setObjectName('receiptHistoryOpen');open_button.setEnabled(False);footer.addWidget(open_button);layout.addLayout(footer)
    state={'rows':[],'view':[],'loading':False,'summary':''}
    def selected():
        i=table.currentRow();valid=not state['loading'] and 0<=i<len(state['view']);open_button.setEnabled(valid)
        if not valid:detail.clear();return
        r=state['view'][i];detail.setPlainText('Nhà cung cấp: '+r['supplier']+'\nNgày lưu: '+r['day'].strftime('%d/%m/%Y')+'\nPhiếu / ảnh: '+r['sheet']+'\n\nMặt hàng trên phiếu\n'+r['products']+'\n\nTệp nguồn\n'+r['report'])
    def render(*_):
        current=table.currentRow();old=state['view'][current] if 0<=current<len(state['view']) else None
        rows=[r for r in state['rows'] if not supplier.currentData() or normalize(r['supplier'])==supplier.currentData()]
        if sort.currentData()=='supplier':rows=sorted(rows,key=lambda r:(normalize(r['supplier']),-r['day'].toordinal(),r['sheet']))
        state['view']=rows;table.blockSignals(True);table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,text in enumerate([r['day'].strftime('%d/%m/%Y'),r['supplier'],r['sheet'],r['products']]):
                cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,j,cell)
        table.clearSelection();table.setCurrentCell(-1,-1)
        if rows:table.selectRow(next((i for i,r in enumerate(rows) if old and r['report']==old['report'] and r['sheet']==old['sheet']),0))
        table.blockSignals(False);selected()
        note.setText(str(len(rows))+' / '+str(len(state['rows']))+' phiếu · '+state['summary'])
    supplier.currentIndexChanged.connect(render);sort.currentIndexChanged.connect(render);table.itemSelectionChanged.connect(selected)
    def load():
        if state['loading']:return
        start=start_edit.date().toPython();end=end_edit.date().toPython()
        if start>end or (end-start).days>365:note.setText('Khoảng ngày không hợp lệ: từ ngày ≤ đến ngày, tối đa 366 ngày.');return
        state['loading']=True;run.setEnabled(False);open_button.setEnabled(False);table.setRowCount(0);state['rows']=[];state['view']=[];detail.clear();supplier.setEnabled(False);sort.setEnabled(False);note.setText('Đang tìm phiếu trong khoảng ngày đã chọn…')
        job=Worker(collect,w.root,w.destination,start,end,search.text())
        def ready(payload):
            rows,errors=payload;state['rows']=rows
            previous=supplier.currentData();supplier.blockSignals(True);supplier.clear();supplier.addItem('Tất cả nhà cung cấp',None)
            choices={normalize(r['supplier']):r['supplier'] for r in rows}
            for key in sorted(choices):supplier.addItem(choices[key],key)
            supplier.setCurrentIndex(max(0,supplier.findData(previous)));supplier.blockSignals(False)
            state['summary']=f'{start:%d/%m/%Y} – {end:%d/%m/%Y}'+(f' · {len(errors)} ngày không đọc được, kết quả chưa đầy đủ.' if errors else '')
            note.setToolTip('\n'.join(errors));render()
        def finished():
            state['loading']=False;run.setEnabled(True);supplier.setEnabled(True);sort.setEnabled(True);selected()
        job.signals.result.connect(ready);job.signals.error.connect(lambda message:note.setText('Chưa tìm được: '+message));job.signals.finished.connect(finished);w._start_worker(job)
    def open_selected():
        i=table.currentRow()
        if w.busy or not 0<=i<len(state['view']) or not w._leave_pr():return
        r=state['view'][i]
        try:payload=w._load_day(r['day'],w.destination,w.root)
        except Exception as exc:QMessageBox.warning(dialog,'Chưa mở được phiếu',str(exc));return
        from pathlib import Path
        if Path(payload[1]).resolve()!=Path(r['report']).resolve() or r['sheet'] not in dict(payload[3]):QMessageBox.warning(dialog,'Phiếu đã thay đổi','Tìm lại trước khi mở phiếu.');return
        w.day=r['day'];w.date_edit.blockSignals(True);w.date_edit.setDate(QDate(w.day.year,w.day.month,w.day.day));w.date_edit.blockSignals(False)
        w.receipt_search.clear();w._day_loaded(payload);w.select_sheet(r['sheet']);w.fluent_nav.set_current('Kiểm tra phiếu')
    run.clicked.connect(load);search.returnPressed.connect(load);open_button.clicked.connect(open_selected);table.cellDoubleClicked.connect(lambda *_:open_selected())
    dialog.setStyleSheet('QWidget#receiptHistoryPage {background:white;color:#334155;font-family:Segoe UI;font-size:13px;} QLineEdit,QDateEdit,QPushButton,QComboBox {min-height:34px;} QLineEdit,QDateEdit,QComboBox,QTextEdit {background:white;border:1px solid #dfe4ed;border-radius:7px;padding:6px;color:#475569;} QPushButton {background:white;border:1px solid #dfe4ed;border-radius:7px;padding:4px 14px;color:#475569;} QPushButton#receiptHistoryRun,QPushButton#receiptHistoryOpen {background:#6554d9;color:white;border-color:#6554d9;} QPushButton:disabled {background:#edeaf8;color:#9993b3;} QTableWidget {border:1px solid #e4e7ef;border-radius:8px;} QTableWidget::item {padding:8px;border-bottom:1px solid #edf0f5;} QTableWidget::item:selected {background:#efecff;color:#5543b6;} QHeaderView::section {background:#f1f5f9;color:#334155;padding:10px;border:0;}')
    w.main_pages.addWidget(dialog);w.main_pages.setCurrentWidget(dialog);load();return dialog


def suggestions(query,entries):
    """Group supplier or matching product suggestions across receipts in one day."""
    result={};terms=normalize(query).split()
    for sheet,rows,nickname in entries:
        if not matches(query,sheet,rows,nickname):continue
        supplier=' '.join(str(v.get('Nhà cung cấp') or '') for _,v in rows)
        supplier_text=normalize(supplier+' '+nickname)
        if not terms or all(t in supplier_text for t in terms):
            result.setdefault(nickname,set()).add(sheet);continue
        found=False
        for _,row in rows:
            name=str(row.get('Tên hàng trên phiếu (Ảnh)') or row.get('Tên chuẩn hệ thống') or '').strip()
            product=normalize(' '.join(str(row.get(k) or '') for k in ('Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống','Mã vật tư')))
            if name and all(t in supplier_text+' '+product for t in terms) and any(t in product for t in terms):
                result.setdefault(name+' · '+nickname,set()).add(sheet);found=True
        if not found:result.setdefault(nickname,set()).add(sheet)
    return result
