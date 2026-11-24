"""Screen44: explain missing receipt images without substituting other pages."""
from pathlib import Path
from receiving_image_archive import image_name, source_digest
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton

def missing(w):
    from receiving_service import invoice_images
    refs=invoice_images(w.current_sheet,w.data_by_sheet.get(w.current_sheet,[]))
    available=set()
    for p in w.images:
        if image_name(p) not in refs:continue
        try:
            if p.is_file():
                source_digest(p)  # Verify manifest-backed copies before clearing the warning.
                available.add(image_name(p))
        except (OSError,ValueError,KeyError):
            continue
    rows=w.data_by_sheet.get(w.current_sheet,[])
    explicit=any(str(v.get('Ảnh nguồn') or '').strip() or str(v.get('Các ảnh cùng phiếu') or '').strip() for _,v in rows)
    if not explicit:return [] if refs & available or not w.current_sheet else [w.current_sheet+' (ảnh gốc)']
    return sorted(refs-available) if refs else (['Chưa có tham chiếu ảnh nguồn'] if w.current_sheet else [])

def refresh(w):
    if not hasattr(w,'receipt_page'):return
    panel=getattr(w,'missing_source_panel',None)
    if panel is None:
        panel=QWidget();panel.setObjectName('missingSourcePanel');v=QVBoxLayout(panel);v.setContentsMargins(16,12,16,12)
        panel.setStyleSheet('QWidget#missingSourcePanel {background:#fffaf0;border:1px solid #f2e6ca;border-radius:9px;}')
        label=QLabel();label.setObjectName('missingSourceDetail');label.setWordWrap(True);v.addWidget(label)
        row=QHBoxLayout();row.addStretch();retry=QPushButton('Mở lại phiếu');retry.setObjectName('missingSourceRetry');row.addWidget(retry);v.addLayout(row)
        retry.clicked.connect(lambda: w.open_day() if not w.busy else None)
        w.receipt_page.layout().insertWidget(1,panel);w.missing_source_panel=panel
    absent=missing(w);panel.setVisible(bool(absent))
    panel.findChild(QLabel,'missingSourceDetail').setText('Thiếu ảnh nguồn · '+w.current_sheet+'\nẢnh không còn ở đường dẫn đã lưu: '+', '.join(absent)+'\nKhôi phục đúng ảnh gốc rồi mở lại phiếu. Chưa xác minh được lượng; không thay bằng ảnh gần giống.')
    if absent and not w.reference_mode and getattr(w.preview,'source_path',None) is not None and not w.preview.source_path.is_file():
        w.preview.clear_image('Thiếu ảnh nguồn — khôi phục đúng ảnh gốc để đối chiếu')
