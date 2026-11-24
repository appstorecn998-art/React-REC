"""Navigation controls over the visible image, without layout columns."""
from PySide6.QtCore import QObject,QEvent,QTimer,QRect
from PySide6.QtWidgets import QPushButton
from shiboken6 import isValid

class PageArrows(QObject):
    def __init__(self,preview,combo):
        super().__init__(preview)
        self.preview=preview;self.combo=combo
        self.left=QPushButton('‹',preview);self.right=QPushButton('›',preview)
        for button,label in [(self.left,'Ảnh trước'),(self.right,'Ảnh sau')]:
            button.setFixedSize(34,48);button.setAccessibleName(label)
            button.setStyleSheet('QPushButton {background:rgba(20,30,45,35);color:white;border:0;border-radius:8px;font-size:30px;} QPushButton:hover {background:rgba(20,30,45,130);} QPushButton:pressed {background:rgba(20,30,45,185);}')
        self.left.clicked.connect(lambda:self.move(-1));self.right.clicked.connect(lambda:self.move(1))
        combo.currentIndexChanged.connect(self.sync)
        combo.model().rowsInserted.connect(lambda *_:QTimer.singleShot(0,self.sync))
        combo.model().rowsRemoved.connect(lambda *_:QTimer.singleShot(0,self.sync))
        combo.model().modelReset.connect(lambda *_:QTimer.singleShot(0,self.sync))
        preview.viewport().installEventFilter(self)
        preview.horizontalScrollBar().valueChanged.connect(self._position)
        preview.verticalScrollBar().valueChanged.connect(self._position)
        self.sync()
    def move(self,delta):
        n=self.combo.count()
        if n>1:self.combo.setCurrentIndex((self.combo.currentIndex()+delta)%n)
        self.sync()
    def _position(self,*_):
        if not isValid(self.preview) or not isValid(self.combo):return
        view=self.preview;rect=view.viewport().rect()
        if view.item is not None:
            try:rect=rect.intersected(view.mapFromScene(view.item.sceneBoundingRect()).boundingRect())
            except RuntimeError:rect=QRect()  # Scene may have just cleared the old item.
        visible=self.combo.count()>1 and view.item is not None and rect.width()>=90 and rect.height()>=60
        for button in (self.left,self.right):
            if button.isHidden()==visible:
                button.setVisible(visible)
                if visible:button.raise_()
        if not visible:return
        origin=view.viewport().geometry().topLeft();y=origin.y()+rect.center().y()-24
        self.left.move(origin.x()+rect.left()+8,y)
        self.right.move(origin.x()+rect.right()-41,y)
    def sync(self,*_):
        if not isValid(self) or not isValid(self.preview) or not isValid(self.combo):return
        n=self.combo.count();i=self.combo.currentIndex();self.combo.hide()
        self._position()
        for button,label in [(self.left,'Ảnh trước'),(self.right,'Ảnh sau')]:button.setToolTip(f'{label} · {i+1}/{n}')
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Resize,QEvent.Show,QEvent.Paint):self._position()
        return super().eventFilter(obj,event)
