"""Serialize automatic Sheets updates after an explicit local approval/mutation."""
from PySide6.QtCore import QTimer

def start(w):
    if getattr(w,'sheets_sync_running',False):
        w.sheets_sync_pending=True;return
    page=getattr(w,'sheets_page',None)
    if page is not None and page.running:
        w.sheets_sync_pending=True
        w.statusBar().showMessage('Sổ đã đổi; sẽ đọc lại sau khi thao tác Sheets hiện tại hoàn tất.');return
    from receiving_qt import Worker
    from receiving_sheets import SheetsClient,plan,apply,file_signature
    import receiving_ledger as ledger
    path=w.ledger_path();root=w.root
    outbox_ids=ledger.pending_sync(path)
    w.sheets_sync_running=True;w.sheets_sync_pending=False
    if page is not None:
        page.running=True;page.save.setEnabled(False);page.reload.setEnabled(False);page.table.setRowCount(0);page.summary.setText('Đang đồng bộ tự động…')
    def status(message):
        from rec_workflow_status import paint
        paint(w.bulk_pr_button,'Đang đồng bộ Sheets' if 'đang đồng bộ' in message.casefold() else 'Đã ghi · Sheets cần thử lại' if 'chưa xác nhận' in message.casefold() else 'Đợt kiểm hoàn tất', 'running' if 'đang đồng bộ' in message.casefold() else 'warning' if 'chưa xác nhận' in message.casefold() else 'done')
        w.sheets_last_status=message;w.statusBar().showMessage(message)
        result_page=getattr(w,'batch_result_page',None)
        if result_page is not None and hasattr(result_page,'update_sync_status'):result_page.update_sync_status(message)
        current=getattr(w,'sheets_page',None)
        if current is not None:current.set_sync_progress(message)
        w.show_top_notice('Google Sheets',message)
    status('Đã ghi sổ; đang đồng bộ Google Sheets…')
    superseded_before_write=[False]
    def sync():
        signature=file_signature(path);cache={}
        summary,records=ledger.summary(path,lambda p:w._ledger_valid(p,cache))
        validation_before={p['receipt_id']:dict(w._ledger_valid(p,{})) for p in records if p['active']}
        suppliers={}
        for active in (False,True):
            for record in records:
                name=str(record.get('supplier_name') or '').strip()
                if bool(record['active'])==active and name:suppliers[record['order_id']]=name
        client=SheetsClient(root)
        from receiving_department_sheets import preview as plan_departments
        from receiving_pr_library import load
        preview=plan_departments(client,summary,records,suppliers,load(w.pr_library_directory()),progress=job.signals.progress.emit)
        if file_signature(path)!=signature or w.ledger_path()!=path:
            superseded_before_write[0]=w.ledger_path()==path
            raise ValueError('Sổ đã đổi khi đồng bộ; cần xem trước lại.')
        if any(dict(w._ledger_valid(p,{}))!=validation_before[p['receipt_id']] for p in records if p['active']):raise ValueError('Nguồn phiếu đã đổi; cần cập nhật sổ và xem trước lại.')
        from receiving_department_sheets import apply_preview
        changed=apply_preview(client,preview,progress=job.signals.progress.emit)
        return dict(changed=changed,skipped=preview.get('skipped',0))
    job=Worker(sync);succeeded=[False]
    def done(result):
        count=result.get('changed',0) if isinstance(result,dict) else result
        skipped=result.get('skipped',0) if isinstance(result,dict) else 0
        if skipped:
            message=f'Đã cập nhật {count} dòng; chưa xác nhận đồng bộ đầy đủ: còn {skipped} dòng cần rà. Mở Google Sheets để xem trước lại.'
            ledger.sync_result(path,outbox_ids,message);status(message)
            current=getattr(w,'sheets_page',None)
            if current is not None:current.summary.setText(message)
            return
        ledger.sync_result(path,outbox_ids)
        succeeded[0]=True;status(f'Đã đồng bộ Google Sheets: {count} dòng thay đổi.')
        current=getattr(w,'sheets_page',None)
        if current is not None:current.summary.setText(f'Đã đồng bộ · {count} thay đổi')
    def failed(message):
        ledger.sync_result(path,outbox_ids,message)
        if superseded_before_write[0] and w.sheets_sync_pending:
            status('Đã lưu quyết định mới trên máy; đang gộp thay đổi để tải lại và đồng bộ Sheets…');return
        status('Đã giữ sổ trên máy; chưa xác nhận đồng bộ Sheets: '+message+' · Mở Google Sheets, làm mới xem trước để kiểm tra. Không tự gửi lại.')
        w.show_top_notice('Chưa xác nhận đồng bộ Google Sheets',message+' · Sổ trên máy được giữ. Làm mới xem trước để kiểm tra.',variant='warning')
    def finish():
        pending=w.sheets_sync_pending;w.sheets_sync_pending=False;w.sheets_sync_running=False
        current=getattr(w,'sheets_page',None)
        if current is not None:current.sync_progress.hide();current.running=False;current.reload.setEnabled(True);current.save.setEnabled(False)
        result_page=getattr(w,'sync_results_page',None)
        if result_page is not None:result_page.refresh_events()
        if pending and (succeeded[0] or superseded_before_write[0]) and w.ledger_path()==path:QTimer.singleShot(0,lambda:start(w))
    job.signals.progress.connect(lambda message:(setattr(w,'sheets_last_status',message),w.statusBar().showMessage(message),getattr(w,'sheets_page',None).set_sync_progress(message) if getattr(w,'sheets_page',None) is not None else None))
    job.signals.result.connect(done);job.signals.error.connect(failed);job.signals.finished.connect(finish)
    w._start_worker(job)
