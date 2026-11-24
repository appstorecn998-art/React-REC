"""Debounced background status for the current day's review/posting workflow."""
import copy
from pathlib import Path
from PySide6.QtCore import QTimer

def paint(button,text,kind):
    colors={'neutral':('#64748b','#f1f5f9'),'warning':('#975a08','#fff7e6'),'ready':('#1d4ed8','#eff6ff'),'running':('#6d28d9','#f5f3ff'),'done':('#166534','#ecfdf3'),'error':('#b42336','#fff1f2')}
    fg,bg=colors[kind];button.setText(('✓ ' if kind=='done' else '● ')+text)
    button.setStyleSheet(f'QPushButton {{color:{fg};background:{bg};border:1px solid {fg};border-radius:7px;padding:0 12px;min-height:34px;}}')
    button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text())+32)

def summarize(entries):
    total=len(entries);posted=sum(e['status']=='Đã ghi sổ' for e in entries);ready=sum(e['status']=='Sẵn sàng ghi sổ' for e in entries);manual=sum(e['status']=='Không có PR/PO' for e in entries);waiting=sum(e['status']=='Chờ PR thay thế' for e in entries);blocked=total-posted-ready-manual-waiting
    if not total:return ('Chưa có phiếu','neutral')
    if blocked:return (f'Còn {blocked}/{total} phiếu cần kiểm','warning')
    if ready:return (f'{ready} phiếu chờ ghi sổ','ready')
    if waiting:return (f'{waiting} phiếu chờ PR thay thế','warning')
    return ('Đợt kiểm hoàn tất','done')

def schedule(w):
    if not hasattr(w,'bulk_pr_button') or not getattr(w,'report',None):return
    if not hasattr(w,'workflow_status_timer'):
        w.workflow_status_timer=QTimer(w);w.workflow_status_timer.setSingleShot(True);w.workflow_status_timer.setInterval(650)
        w.workflow_status_timer.timeout.connect(lambda:refresh(w))
    w.workflow_status_timer.start()

def refresh(w):
    if w.busy or getattr(w,'workflow_status_running',False):schedule(w);return
    from receiving_qt import Worker
    from receiving_bulk_ledger import prepare
    if not w.report or not Path(w.report).is_file():paint(w.bulk_pr_button,'Chưa có phiếu','neutral');return
    context=(str(w.report),w.source_hash,w.day.isoformat())
    w.workflow_status_running=True
    task=Worker(prepare,w.folder,w.report,copy.deepcopy(list(w.data_by_sheet.items())),list(w.images),w.pr_library_directory(),w.ledger_path(),w.day.isoformat())
    def ready(preview):
        if context!=(str(w.report),w.source_hash,w.day.isoformat()):schedule(w);return
        text,kind=summarize(preview['entries'])
        if getattr(w,'sheets_sync_running',False):text,kind='Đang đồng bộ Sheets','running'
        elif kind=='done' and 'chưa xác nhận' in getattr(w,'sheets_last_status','').casefold():text,kind='Đã ghi · Sheets cần thử lại','warning'
        paint(w.bulk_pr_button,text,kind)
        w.bulk_pr_button.setToolTip('Hoàn tất đợt kiểm · '+w.day.strftime('%d/%m/%Y')+'\n'+'\n'.join(e['sheet']+' · '+e['status']+(' · '+e.get('reason','') if e['status']=='Cần rà lại' else '') for e in preview['entries']))
    def failed(message):
        if context==(str(w.report),w.source_hash,w.day.isoformat()):paint(w.bulk_pr_button,'Chưa xác định trạng thái','error');w.bulk_pr_button.setToolTip(message)
    task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(lambda:setattr(w,'workflow_status_running',False));w._start_worker(task)
