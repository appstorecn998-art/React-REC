"""Explicit, receipt-bound selection of a previously stored PR."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QDialogButtonBox,QMessageBox,QSplitter
import receiving_pr_library as library

def show(w,selected_key=None):
    if w.busy or not w.current_sheet or not w._leave_pr():return False
    path=w.reference_link_path();before=path.read_bytes() if path.exists() else None
    context=(str(w.report),w.current_sheet,w.source_hash,str(w.pr_library_directory()))
    records=library.load(w.pr_library_directory())
    from receiving_pr_number_identity import rank_suggestions
    entries=[dict(key=key,record=record,title=library.title(record),complete=False) for key,record in records.items()]
    ranked=rank_suggestions(entries,{},w.data_by_sheet.get(w.current_sheet,[]))
    reasons={entry['key']:entry.get('suggestion_reason','').replace('Có mặt hàng phù hợp','Tên mặt hàng có từ trùng; cần rà quy cách') for entry in ranked}
    dialog=QDialog(w);dialog.setObjectName('assignStoredPR');dialog.setWindowTitle('Ghép PR đã lưu');dialog.resize(1060,720)
    layout=QVBoxLayout(dialog);heading=QLabel('Chọn PR cho phiếu '+w.current_sheet);heading.setStyleSheet('font-size:18px;font-weight:600;');layout.addWidget(heading)
    search=QLineEdit();search.setPlaceholderText('Tìm số PR, nhà cung cấp hoặc ngày…');search.setClearButtonEnabled(True);layout.addWidget(search)
    split=QSplitter();listing=QListWidget();listing.setObjectName('assignStoredPRList');split.addWidget(listing)
    from receiving_qt import PreviewView
    preview=PreviewView();split.addWidget(preview);split.setSizes([430,600]);layout.addWidget(split,1)
    note=QLabel('Chọn để xem ảnh. Chỉ ghép khi bấm xác nhận; không tự đổi PR đang gán.');note.setWordWrap(True);layout.addWidget(note)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);confirm=box.button(QDialogButtonBox.Save);confirm.setText('Ghép PR này');confirm.setEnabled(False);layout.addWidget(box)
    state={'key':None};original_key=None
    if before:
        import json
        original_key=json.loads(before).get('library_key')
    preferred=selected_key or original_key
    def fill():
        from supplier_rules import normalize_name
        selected=listing.currentItem().data(Qt.UserRole) if listing.currentItem() else preferred
        listing.blockSignals(True);listing.clear();query=normalize_name(search.text())
        for entry in ranked:
            key=entry['key'];record=entry['record'];title=entry['title']
            if query and query not in normalize_name(title):continue
            reason=reasons[key]
            item=QListWidgetItem(('Gợi ý · ' if reason else '')+title+('\nGợi ý: '+reason if reason else '\nChưa có dấu hiệu phù hợp với phiếu này'));item.setToolTip(item.text());item.setData(Qt.UserRole,key);listing.addItem(item)
        index=next((i for i in range(listing.count()) if listing.item(i).data(Qt.UserRole)==selected),0 if listing.count() else -1)
        listing.setCurrentRow(index);listing.blockSignals(False);selected_row()
    def selected_row(*_):
        item=listing.currentItem();state['key']=item.data(Qt.UserRole) if item else None;confirm.setEnabled(False)
        if not item:preview.clear_image('Không có PR phù hợp');return
        try:
            images=library.images_for(records[state['key']]);preview.set_image(images[0]);confirm.setEnabled(True);note.setText((('Gợi ý: '+reasons[state['key']]) if reasons[state['key']] else 'Chưa có bằng chứng phù hợp; kiểm tra kỹ trước khi ghép.')+' · '+str(len(images))+' trang. Gợi ý chưa phải xác nhận đúng PR.')
        except (OSError,ValueError) as exc:preview.clear_image('Chưa đọc được ảnh PR');note.setText(str(exc))
    search.textChanged.connect(fill);listing.currentRowChanged.connect(selected_row);box.rejected.connect(dialog.reject)
    def assign():
        try:
            current=(str(w.report),w.current_sheet,w.source_hash,str(w.pr_library_directory()))
            if context!=current or w.reference_link_path()!=path:raise ValueError('Phiếu đang chọn đã đổi. Mở lại cửa sổ ghép PR.')
            if (path.read_bytes() if path.exists() else None)!=before:raise ValueError('Liên kết PR vừa thay đổi. Mở lại để kiểm tra; chưa ghi đè.')
            key=state['key']
            if not key:return
            if before is not None and key!=original_key:
                answer=QMessageBox.question(dialog,'Thay PR đã gán?','Thay PR của phiếu '+context[1]+' bằng '+library.title(records[key])+'?\nBản đối chiếu cũ sẽ cần rà lại.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
                if answer!=QMessageBox.Yes:return
            if context!=(str(w.report),w.current_sheet,w.source_hash,str(w.pr_library_directory())) or w.reference_link_path()!=path:
                raise ValueError('Phiếu đã đổi trong lúc xác nhận. Chưa ghép PR; mở lại hộp chọn.')
            w.use_library_pr(key,expected=before)
            w.reference_image=None
            if w.reference_mode:w.toggle_reference_images()
            w.update_pr_status();dialog.accept()
        except (OSError,ValueError,KeyError) as exc:QMessageBox.warning(dialog,'Chưa ghép PR',str(exc))
    confirm.clicked.connect(assign);fill()
    dialog.setStyleSheet('QDialog {background:white;color:#40506c;font-family:Segoe UI;font-size:13px;} QLineEdit {min-height:36px;border:1px solid #dfe4ed;border-radius:7px;padding:0 10px;} QListWidget {border:1px solid #e3e4ee;border-radius:7px;outline:0;} QListWidget::item {padding:12px;border-bottom:1px solid #f0f1f6;} QListWidget::item:selected {background:#ece8ff;color:#5143bd;} QPushButton {min-height:36px;padding:0 14px;border:1px solid #dfe4ed;border-radius:7px;}')
    try:return dialog.exec()==QDialog.Accepted
    finally:preview.pool.waitForDone()
