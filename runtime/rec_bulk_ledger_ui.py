"""Batch ledger approval dialog; all source work runs in a worker."""
from pathlib import Path
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QDialogButtonBox,QMessageBox,QWidget,QHBoxLayout,QHeaderView,QAbstractItemView,QPushButton

def show(w):
    if w.busy or not w.report:return
    if not w._leave_pr():return
    from receiving_qt import Worker
    from receiving_bulk_ledger import prepare,apply
    folder,report,path,day=w.folder,w.report,w.ledger_path(),w.day.isoformat()
    w.set_busy(True,'Đang kiểm tra điều kiện ghi sổ các phiếu trong ngày…')
    job=Worker(prepare,folder,report,list(w.data_by_sheet.items()),list(w.images),w.pr_library_directory(),path,day)
    def ready(preview):
        w.set_busy(False)
        if w.report!=report or w.folder!=folder or w.day.isoformat()!=day:
            w.show_top_notice('Dữ liệu đã đổi','Mở lại danh sách ghi sổ cho ngày đang chọn.',variant='warning');return
        build_page(w,preview,folder,report,day)
    def failed(msg):
        w.set_busy(False);w.show_top_notice('Chưa tải được danh sách',msg,variant='warning')
    job.signals.result.connect(ready);job.signals.error.connect(failed);w._start_worker(job)

