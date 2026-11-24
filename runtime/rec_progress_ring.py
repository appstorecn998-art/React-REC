"""Small honest progress indicator: determinate counts or waiting spinner."""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt,QTimer,QRectF
from PySide6.QtGui import QPainter,QPen,QColor
class ProgressRing(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(64,64);self.value=None;self.angle=0
        self.timer=QTimer(self);self.timer.setInterval(80);self.timer.timeout.connect(self.tick)
    def tick(self):self.angle=(self.angle+18)%360;self.update()
    def set_progress(self,value=None):
        self.value=value
        if value is None:self.timer.start()
        else:self.timer.stop()
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);r=QRectF(6,6,52,52)
        p.setPen(QPen(QColor('#e5eaf2'),5));p.drawEllipse(r)
        p.setPen(QPen(QColor('#1670ef'),5,Qt.SolidLine,Qt.RoundCap))
        p.drawArc(r,int((90-self.angle if self.value is None else 90)*16),int(-100*16 if self.value is None else -max(0,min(100,self.value))*3.6*16))
        p.setPen(QColor('#243447'));p.drawText(self.rect(),Qt.AlignCenter,'…' if self.value is None else str(int(self.value))+'%')
