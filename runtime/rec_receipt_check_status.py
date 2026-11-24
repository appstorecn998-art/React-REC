"""Read-only receipt card status; delivery review alone is not PR review."""
from rec_pr_review import inspection

class ReceiptContext:
    def __init__(self,w,sheet):self.window=w;self.current_sheet=sheet
    def __getattr__(self,name):return getattr(self.window,name)
    def reference_link_path(self):return type(self.window).reference_link_path(self) if hasattr(type(self.window),'reference_link_path') else self.window.reference_link_path()
    def receipt_references(self):return type(self.window).receipt_references(self) if hasattr(type(self.window),'receipt_references') else self.window.receipt_references()


def compute_status(w,sheet):
    if not w.approved(sheet):return 'Chưa kiểm',False
    context=ReceiptContext(w,sheet)
    from receiving_no_po import active
    rows=w.data_by_sheet.get(sheet,[])
    if active(w.folder,sheet,rows,w.images):return 'Đã kiểm phiếu · Không PR/PO',True
    if not context.receipt_references():return 'Chưa ghép PR',False
    dirty=sheet==w.current_sheet and getattr(w,'pr_dirty',lambda:False)()
    state=inspection(context,context.reference_link_path().with_suffix('.comparison.json'),dirty)['state']
    if state=='done':return 'Đã kiểm',True
    if state=='partial_done':return 'Còn dòng chưa rà PR',False
    return ('PR cần rà lại' if state=='stale' else 'Chờ rà PR'),False



def _stamp(w):
    from pathlib import Path
    # Stat metadata, never read/hash photographs on the GUI thread.
    paths=[]
    if w.folder:
        folder=Path(w.folder)
        for name in ('.receiving/manual-pr-links','.receiving/no-po'):
            paths.extend((folder/name).glob('*.json'))
    paths.append(Path(w.pr_library_directory())/'index.json')
    paths.extend(w.images)
    paths.extend(Path(p).parent/'image-manifest.json' for p in w.images)
    values=[]
    for path in set(map(Path,paths)):
        try:
            st=path.stat();values.append((str(path),st.st_size,st.st_mtime_ns,st.st_ctime_ns))
        except OSError:values.append((str(path),None))
    return (str(w.folder),str(w.report),w.source_hash,tuple(sorted(w.reviews.items())),tuple(sorted(values)))


def _queue(w):
    if getattr(w,'_card_status_queued',False):return
    from PySide6.QtCore import QTimer
    w._card_status_queued=True
    QTimer.singleShot(0,lambda:_start(w))


def status(w,sheet):
    if not w.approved(sheet):return 'Chưa kiểm',False
    if sheet==w.current_sheet and getattr(w,'pr_dirty',lambda:False)():return 'PR cần rà lại',False
    _queue(w)
    cache=getattr(w,'_card_status_cache',{})
    key=(str(w.folder),w.source_hash,sheet)
    return cache.get(key,('Đang kiểm tra PR…',False))


def _start(w):
    from shiboken6 import isValid
    if not isValid(w):return
    w._card_status_queued=False
    if getattr(w,'_card_status_running',False):return
    stamp=_stamp(w)
    if stamp==getattr(w,'_card_status_stamp',None):return
    from types import SimpleNamespace,MethodType
    from copy import deepcopy
    from receiving_qt import Worker
    window_type=type(w)
    snap=SimpleNamespace(current_sheet='',data_by_sheet=deepcopy(w.data_by_sheet),images=list(w.images),folder=w.folder,report=w.report,root=w.root,pr_dirty=lambda:False)
    snap.reference_link_path=MethodType(window_type.reference_link_path,snap)
    snap.receipt_references=MethodType(window_type.receipt_references,snap)
    library=w.pr_library_directory();snap.pr_library_directory=lambda:library
    approved={name:w.approved(name) for name in w.data_by_sheet}
    snap.approved=lambda name:approved.get(name,False)
    source_hash=w.source_hash
    w._card_status_running=True
    # Drop cached labels until this generation has been verified.
    w._card_status_cache={}
    def work():
        result={}
        for sheet in snap.data_by_sheet:
            snap.current_sheet=sheet
            try:result[sheet]=compute_status(snap,sheet)
            except (OSError,ValueError,KeyError,TypeError):result[sheet]=('PR cần kiểm tra nguồn',False)
        return result
    def ready(result):
        if not isValid(w) or _stamp(w)!=stamp:return
        w._card_status_stamp=stamp
        w._card_status_cache={(str(w.folder),source_hash,sheet):value for sheet,value in result.items()}
        # Refresh chips in place: rebuilding cards also reselects/reloads the image.
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        for i in range(w.receipt_list.count()):
            item=w.receipt_list.item(i);sheet=item.data(Qt.UserRole)
            card=w.receipt_list.itemWidget(item)
            if card is None:continue
            label,checked=result.get(sheet,('PR cần kiểm tra nguồn',False))
            for chip in card.findChildren(QLabel):
                if chip.objectName() not in ('checkedChip','pendingChip'):continue
                name='checkedChip' if checked else 'pendingChip'
                if chip.text()==label and chip.objectName()==name:continue
                chip.setText(label);chip.setObjectName(name)
                chip.style().unpolish(chip);chip.style().polish(chip)
        if w.filter_box.currentText()!='Tất cả phiếu':w.filter_receipts()
    def failed(_):
        if isValid(w):
            w._card_status_stamp=stamp
            w._card_status_cache={(str(w.folder),source_hash,sheet):('PR cần kiểm tra nguồn',False) for sheet in snap.data_by_sheet}
    def finished():
        if not isValid(w):return
        w._card_status_running=False
        if _stamp(w)!=stamp:_queue(w)
    job=Worker(work);job.signals.result.connect(ready);job.signals.error.connect(failed);job.signals.finished.connect(finished)
    w._start_worker(job)