def build_page(w,preview,folder,report,day):
    from receiving_qt import Worker
    from receiving_bulk_ledger import apply
    from rec_dialog_surface import surface
    import copy
    old=getattr(w,'bulk_ledger_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('bulkLedgerPage');QVBoxLayout(page);w.bulk_ledger_page=page
    entries=preview['entries'];ready_status='Sẵn sàng ghi sổ'
    badges=QWidget();bar=QHBoxLayout(badges);bar.setContentsMargins(0,0,0,0);bar.setSpacing(22)
    statuses=[('Sẵn sàng',lambda e:e['status']==ready_status,'#178255'),('Cần rà',lambda e:e['status'] not in [ready_status,'Đã ghi sổ','Không có PR/PO','Chờ PR thay thế'],'#b07c1b'),('Đã ghi',lambda e:e['status']=='Đã ghi sổ','#7e8ba1'),('Không PR/PO',lambda e:e['status']=='Không có PR/PO','#8a5ac0')]
    statuses.append(('Chờ PR thay thế',lambda e:e['status']=='Chờ PR thay thế','#8a5ac0'))
    badge_labels=[]
    for label,predicate,color in statuses:
        text=QLabel(f'• {label} {sum(predicate(e) for e in entries)}');text.setStyleSheet(f'color:{color};font-size:14px;font-weight:600;');bar.addWidget(text);badge_labels.append(text)
    bar.addStretch()
    table=QTableWidget(len(entries),4);table.setObjectName('bulkLedgerApprovalTable');table.setHorizontalHeaderLabels(['Chọn','Phiếu / NCC','Lượng đối chiếu','Trạng thái / lý do'])
    table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True);table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Fixed);table.setColumnWidth(0,65);table.horizontalHeader().setFixedHeight(44)
    table.setStyleSheet('QTableWidget#bulkLedgerApprovalTable {font-size:15px;color:#334155;} QTableWidget#bulkLedgerApprovalTable::item {font-size:15px;padding:10px;} QHeaderView::section {font-size:14px;color:#475569;font-weight:600;}')
    rows_by_sheet=dict(w.data_by_sheet)
    for i,e in enumerate(entries):
        cell=QTableWidgetItem();cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable if e['status']==ready_status else Qt.NoItemFlags);cell.setCheckState(Qt.Checked if e['status']==ready_status else Qt.Unchecked);table.setItem(i,0,cell)
        supplier=e.get('payload',{}).get('supplier_name') or ' / '.join(sorted({str(v.get('Nhà cung cấp') or '') for _,v in rows_by_sheet.get(e['sheet'],[])}-{''}))
        quantities=e['reason'] if e['status']==ready_status else '—'
        label='Sẵn sàng' if e['status']==ready_status else e['status']
        detail=label+(' · '+e['reason'] if e['status']!=ready_status and e.get('reason') else '')
        for col,text in enumerate([e['sheet']+(' · '+supplier if supplier else ''),quantities,detail],1):
            item=QTableWidgetItem(text);item.setToolTip(text);table.setItem(i,col,item)
            if col==3:
                from PySide6.QtGui import QColor
                item.setForeground(QColor('#178255' if e['status']==ready_status else '#8a5ac0' if e['status']=='Không có PR/PO' else '#7e8ba1' if e['status']=='Đã ghi sổ' else '#b07c1b'))
        table.setRowHeight(i,60)
    table.setFixedHeight(min(430,44+60*max(1,len(entries))+2))
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(14)
    changed=QLabel();changed.setObjectName('bulkSourceChangedBanner');changed.setWordWrap(True);changed.hide();changed.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;');v.addWidget(changed);v.addWidget(table)
    outcome=QLabel('Chưa có phiếu trong ngày đang chọn.' if not entries else '');outcome.setWordWrap(True);outcome.setObjectName('bulkLedgerOutcome');v.addWidget(outcome)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=buttons.button(QDialogButtonBox.Save);save.setText('Hoàn tất đợt & ghi sổ');buttons.button(QDialogButtonBox.Cancel).setText('Hủy');update=buttons.addButton('Chỉ cập nhật đối chiếu',QDialogButtonBox.ActionRole)
    reload=buttons.addButton('Tải lại danh sách',QDialogButtonBox.ActionRole)
    notice=QLabel('Kiểm tra lại Excel, ảnh, bộ PR và thư viện PR ngay trước khi ghi. Nếu thành công một phần, báo kết quả từng phiếu.')
    surface(page,'Hoàn tất đợt kiểm','Ghi tất cả phiếu đã kiểm trong ngày đang chọn · '+w.day.strftime('%d/%m/%Y'),content,notice,buttons,extras=badges)
    page.setStyleSheet(page.styleSheet()+'QWidget#bulkLedgerPage {background:white;}')
    for label in page.findChildren(QLabel):
        if label.text()=='Rà soát / Hoàn tất đợt kiểm':label.setText('Sổ nhận hàng / Hoàn tất đợt kiểm')
    page.layout().setStretch(page.layout().count()-1,0);page.layout().addStretch()
    state={'running':False,'done':False}
    def valid_context():
        if w.report!=report or w.folder!=folder or w.day.isoformat()!=day:
            outcome.setText('Ngày hoặc báo cáo đang xem đã đổi. Mở lại danh sách trước khi thực hiện.');return False
        return True
    def selection():return [i for i,e in enumerate(entries) if e['status']==ready_status and table.item(i,0).checkState()==Qt.Checked]
    def update_buttons(*_):
        save.setEnabled(bool(selection()) and not state['running'] and not state['done']);update.setEnabled(bool(preview.get('changes')) and not state['running'] and not state['done'])
    table.itemChanged.connect(update_buttons);update_buttons()
    def set_running(value,message=''):
        state['running']=value;reload.setEnabled(not value);table.setEnabled(not value);buttons.button(QDialogButtonBox.Cancel).setEnabled(not value);update_buttons();w.set_busy(value,message)
    def fail(message):
        outcome.setText('Chưa hoàn tất: '+message+'\nMở lại danh sách để kiểm tra nguồn và kết quả trước khi thử tiếp.');state['done']=True;update_buttons()
    def back():
        if not state['running']:w.show_shortage_ledger()
    buttons.rejected.connect(back)
    def posted(results):
        state['done']=True
        reviews=Path(folder)/'reviewed.json'
        if w.folder==folder:
            w.reviews=json.loads(reviews.read_text(encoding='utf-8')) if reviews.exists() else {};w.update_pr_status();w.review_label.setText('Đã kiểm tra' if w.approved(w.current_sheet) else 'Chưa kiểm tra')
        ok=sum(status=='Đã ghi sổ' for _,status,_ in results)
        outcome.setText(f'Đã ghi sổ {ok}/{len(results)} phiếu đã chọn.\n'+'\n'.join(sheet+' · '+status+(' · '+reason if reason else '') for sheet,status,reason in results))
        outcome.setToolTip(outcome.text());update_buttons()
        from rec_batch_result_page import show_result
        full_results=list(results)+[(e['sheet'],e['status'],e.get('reason','')) for e in entries if e['sheet'] not in {r[0] for r in results}]
        w.sheets_last_status='Sheets: đang chờ đồng bộ đợt này' if ok else 'Sheets: không có phiếu mới được ghi trong đợt này'
        show_result(w,full_results,day,report)
        if ok:
            from rec_auto_sheets import start
            start(w)
            if getattr(w,'ledger_refresh',None):w.ledger_refresh()
    def record():
        if state['running'] or state['done'] or not valid_context() or not selection():return
        chosen=set(selection());snapshot=copy.deepcopy(preview)
        for i,e in enumerate(snapshot['entries']):
            if e['status']==ready_status and i not in chosen:e['status']='Không chọn'
        set_running(True,'Đang ghi sổ các phiếu đã duyệt…')
        task=Worker(apply,snapshot);task.kwargs['progress']=task.signals.progress.emit;task.signals.progress.connect(w.statusBar().showMessage)
        task.signals.result.connect(posted);task.signals.error.connect(fail);task.signals.finished.connect(lambda:set_running(False));w._start_worker(task)
    def comparisons_only():
        if state['running'] or state['done'] or not valid_context():return
        from receiving_pr_bulk import apply as update_comparisons
        set_running(True,'Đang cập nhật đối chiếu PR…');task=Worker(update_comparisons,copy.deepcopy(preview))
        def updated(count):
            state['done']=True;outcome.setText(f'Đã cập nhật đối chiếu {count} phiếu. Chưa ghi thêm lần nhận vào sổ.');update_buttons()
        task.signals.result.connect(updated);task.signals.error.connect(fail);task.signals.finished.connect(lambda:set_running(False));w._start_worker(task)
    def reload_list():
        if state['running'] or w.busy or not valid_context() or not w._leave_pr():return
        set_running(True,'Đang tải lại nguồn và danh sách…')
        task=Worker(w._load_day,w.day,w.destination,w.root)
        def loaded(payload):
            if not valid_context():return
            w._day_loaded(payload);set_running(False)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,lambda:show(w))
        task.signals.result.connect(loaded);task.signals.error.connect(fail)
        task.signals.finished.connect(lambda:set_running(False) if state['running'] else None);w._start_worker(task)
    wait=buttons.addButton('Chờ PR thay thế / Bỏ chờ',QDialogButtonBox.ActionRole);wait.setObjectName('waitReplacementPR')
    def defer_selected():
        if state['running'] or w.busy or not valid_context():return
        index=table.currentRow()
        if not 0<=index<len(entries):outcome.setText('Chọn dòng phiếu cần xử lý trước.');return
        entry=entries[index];sheet=entry['sheet']
        if entry['status']=='Đã ghi sổ':outcome.setText('Phiếu đã ghi sổ; không chuyển chờ thay PR ở đây.');return
        from receiving_pending_pr import set_pending
        from receiving_service import snapshot,sheet_signature
        try:
            rows=rows_by_sheet[sheet];current=dict(snapshot(report)[1]).get(sheet)
            if current is None or sheet_signature(sheet,current)!=sheet_signature(sheet,rows):raise ValueError('Phiếu đã đổi. Tải lại trước.')
            enabled=entry['status']!='Chờ PR thay thế'
            reason=''
            if enabled:
                from PySide6.QtWidgets import QInputDialog
                reason,okay=QInputDialog.getText(page,'Chờ bộ phận cấp PR thay thế','Phiếu '+sheet+'\nKhông ghi sổ, không cộng vào PR cũ. Lý do:',text='Bếp ghi sai số PR/ngày PR, đang chờ PR mới')
                if not okay:return
            set_pending(folder,sheet,rows,w.images,reason,enabled)
            outcome.setText('Đã chuyển chờ PR thay thế. Có thể ghi các phiếu sẵn sàng khác.' if enabled else 'Đã bỏ chờ. Kiểm tra PR mới trước khi ghi sổ.')
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,lambda:show(w))
        except (OSError,ValueError,KeyError) as exc:outcome.setText(str(exc))
    # Auxiliary actions have their own row, outside the fixed-width button box.
    tools=QHBoxLayout();tools.setContentsMargins(0,0,0,0);tools.setSpacing(10)
    for button in (wait,reload,update):
        buttons.removeButton(button)
        button.setStyleSheet('QPushButton {background:white;color:#475569;border:1px solid #dce2ed;border-radius:6px;padding:0 14px;font-size:13px;min-height:36px;max-height:36px;} QPushButton:hover {background:#f5f3ff;border-color:#b8aef2;} QPushButton:disabled {color:#a0a8b6;border-color:#edf0f5;}')
        button.ensurePolished();button.setFixedHeight(38);button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text())+32);button.setMaximumWidth(16777215)
        tools.addWidget(button);button.show()
    tools.addStretch();v.addLayout(tools)
    save.setText('Ghi sổ các phiếu đã chọn')
    for button in buttons.buttons():
        button.ensurePolished();button.setFixedSize(button.fontMetrics().horizontalAdvance(button.text())+40,38)
    buttons.setFixedWidth(sum(b.width() for b in buttons.buttons())+24)
    wait.clicked.connect(defer_selected)
    reload.clicked.connect(reload_list)
    buttons.accepted.connect(record);update.clicked.connect(comparisons_only)
    def open_receipt(row,col):
        if col==0 or state['running'] or w.busy or not valid_context():return
        sheet=entries[row]['sheet']
        w.select_sheet(sheet)
        if w.current_sheet!=sheet:return
        w.main_pages.setCurrentWidget(w.receipt_page)
        w.review_tabs.setCurrentIndex(0)
        w.receipt_menu.hide()
        w.statusBar().showMessage('Đang xem '+sheet+' · sửa phiếu rồi mở lại Hoàn tất đợt kiểm để cập nhật danh sách.',7000)
    table.cellClicked.connect(open_receipt)
    table.setToolTip('Bấm tên phiếu hoặc trạng thái để mở phiếu. Ô Chọn chỉ dùng chọn ghi sổ.')
    for i in range(table.rowCount()):table.setRowHeight(i,max(76,table.rowHeight(i)))
    w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page)
    return page
