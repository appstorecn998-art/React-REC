"""Large read-only PR image view using the existing zoom and drag viewer."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QMessageBox
from PySide6.QtCore import Qt
import receiving_pr_library as library


def show(w,key,index=0):
    record=library.load(w.pr_library_directory()).get(key)
    if not record:return
    try:paths=library.images_for(record)
    except (OSError,ValueError) as exc:QMessageBox.warning(w,'Chưa mở được ảnh PR',str(exc));return
    if not paths:return
    from receiving_qt import PreviewView
    dialog=QDialog(w);dialog.setObjectName('prImageZoom');dialog.setWindowTitle('Ảnh PR '+str(record.get('number') or '')+' · Phóng to để đọc')
    layout=QVBoxLayout(dialog);bar=QHBoxLayout();layout.addLayout(bar)
    previous=QPushButton('Trang trước');following=QPushButton('Trang sau');counter=QLabel()
    for widget in [previous,counter,following]:bar.addWidget(widget)
    bar.addStretch()
    preview=PreviewView();preview.setObjectName('largePRPreview');layout.addWidget(preview,1)
    for title,name,callback in [('−','prZoomOut',lambda:preview.zoom_at(1/1.25)),('+','prZoomIn',lambda:preview.zoom_at(1.25)),('Vừa khung','prZoomFit',preview.fit_image)]:
        button=QPushButton(title);button.setObjectName(name);button.setAccessibleName('Thu nhỏ' if title=='−' else 'Phóng to' if title=='+' else title);button.clicked.connect(callback);bar.addWidget(button)
    close=QPushButton('Đóng');close.clicked.connect(dialog.accept);bar.addWidget(close)
    hint=QLabel('Lăn chuột để phóng to/thu nhỏ · Kéo ảnh để di chuyển · Bấm đúp để vừa khung · Esc để đóng');layout.addWidget(hint)
    state={'index':max(0,min(index,len(paths)-1))}
    def display(delta=0):
        state['index']=max(0,min(state['index']+delta,len(paths)-1))
        try:
            current=library.load(w.pr_library_directory()).get(key)
            if current!=record:raise ValueError('Bộ PR đã đổi. Đóng và mở lại để xem ảnh mới.')
            checked=library.images_for(current);preview.set_image(checked[state['index']])
            counter.setText('Trang '+str(state['index']+1)+' / '+str(len(checked)))
            previous.setEnabled(state['index']>0);following.setEnabled(state['index']<len(checked)-1)
        except (OSError,ValueError,IndexError) as exc:
            preview.clear_image(str(exc));previous.setEnabled(False);following.setEnabled(False)
    previous.clicked.connect(lambda:display(-1));following.clicked.connect(lambda:display(1));display()
    screen=w.screen().availableGeometry();dialog.resize(max(640,int(screen.width()*.9)),max(480,int(screen.height()*.9)))
    try:dialog.exec()
    finally:preview.pool.waitForDone()
    return dialog
