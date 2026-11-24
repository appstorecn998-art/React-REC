"""Clear row spotlight on deliberate clicks outside a row, without disrupting editors/menus."""
from PySide6.QtCore import QObject,QEvent,QModelIndex
from PySide6.QtWidgets import QApplication,QWidget,QMenu
from shiboken6 import isValid

class SelectionFocus(QObject):
    def __init__(self,window):
        super().__init__(window);self.owner=window
        QApplication.instance().installEventFilter(self)
        from rec_calendar_style import install
        install(QApplication.instance())
    def clear(self):
        w=self.owner
        if not isValid(w) or not isValid(w.table) or not w.table.currentIndex().isValid():return
        w.table.clearSelection();w.table.setCurrentIndex(QModelIndex());w.clear_row_region()
    def eventFilter(self,obj,event):
        if event.type()!=QEvent.MouseButtonPress or not isinstance(obj,QWidget):return False
        w=self.owner
        if not isValid(w) or not isValid(obj) or not isValid(w.table) or not w.table.isVisible():return False
        if obj.window() is not w:return False
        panel=getattr(w,'pr_panel',None)
        if panel is not None and (obj is panel or panel.isAncestorOf(obj)):return False
        if QApplication.activePopupWidget() is not None:return False
        if obj is w.table.viewport():
            if not w.table.indexAt(event.position().toPoint()).isValid():self.clear()
        elif not (obj is w.table or w.table.isAncestorOf(obj)):
            self.clear()
        return False
