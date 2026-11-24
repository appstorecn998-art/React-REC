"""Receipt display order is independent of worksheet and accounting row order."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView,QMessageBox


def ordered(folder,data):
    path=Path(folder)/'receipt-order.json'
    try:
        names=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(names,list) or any(not isinstance(n,str) for n in names):return list(data)
    except (OSError,ValueError):return list(data)
    rank={name:i for i,name in enumerate(dict.fromkeys(names))}
    return sorted(data,key=lambda entry:rank.get(entry[0],len(rank)))


def install(w):
    listing=w.receipt_list
    listing.setDragDropMode(QAbstractItemView.InternalMove)
    listing.setDefaultDropAction(Qt.MoveAction)
    listing.setDragDropOverwriteMode(False)
    listing.setDropIndicatorShown(True)
    listing.setAutoScroll(True)
    listing.setToolTip('Giữ chuột kéo phiếu đến vị trí mới. Thứ tự được lưu riêng cho ngày đang chọn.')
    listing.setStyleSheet(listing.styleSheet()+' QListWidget::drop-indicator {height:3px;background:#6552df;}')
    def moved(*_):
        if not w.folder:return
        visible=[listing.item(i).data(Qt.UserRole) for i in range(listing.count())]
        # Filtered lists reorder only their own slots; hidden receipts keep their place.
        full=[name for name,_ in ordered(w.folder,w.data)]
        slots=iter(visible);shown=set(visible)
        names=[next(slots) if name in shown else name for name in full]
        try:
            from receiving_service import atomic_json
            atomic_json(Path(w.folder)/'receipt-order.json',names)
        except OSError as exc:
            QMessageBox.warning(w,'Chưa lưu thứ tự phiếu',str(exc));w.filter_receipts();return
        i=listing.currentRow()
        w.previous.setEnabled(i>0);w.next.setEnabled(i>=0 and i<listing.count()-1)
        w.position.setText(f'Phiếu {i+1} / {listing.count()}')
        w.statusBar().showMessage('Đã lưu thứ tự phiếu trong ngày.',3000)
    listing.model().rowsMoved.connect(moved)
    busy=w.set_busy
    def set_busy(*args,**kwargs):
        result=busy(*args,**kwargs)
        listing.setDragEnabled(not w.busy);listing.setAcceptDrops(not w.busy)
        return result
    w.set_busy=set_busy
