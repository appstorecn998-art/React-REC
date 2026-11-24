"""Design27: background read-only audit, no implicit posting or confirmations."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QDate
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QDialogButtonBox,QTabWidget
from rec_pr_surface import flat_page
from receiving_service import snapshot,sheet_signature,day_images

def collect(w,path,root):
    import receiving_ledger as ledger
    findings=[];cache={}
    _,history=ledger.summary(path,lambda p:w._ledger_valid(p,cache))
    recorded={(str(Path(r['report']).resolve()).casefold(),r['sheet']) for r in history if r['active']}
    for record in history:
        if record['active']:findings.append(dict(group='Nguồn hợp lệ' if record['valid'] else 'Nguồn cần cập nhật',description=record['day']+' · '+record['sheet'],action='Xem lịch sử' if record['valid'] else 'Kiểm tra',payload=record))
    for report in sorted(Path(root).rglob('TongHopPhieuNgay_*.xlsx')):
        if any('.autowatcher-backups' in part or part.startswith('.codex-') for part in report.parts):continue
        try:
            _,sheets=snapshot(report);signatures={sheet_signature(name,rows):name for name,rows in sheets}
            for comparison in report.parent.rglob('*.comparison.json'):
                if '.autowatcher-backups' in comparison.parts:continue
                try:
                    data=json.loads(comparison.read_text(encoding='utf-8'));sheet=signatures.get(data.get('signature'))
                    if sheet and (str(report.resolve()).casefold(),sheet) not in recorded:findings.append(dict(group='Đối chiếu đã lưu, chưa ghi',description=report.name+' · '+sheet,action='Mở phiếu',report=str(report),sheet=sheet))
                    elif not sheet:findings.append(dict(group='Nguồn cần cập nhật',description=comparison.name+' · Chữ ký đối chiếu không khớp phiếu hiện tại',action='Kiểm tra',report=str(report),sheet=None))
                except (OSError,ValueError,TypeError) as exc:findings.append(dict(group='Không đọc được dữ liệu',description=comparison.name+' · '+str(exc),action='Kiểm tra',report=str(report),sheet=None))
        except (OSError,ValueError,KeyError) as exc:findings.append(dict(group='Không đọc được dữ liệu',description=report.name+' · '+str(exc),action='Kiểm tra',report=str(report),sheet=None))
    pending=ledger.pending_sync(path)
    if pending:findings.append(dict(group='Outbox chờ / lỗi',description=str(len(pending))+' lần đồng bộ chưa hoàn tất',action='Thử lại',sync=True))
    return findings

def show(w):
    old=getattr(w,'audit_page',None)
    if old is not None:w.main_pages.setCurrentWidget(old);old.reload_audit();return old
    page=QWidget();page.setObjectName('auditPage');QVBoxLayout(page);w.audit_page=page
    table=QTableWidget(0,3);table.setObjectName('auditFindingsTable');table.setHorizontalHeaderLabels(['Nhóm','Phát hiện','Hành động']);table.verticalHeader().hide();table.setShowGrid(False);table.setWordWrap(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.addWidget(table)
    status=QLabel();status.setObjectName('auditStatus');status.setWordWrap(True);v.addWidget(status)
    box=QDialogButtonBox(QDialogButtonBox.Save);reload_button=box.button(QDialogButtonBox.Save);reload_button.setText('Tải lại kết quả')
    notice=QLabel('Rà soát chỉ đọc dữ liệu, không tự xác nhận hoặc ghi sổ. Chọn Thử lại mới chạy đồng bộ các sự kiện đang chờ.')
    flat_page(page,'Rà soát toàn bộ dữ liệu','Chỉ kiểm tra; không tự xác nhận hoặc ghi sổ',content,notice,box)
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Rà soát toàn bộ dữ liệu':label.setText('Sổ nhận hàng / Rà soát toàn bộ dữ liệu')
    notice.hide()
    page.setStyleSheet(page.styleSheet()+'QWidget#auditPage {background:white;}');page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch()
    state={'loading':False}
    def open_source(finding):
        if w.busy:return
        if finding.get('sync'):
            __import__('rec_auto_sheets').start(w);status.setText('Đã yêu cầu thử lại đồng bộ. Kết quả Sheets báo riêng; không ghi thêm lần nhận.');return
        if finding.get('payload'):
            if finding['payload']['valid']:
                w.show_shortage_ledger();tabs=w.ledger_page.findChild(QTabWidget)
                for i in range(tabs.count()):
                    if tabs.tabText(i)=='Lịch sử giao hàng':tabs.setCurrentIndex(i);break
            else:__import__('rec_receipt_source_page').show(w,finding['payload'])
            return
        if not finding.get('sheet'):status.setText('Nguồn cần rà: '+finding['description']);return
        if not w._leave_pr():return
        from receiving_qt import Worker
        report=Path(finding['report']);sheet=finding['sheet']
        def read():
            from datetime import datetime
            day=datetime.strptime(report.stem.removeprefix('TongHopPhieuNgay_'),'%d-%m-%Y').date();folder,_=__import__('receiving_service').paths(w.root,day,w.destination)
            h,data=snapshot(report)
            if sheet not in dict(data):raise ValueError('Phiếu đã đổi hoặc không còn trong nguồn.')
            reviews=json.loads((folder/'reviewed.json').read_text(encoding='utf-8')) if (folder/'reviewed.json').exists() else {}
            return day,(folder,report,h,data,day_images(report.parent),{n:sheet_signature(n,r) for n,r in data},reviews)
        def ready(result):
            day,payload=result;w.day=day;w.date_edit.blockSignals(True);w.date_edit.setDate(QDate(day.year,day.month,day.day));w.date_edit.blockSignals(False);w._day_loaded(payload);w.select_sheet(sheet);w.main_pages.setCurrentWidget(w.receipt_page)
        w.set_busy(True,'Đang mở phiếu cần rà…');job=Worker(read);job.signals.result.connect(ready);job.signals.error.connect(lambda text:status.setText('Chưa mở được: '+text));job.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(job)
    def render(findings):
        table.setRowCount(len(findings))
        for i,finding in enumerate(findings):
            for col,text in enumerate([finding['group'],finding['description']]):cell=QTableWidgetItem(text);cell.setToolTip(text);table.setItem(i,col,cell)
            button=QPushButton(finding['action']);button.setFixedSize(112,34);button.clicked.connect(lambda checked=False,f=finding:open_source(f));table.setCellWidget(i,2,button);table.setRowHeight(i,60)
        table.setFixedHeight(min(500,44+60*max(1,len(findings))+2));content.setFixedHeight(table.height()+65);status.setText(str(len(findings))+' kết quả rà soát.' if findings else 'Chưa có lần nhận hoặc đối chiếu đã lưu để rà soát.')
    def refresh():
        if w.busy or state['loading']:return
        from receiving_qt import Worker
        from receiving_service import accounting_root
        path=w.ledger_path();root=accounting_root(w.destination);state['loading']=True;reload_button.setEnabled(False);table.setEnabled(False);status.setText('Đang đọc và kiểm tra nguồn…')
        job=Worker(collect,w,path,root)
        def ready(findings):
            if w.ledger_path()!=path or accounting_root(w.destination)!=root:status.setText('Nguồn đang xem đã đổi. Tải lại kết quả.');return
            render(findings)
        job.signals.result.connect(ready);job.signals.error.connect(lambda text:status.setText('Chưa rà soát được: '+text+' · Dữ liệu cũ vẫn giữ.'))
        def finish():state['loading']=False;reload_button.setEnabled(True);table.setEnabled(True)
        job.signals.finished.connect(finish);w._start_worker(job)
    page.reload_audit=refresh;box.accepted.connect(refresh);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);refresh();return page
