"""Shared date-picker styling for existing and dynamically created REC pages."""
from PySide6.QtCore import QObject,QEvent,Qt,QLocale,QTimer,QDate,QSize,QRectF,QPointF
from PySide6.QtWidgets import QDateEdit,QCalendarWidget,QToolButton,QStyle,QStyledItemDelegate,QTableView,QWidget
from PySide6.QtGui import QColor,QPainter,QTextCharFormat,QFont,QIcon,QPixmap,QPen,QPolygonF
from shiboken6 import isValid
import weakref

def style_date(edit):
 if not isValid(edit) or edit.property('recCalendarStyled'):return
 edit.setProperty('recCalendarStyled',True)
 if not edit.calendarPopup():return
 style_calendar(edit.calendarWidget())

def style_calendar(calendar):
 if not isValid(calendar) or calendar.property('recCalendarStyled'):return
 calendar.setProperty('recCalendarStyled',True);calendar.setObjectName('recCalendar')
 calendar.setLocale(QLocale('en_GB'));calendar.setFirstDayOfWeek(Qt.Monday)
 calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
 calendar.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
 calendar.setGridVisible(False);calendar.setFixedSize(280,292)
 font=QFont('Segoe UI');font.setPixelSize(12);calendar.setFont(font)
 neutral=QTextCharFormat();neutral.setForeground(QColor('#253047'))
 for day in [Qt.Monday,Qt.Tuesday,Qt.Wednesday,Qt.Thursday,Qt.Friday,Qt.Saturday,Qt.Sunday]:calendar.setWeekdayTextFormat(day,neutral)
 today=QTextCharFormat();today.setForeground(QColor('#0866f5'));today.setFontWeight(QFont.DemiBold);calendar.setDateTextFormat(QDate.currentDate(),today)
 calendar.setStyleSheet('''
 QCalendarWidget#recCalendar {background:white;border:1px solid #e1e3e8;border-radius:10px;min-width:280px;max-width:280px;min-height:292px;max-height:292px;font-family:"Segoe UI";font-size:12px;}
 QCalendarWidget QWidget#qt_calendar_navigationbar {background:white;border:0;min-height:40px;}
 QCalendarWidget QToolButton {background:transparent;color:#182132;border:0;border-radius:6px;padding:2px;min-width:0px;min-height:28px;max-height:28px;font-size:12px;font-weight:600;}
 QCalendarWidget QToolButton:hover {background:#f2f5fa;}
 QCalendarWidget QToolButton::menu-indicator {width:0px;}
 QCalendarWidget QAbstractItemView {background:white;color:#253047;selection-background-color:#0866f5;selection-color:white;border:0;outline:0;font-size:12px;min-width:0px;}
 QCalendarWidget QSpinBox {background:white;color:#253047;border:1px solid #dce1e9;border-radius:4px;min-height:24px;}
 QCalendarWidget QMenu {background:white;color:#334155;border:1px solid #dddfe5;}
 QCalendarWidget QMenu::item {padding:7px 16px;}
 QCalendarWidget QMenu::item:selected {background:#edf4ff;}
 ''')
 view=calendar.findChild(QTableView,'qt_calendar_calendarview')
 if view:
  view.setItemDelegate(CalendarDelegate(view));view.setMouseTracking(True)
 for name,left in [('qt_calendar_prevmonth',True),('qt_calendar_nextmonth',False)]:
  button=calendar.findChild(QToolButton,name)
  if button:
   pixmap=QPixmap(20,20);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing);painter.setPen(QPen(QColor('#727983'),1.4))
   points=[QPointF(11,6),QPointF(7,10),QPointF(11,14)] if left else [QPointF(8,6),QPointF(12,10),QPointF(8,14)]
   painter.drawPolyline(QPolygonF(points));painter.end();button.setIcon(QIcon(pixmap));button.setIconSize(QSize(20,20));button.setFixedWidth(28);button.setToolTip('Tháng trước' if left else 'Tháng sau')

class CalendarDelegate(QStyledItemDelegate):
 """Paint the existing calendar model; date selection/ranges stay owned by Qt."""
 def paint(self,painter,option,index):
  text=str(index.data(Qt.DisplayRole) or '')
  if not text:return
  painter.save();painter.setRenderHint(QPainter.Antialiasing);painter.setClipRect(option.rect)
  painter.fillRect(option.rect,QColor('white'));font=QFont(option.font);font.setPixelSize(12)
  color=QColor('#253047')
  if index.row()==0:
   text=text[:2];color=QColor('#7b8390');font.setPixelSize(11)
  else:
   foreground=index.data(Qt.ForegroundRole)
   if foreground is not None:color=foreground.color() if hasattr(foreground,'color') else QColor(foreground)
   model_font=index.data(Qt.FontRole)
   if isinstance(model_font,QFont):font.setWeight(model_font.weight())
   blocked=bool(self.parent().parentWidget().property('recWeekdaysOnly')) and index.column()>=5
   if blocked:color=QColor('#b6bdc9')
   selected=bool(option.state & QStyle.State_Selected) and not blocked
   if selected:
    rect=QRectF(0,0,30,30);rect.moveCenter(QRectF(option.rect).center());painter.setPen(Qt.NoPen);painter.setBrush(QColor('#0866f5'));painter.drawRoundedRect(rect,7,7);color=QColor('white');font.setWeight(QFont.DemiBold)
   elif option.state & QStyle.State_MouseOver and not blocked:
    rect=QRectF(0,0,30,30);rect.moveCenter(QRectF(option.rect).center());painter.setPen(Qt.NoPen);painter.setBrush(QColor('#f0f5ff'));painter.drawRoundedRect(rect,7,7)
  painter.setFont(font);painter.setPen(color);painter.drawText(option.rect,Qt.AlignCenter,text);painter.restore()

class CalendarStyler(QObject):
 def eventFilter(self,obj,event):
  if event.type()==QEvent.Wheel and isinstance(obj,QWidget):
   current=obj
   while current is not None:
    if isinstance(current,(QDateEdit,QCalendarWidget)):
     event.accept();return True
    current=current.parentWidget()
  if event.type()==QEvent.Polish and isinstance(obj,(QDateEdit,QCalendarWidget)):
   ref=weakref.ref(obj)
   def apply():
    edit=ref()
    if edit is not None and isValid(edit):
     (style_date if isinstance(edit,QDateEdit) else style_calendar)(edit)
   QTimer.singleShot(0,apply)
  return False

def install(app):
 if getattr(app,'rec_calendar_styler',None) is not None:return
 app.rec_calendar_styler=CalendarStyler(app);app.installEventFilter(app.rec_calendar_styler)
 for widget in app.allWidgets():
  if isinstance(widget,QDateEdit):style_date(widget)
  elif isinstance(widget,QCalendarWidget):style_calendar(widget)
