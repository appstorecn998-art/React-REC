"""Shared REC navigation: overlays never participate in content sizing."""
import os
os.environ['FLUENT_BLUE_QT_BINDING']='PySide6'
from fluent_blue import Sidebar, Button, ThemeManager
from PySide6.QtCore import QTimer, QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
class HoverSidebar(Sidebar):
    """Icon rail with delayed hover expansion and an explicit pin for touch/keyboard."""
    def __init__(self):
        super().__init__(width=210,collapsed_width=56,tone='default')
        self.pinned=True
        self.hover_enabled=False
        self.collapse_timer=QTimer(self);self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self.collapse_if_free)
        self.pin=Button('',icon='sidebar',variant='secondary',tooltip='Ghim / bỏ ghim thanh điều hướng')
        self.pin.setCheckable(True);self.pin.toggled.connect(self.set_pinned)
        self.header_layout.addWidget(self.pin)
        self.installEventFilter(self)
    def eventFilter(self,obj,event):
        if obj is self and self.hover_enabled:
            if event.type()==QEvent.Type.Enter:
                self.collapse_timer.stop();self.set_collapsed(False)
            elif event.type()==QEvent.Type.Leave:
                self.collapse_timer.start(300)
        return super().eventFilter(obj,event)
    def set_pinned(self,on):
        self.pinned=on;self.collapse_timer.stop();self.set_collapsed(not on)
    def collapse_if_free(self):
        if not self.pinned and not self.underMouse():self.set_collapsed(True)

class OverlayHost(QWidget):
    def __init__(self, content, side):
        super().__init__()
        self.content=content;self.side=side
        layout=QHBoxLayout(self);layout.setContentsMargins(210,0,0,0);layout.setSpacing(0)
        layout.addWidget(content)
        side.setParent(self);side.move(0,0);side.raise_()
        side.collapsed_changed.connect(lambda _:self.sync_side())
    def sync_side(self):
        self.layout().setContentsMargins(self.side.width(),0,0,0);self.side.raise_()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.side.setFixedHeight(self.height());self.side.move(0,0);self.side.raise_()

