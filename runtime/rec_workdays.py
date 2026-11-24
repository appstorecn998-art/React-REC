"""Receiving operates Monday through Friday."""
from datetime import timedelta
from PySide6.QtCore import QDate,Qt,QEvent
from shiboken6 import isValid
from PySide6.QtWidgets import QCalendarWidget,QTableView


def previous_workday(day):
    return day-timedelta(days=max(0,day.weekday()-4))


class WorkdayCalendar(QCalendarWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setProperty('recWeekdaysOnly',True)
        self.setFirstDayOfWeek(Qt.Monday)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self._last=QDate(previous_workday(__import__('datetime').date.today()))
        self.setSelectedDate(self._last)
        self.selectionChanged.connect(self._validate)
        view=self.findChild(QTableView,'qt_calendar_calendarview')
        self._view=view
        if view:
            view.installEventFilter(self);view.viewport().installEventFilter(self)
        self.setToolTip('Chọn ngày làm việc từ thứ Hai đến thứ Sáu. Thứ Bảy và Chủ nhật nghỉ.')
    def _validate(self):
        selected=self.selectedDate()
        if selected.dayOfWeek()>5:
            blocked=self.blockSignals(True)
            try:self.setSelectedDate(self._last)
            finally:self.blockSignals(blocked)
        else:self._last=selected
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease,QEvent.MouseButtonDblClick) and getattr(self,'_view',None) is not None and isValid(self._view) and obj is self._view.viewport():
            index=self._view.indexAt(event.position().toPoint())
            if index.isValid() and index.row()>0 and index.column()>=5:return True
        return super().eventFilter(obj,event)
