"""Shared readable ledger surfaces with content-based row heights."""
from PySide6.QtCore import Qt,QRect,QTimer
from PySide6.QtGui import QFontMetrics
from shiboken6 import isValid
from PySide6.QtWidgets import QTableWidget,QFrame,QHBoxLayout,QVBoxLayout,QLabel,QHeaderView

class LedgerTable(QTableWidget):
    def resizeEvent(self,event):
        super().resizeEvent(event)
        weights=getattr(self,'column_weights',None)
        if weights:
            for col,ratio in enumerate(weights):self.setColumnWidth(col,max(70,int(self.viewport().width()*ratio)))
        if not getattr(self,'_fit_pending',False):
            self._fit_pending=True;QTimer.singleShot(0,self.fit_content)
    def fit_content(self):
        if not isValid(self):return
        self._fit_pending=False
        vertical=self.verticalScrollBar().value();horizontal=self.horizontalScrollBar().value()
        for row in range(self.rowCount()):
            height=64
            for col in range(self.columnCount()):
                cell=self.item(row,col)
                if cell:
                    h=QFontMetrics(self.font()).boundingRect(QRect(0,0,max(30,self.columnWidth(col)-28),100000),Qt.TextWordWrap,cell.text()).height()+28
                    height=max(height,h)
            if self.rowHeight(row)!=height:self.setRowHeight(row,height)
        self.verticalScrollBar().setValue(vertical);self.horizontalScrollBar().setValue(horizontal)

def stats(items,parent=None):
    host=QFrame(parent);layout=QHBoxLayout(host);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12);values=[]
    for label,color,bg in items:
        card=QFrame();card.setStyleSheet('QFrame {background:'+bg+';border-radius:9px;} QLabel {color:'+color+';background:transparent;}');v=QVBoxLayout(card);v.setContentsMargins(16,12,16,12)
        number=QLabel('0');number.setStyleSheet('font-size:24px;font-weight:600;');v.addWidget(number);v.addWidget(QLabel(label));layout.addWidget(card,1);values.append(number)
    return host,values

SURFACE='''QHeaderView::section {background:#f1f5f9;color:#475569;font-size:12px;font-weight:600;padding:12px;border:0;border-bottom:1px solid #dce4ee;}
QTableWidget {background:white;color:#334155;font-size:13px;border:1px solid #e2e8f0;border-radius:8px;}
QTableWidget::item {padding:12px;border-bottom:1px solid #edf0f5;}
QTableWidget::item:selected {background:#eeebff;color:#334155;}
QPushButton {min-height:34px;padding:0 14px;border-radius:7px;}
'''
