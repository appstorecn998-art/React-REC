"""Remove an accidental receipt from the current day, retaining its source archive."""
from pathlib import Path
import json,os,tempfile,shutil,sqlite3
from datetime import datetime
from openpyxl import load_workbook
from receiving_service import digest,invoice_pages,atomic_json
from receiving_image_archive import source_digest
from multi_delivery import output_lock

def remove(report,expected,sheet,images,ledger=None,allow_no_images=False,*,day=None):
    report=Path(report);meta=report.parent/'.receiving';excluded=meta/'excluded-images.json'
    # Require reversal through the ledger flow for committed receipts.
    if ledger and Path(ledger).exists():
        conn=sqlite3.connect(Path(ledger).resolve().as_uri()+'?mode=ro',uri=True)
        try:
            for raw, in conn.execute('SELECT payload FROM receipts WHERE active=1'):
                payload=json.loads(raw)
                if payload.get('sheet')==sheet and (day is None or payload.get('day') in (None,day)):
                    raise ValueError('Phiếu đã ghi sổ. Cần hủy ghi nhận trong Sổ nhận hàng trước khi xóa ảnh/phiếu.')
        finally:conn.close()
    with output_lock(report):
        if digest(report)!=expected:raise ValueError('Phiếu đã thay đổi. Tải lại trước khi xóa.')
        b=load_workbook(report);tmp=None
        try:
            if sheet not in b.sheetnames:raise ValueError('Phiếu không còn tồn tại.')
            old=json.loads(excluded.read_text(encoding='utf-8')) if excluded.exists() else []
            if not images and not allow_no_images:raise ValueError('Không xác định được ảnh nguồn; chưa xóa để tránh mất dữ liệu.')
            hashes={digest(p) for p in images}|{source_digest(p) for p in images}
            backup=report.parent/'.autowatcher-backups'/('remove-receipt-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True)
            shutil.copy2(report,backup/report.name)
            if excluded.exists():shutil.copy2(excluded,backup/excluded.name)
            atomic_json(backup/'removal.json',{'sheet':sheet,'images':[str(p) for p in images],'reason':'Người dùng xóa ảnh thêm nhầm'})
            b.remove(b[sheet])
            if not b.sheetnames:b.create_sheet('Chưa có phiếu')
            fd,tmp=tempfile.mkstemp(dir=report.parent,suffix='.xlsx');os.close(fd);b.save(tmp)
            if digest(report)!=expected:raise ValueError('Báo cáo vừa đổi; chưa xóa.')
            atomic_json(excluded,sorted(set(old)|hashes))
            try:os.replace(tmp,report)
            except Exception:
                atomic_json(excluded,old);raise
            return backup
        finally:
            b.close()
            if tmp:Path(tmp).unlink(missing_ok=True)

def show(w):
    from PySide6.QtWidgets import QMessageBox
    from receiving_qt import Worker
    from receiving_service import accounting_root
    if w.busy or not w.current_sheet or not w._leave_pr():return
    sheet=w.current_sheet;rows=w.data_by_sheet.get(sheet,[]);images=invoice_pages(sheet,rows,w.images)
    text=f'Gỡ phiếu {sheet} và {len(images)} ảnh nguồn khỏi ngày đang làm?\nPhiếu nhiều trang sẽ được gỡ cùng nhau. Ảnh gốc và bản sao lưu vẫn được giữ.'
    if QMessageBox.question(w,'Xóa ảnh / phiếu thêm nhầm',text)!=QMessageBox.Yes:return
    report,expected=w.report,w.source_hash;ledger=accounting_root(w.destination)/'.receiving/receiving-ledger.sqlite'
    task=Worker(remove,report,expected,sheet,images,ledger);w.set_busy(True)
    task.signals.result.connect(lambda _:w.statusBar().showMessage('Đã gỡ ảnh/phiếu thêm nhầm. Ảnh gốc và bản sao lưu được giữ.'))
    task.signals.error.connect(lambda message:QMessageBox.warning(w,'Chưa xóa',message))
    def finished():w.set_busy(False);w.open_day()
    task.signals.finished.connect(finished);w._start_worker(task)
