"""Click-controlled navigation with a compact captioned rail."""
from PySide6.QtCore import QObject,QEvent,Qt,QRect,QSize,QSettings
from PySide6.QtGui import QPainter,QColor,QFont
from PySide6.QtWidgets import QPushButton
from fluent_blue.icons import icon as make_icon

class CompactPaint(QObject):
    def __init__(self,side):super().__init__(side);self.side=side
    def eventFilter(self,item,event):
        if event.type()!=QEvent.Paint or not self.side.is_collapsed():return False
        painter=QPainter(item);painter.setRenderHint(QPainter.Antialiasing)
        if item.isChecked() or item.underMouse() or item.hasFocus():
            painter.setPen(Qt.NoPen);painter.setBrush(QColor('#eeebff' if item.isChecked() else '#f0eef7'))
            painter.drawRoundedRect(item.rect().adjusted(1,1,-1,-1),8,8)
        make_icon(item.icon_name,28,'primary-text' if item.isChecked() else 'text-secondary').paint(painter,QRect((item.width()-28)//2,6,28,28))
        painter.setPen(QColor('#5548c3' if item.isChecked() else '#657086'))
        font=QFont('Segoe UI');font.setPixelSize(10);painter.setFont(font)
        caption={'Tiếp nhận ảnh':'Nhận ảnh','Kiểm tra phiếu':'Kiểm phiếu','Tra cứu danh mục':'Danh mục','Google Sheets':'Sheets'}.get(item.key,item.key)
        painter.drawText(QRect(0,35,item.width(),20),Qt.AlignHCenter|Qt.AlignTop,caption)
        painter.end();return True

def install(w):
    settings=QSettings("REC Software","REC")
    saved_collapsed=settings.value("navigation/collapsed",False,type=bool)
    side=w.fluent_nav;host=w.fluent_host
    icons={'Tổng quan':'dashboard','Tiếp nhận ảnh':'image','Kiểm tra phiếu':'check-circle',
           'Thư viện PR':'folder-open','Sổ nhận hàng':'list-ordered','Chờ giao bù':'clock',
           'Giá mua':'table','Google Sheets':'table','Xuất phiếu':'download','Tra cứu danh mục':'search',
           'Nhà cung cấp':'users','Cài đặt':'settings'}
    for key,name in icons.items():
        item=side.item(key);item.icon_name=name;item.refresh_theme()
    side.hover_enabled=False;side.collapse_timer.stop()
    side._expanded_width=200;side._collapsed_width=84
    from PySide6.QtGui import QIcon,QPixmap
    pix=QPixmap(24,24);pix.fill(Qt.transparent)
    ink=QPainter(pix);ink.setPen(QColor('#56647b'))
    for y in (6,12,18):ink.drawLine(3,y,21,y)
    ink.end()
    button=QPushButton();button.setIcon(QIcon(pix));button.setIconSize(QSize(24,24));button.setObjectName('navigationMenu')
    button.setAccessibleName('Mở hoặc thu gọn thanh điều hướng');button.setFixedSize(40,40)
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet('QPushButton {border:0;border-radius:20px;background:transparent;color:#56647b;font-size:23px;} QPushButton:hover {background:#eeebff;}')
    side.header_layout.setContentsMargins(16,6,0,6);side.header_layout.addWidget(button)
    painter=CompactPaint(side);side.compact_painter=painter;side.menu_button=button
    for key in side.keys():
        item=side.item(key);item.installEventFilter(painter);item.setAccessibleName(key)
        item.setIconSize(QSize(26,26))
    def apply(collapsed):
        side.collapse_timer.stop();side._collapsed=collapsed
        side.setFixedWidth(84 if collapsed else 200)
        for label in side._section_labels:label.setVisible(not collapsed)
        for key in side.keys():
            item=side.item(key);item.set_collapsed(collapsed);item.setFixedHeight(62 if collapsed else 46)
            item.setToolTip(key);item.update()
        button.setToolTip('Mở menu' if collapsed else 'Thu gọn menu')
        button.setProperty('expanded',not collapsed)
        host.sync_side()
        settings.setValue("navigation/collapsed",bool(collapsed));settings.sync()
    side.set_collapsed=apply
    button.clicked.connect(lambda:apply(not side.is_collapsed()))
    apply(saved_collapsed)
