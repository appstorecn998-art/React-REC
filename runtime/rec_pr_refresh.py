"""Rebuild captured PR callbacks after receipt inputs have actually changed."""
from copy import deepcopy
from rec_pr_review import canonical,RECEIPT_FIELDS,comparable_receipt


def reconcile(state,old_rows,new_rows):
    old=dict(old_rows);new=dict(new_rows)
    identity=('Tên hàng trên phiếu (Ảnh)','Ảnh nguồn','STT trên phiếu')
    same_identity=lambda row:row in old and row in new and all(old[row].get(k)==new[row].get(k) for k in identity)
    links={p:row for p,row in state['links'].items() if row is None or same_identity(row)}
    allocated={r['pr_index']:r.get('row') for r in state['results'] if r.get('pr_index') is not None}
    conversions={}
    for p,value in state['conversions'].items():
        row=allocated.get(p)
        if row is not None and same_identity(row) and comparable_receipt([(row,{k:old[row].get(k) for k in RECEIPT_FIELDS})])==comparable_receipt([(row,{k:new[row].get(k) for k in RECEIPT_FIELDS})]):
            conversions[p]=deepcopy(value)
    return links,conversions


def rebuild(w,state,old_rows):
    from receiving_pr_image_identity import pr_images_match
    from PySide6.QtWidgets import QMessageBox
    images=w.receipt_references()
    # Retire callbacks that captured the previous rows, including pending autosave.
    panel=getattr(w,'pr_panel',None)
    if panel is not None and hasattr(panel,'draft_timer'):panel.draft_timer.stop()
    w.pr_dirty=lambda:False
    w.pr_save_draft=None
    if not pr_images_match(state['images'],images):
        if panel is not None:panel.hide();panel.setParent(None);panel.deleteLater();del w.pr_panel
        w.pr_sheet=None
        w.pr_placeholder.setText('Bộ ảnh PR đã đổi. Mở lại tab PR để đối chiếu nguồn mới.');w.pr_placeholder.show()
        w.update_pr_status()
        return
    tab=w.review_tabs.currentIndex()
    try:
        preserved=reconcile(state,old_rows,w.data_by_sheet[w.current_sheet])
        w.show_pr_comparison(state['items'],w.data_by_sheet[w.current_sheet],images,preserved=preserved)
        # This saves fresh calculations as a draft; it never re-confirms review.
        if not w.pr_save_draft():raise ValueError(w.statusBar().currentMessage() or 'Chưa lưu được bản đối chiếu mới.')
        w.statusBar().showMessage('Đã cập nhật đối chiếu PR theo phiếu vừa sửa. Rà kết quả mới trước khi xác nhận.',7000)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        if getattr(w,'pr_panel',None) is panel:
            panel.hide();panel.setParent(None);panel.deleteLater();del w.pr_panel
        w.pr_sheet=None
        QMessageBox.warning(w,'Chưa cập nhật được đối chiếu PR',str(exc))
    finally:
        w.review_tabs.blockSignals(True);w.review_tabs.setCurrentIndex(tab);w.review_tabs.blockSignals(False)
