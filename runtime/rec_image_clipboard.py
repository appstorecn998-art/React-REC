"""Copy the currently selected source photo, without overlays or UI chrome."""
from pathlib import Path
from PySide6.QtGui import QImageReader,QImage,QIcon,QPixmap,QPainter
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import QApplication,QPushButton,QMessageBox


def publish_bitmap(image):
    import os
    if os.name!='nt':
        QApplication.clipboard().setImage(image)
        return
    import ctypes
    from ctypes import wintypes
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import QByteArray,QBuffer,QIODevice
    # Publish actual bitmap bytes now; a paste must not wait for Qt to render them.
    global _clipboard_owner
    if '_clipboard_owner' not in globals():_clipboard_owner=QWidget()
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.OpenClipboard.argtypes=[wintypes.HWND];user.OpenClipboard.restype=wintypes.BOOL
    user.EmptyClipboard.restype=wintypes.BOOL
    user.CloseClipboard.restype=wintypes.BOOL
    user.SetClipboardData.argtypes=[wintypes.UINT,wintypes.HANDLE];user.SetClipboardData.restype=wintypes.HANDLE
    kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t];kernel.GlobalAlloc.restype=wintypes.HGLOBAL
    kernel.GlobalLock.argtypes=[wintypes.HGLOBAL];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HGLOBAL];kernel.GlobalUnlock.restype=wintypes.BOOL
    kernel.GlobalFree.argtypes=[wintypes.HGLOBAL];kernel.GlobalFree.restype=wintypes.HGLOBAL
    user.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR];user.RegisterClipboardFormatW.restype=wintypes.UINT
    png_format=user.RegisterClipboardFormatW('PNG')
    if not png_format:raise ctypes.WinError(ctypes.get_last_error())
    def encode(format):
        data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.WriteOnly)
        try:
            if not image.save(buffer,format):raise OSError('Không tạo được ảnh clipboard '+format)
        finally:buffer.close()
        return bytes(data)
    # Zalo needs encoded PNG too; standard bottom-up 24-bit DIB supports older readers.
    png=encode('PNG')
    rgb=image.convertToFormat(QImage.Format_RGB888)
    data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.WriteOnly)
    try:
        if not rgb.save(buffer,'BMP'):raise OSError('Không tạo được bitmap clipboard.')
    finally:buffer.close()
    dib=bytes(data)[14:]
    blocks=[];opened=False
    try:
        for format,payload in [(png_format,png),(8,dib)]:
            memory=kernel.GlobalAlloc(0x0002,len(payload))
            if not memory:raise ctypes.WinError(ctypes.get_last_error())
            blocks.append([format,memory])
            pointer=kernel.GlobalLock(memory)
            if not pointer:raise ctypes.WinError(ctypes.get_last_error())
            try:ctypes.memmove(pointer,payload,len(payload))
            finally:kernel.GlobalUnlock(memory)
        if not user.OpenClipboard(int(_clipboard_owner.winId())):raise ctypes.WinError(ctypes.get_last_error())
        opened=True
        if not user.EmptyClipboard():raise ctypes.WinError(ctypes.get_last_error())
        for block in blocks:
            if not user.SetClipboardData(block[0],block[1]):raise ctypes.WinError(ctypes.get_last_error())
            block[1]=None  # Ownership transferred to Windows.
    finally:
        if opened:user.CloseClipboard()
        for _,memory in blocks:
            if memory:kernel.GlobalFree(memory)



def copy_source(path):
    if path is None or not Path(path).is_file():raise ValueError('Chưa có ảnh để sao chép hoặc ảnh nguồn đã mất.')
    reader=QImageReader(str(path));reader.setAutoTransform(True)
    size=reader.size()
    if size.isValid() and max(size.width(),size.height())>1280:
        reader.setScaledSize(size.scaled(QSize(1280,1280),Qt.KeepAspectRatio))
    image=reader.read()
    if image.isNull():raise ValueError('Không đọc được ảnh nguồn để sao chép.')
    # Clipboard images are decoded bitmaps; large phone photos can exceed 90 MB.
    if max(image.width(),image.height())>1280:
        image=image.scaled(QSize(1280,1280),Qt.KeepAspectRatio,Qt.SmoothTransformation)
    image=image.convertToFormat(QImage.Format_RGB32)
    publish_bitmap(image)
    return image.size()


def install(w):
    button=QPushButton();button.setObjectName('copyReceiptImage')
    button.setAccessibleName('Sao chép ảnh để gửi Zalo')
    # Draw the copy glyph locally so it is available in packaged builds too.
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    svg=QSvgRenderer(QByteArray(b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#59657a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>'))
    pixmap=QPixmap(40,40);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);svg.render(painter);painter.end()
    button.setIcon(QIcon(pixmap));button.setIconSize(QSize(20,20))
    button.setStyleSheet('QPushButton#copyReceiptImage {padding:0;min-width:34px;max-width:34px;min-height:32px;max-height:32px;}')
    button.setFixedSize(36,34)
    button.setToolTip('Sao chép ảnh để gửi Zalo. Toàn bộ trang đang xem, cạnh dài tối đa 1280px để dán nhanh. Sang Zalo nhấn Ctrl+V để dán; ảnh không kèm vùng tô sáng hay giao diện REC.')
    w.image_header.addWidget(button)
    def refresh(*_):
        source=w.preview.source_path
        button.setEnabled(source is not None and Path(source).is_file())
    def copy():
        try:
            copy_source(w.preview.source_path)
            w.statusBar().showMessage('Đã sao chép ảnh tối ưu để gửi. Sang Zalo nhấn Ctrl+V để dán.',8000)
        except (OSError,ValueError) as exc:QMessageBox.warning(w,'Chưa sao chép được ảnh',str(exc))
    button.clicked.connect(copy);w.preview.imageChanged.connect(refresh);refresh()
    return button
