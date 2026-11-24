"""Fluent Blue presentation adapter; retains all REC services and signals."""
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtWidgets import QFrame, QStackedWidget, QScrollArea, QSizePolicy, QHBoxLayout, QWidget, QLabel, QDialog, QVBoxLayout, QApplication, QAbstractItemView, QDialogButtonBox
from fluent_blue import ThemeManager, Text, Button, DatePicker
from fluent_blue.icons import icon as make_icon
from PySide6.QtCore import QSize
from fluent_blue.core.configuration import config
from rec_navigation import HoverSidebar, OverlayHost

def install_interface(w):
    config.animations=False
    ThemeManager.set_theme('light')
    # The original live lists remain authoritative; no duplicated receipt model.
    # A normal popup frame keeps live receipt cards fully interactive.
    popup=QFrame(w,Qt.Popup)
    popup_layout=QVBoxLayout(popup);popup_layout.setContentsMargins(0,0,0,0)
    panel=w.receipt_panel;panel.setMinimumSize(400,400);panel.setMaximumWidth(520)
    popup_layout.addWidget(panel);panel.show()
    picker=Button('Chọn phiếu trong ngày');picker.setFixedWidth(210)
    def open_picker():
        if w.busy or not w.receipt_list.count():return
        from PySide6.QtCore import QTimer
        point=picker.mapToGlobal(picker.rect().bottomLeft())
        screen=QApplication.screenAt(point) or w.screen();bounds=screen.availableGeometry()
        popup.ensurePolished();popup.layout().activate()
        popup.resize(min(480,bounds.width()-24),min(560,bounds.height()-80))
        popup.show()
        # Position the actual popup size, after Qt has applied layout constraints.
        x=max(bounds.left()+8,min(point.x(),bounds.right()-popup.width()-8))
        below=point.y()+5;above=picker.mapToGlobal(picker.rect().topLeft()).y()-popup.height()-5
        y=below if below+popup.height()<=bounds.bottom()-8 else above
        popup.move(x,max(bounds.top()+8,min(y,bounds.bottom()-popup.height()-8)))
        popup.raise_();w.receipt_list.setFocus()
        current=w.receipt_list.currentItem()
        if current:QTimer.singleShot(0,lambda:w.receipt_list.scrollToItem(current,QAbstractItemView.PositionAtCenter) if popup.isVisible() else None)
    picker.clicked.connect(open_picker)
    w.open_receipt_picker=open_picker
    old_date=w.date_edit
    w.date_edit=RECDatePicker(date=w.day,display_format='%d/%m/%Y',clearable=False)
    w.date_edit.dateChanged.connect(lambda _:w.open_day())
    old_date.hide();old_date.deleteLater()
    w.date_edit.setFixedWidth(150)
    bar=w.receipt_toolbar
    while bar.count():
        item=bar.takeAt(0)
        if item.widget():item.widget().hide()
    bar.setSpacing(8);bar.setContentsMargins(0,0,0,0)
    for widget in [QLabel('Ngày'),w.date_edit,QLabel('Phiếu trong ngày'),w.previous,picker,w.next,
                   w.add_button,w.read_button,w.reload_button,w.merge_button]:
        bar.addWidget(widget);widget.show()
    for button,icon,label in [(w.previous,'chevron-left','Phiếu trước (Alt+←)'),(w.next,'chevron-right','Phiếu sau (Alt+→)')]:
        button.setText('');button.setIcon(make_icon(icon));button.setFixedWidth(34)
        button.setToolTip(label);button.setAccessibleName(label)
    def sync_receipt_arrows(*_):
        from shiboken6 import isValid
        if not all(isValid(widget) for widget in [w.receipt_list,w.previous,w.next]):return
        index=w.receipt_list.currentRow();count=w.receipt_list.count()
        w.previous.setEnabled(not w.busy and index>0)
        w.next.setEnabled(not w.busy and count>0 and index<count-1)
    w.sync_receipt_arrows=sync_receipt_arrows
    w.receipt_list.currentRowChanged.connect(sync_receipt_arrows)
    for signal in [w.receipt_list.model().rowsInserted,w.receipt_list.model().rowsRemoved,w.receipt_list.model().modelReset]:
        signal.connect(sync_receipt_arrows)
    original_busy=w.set_busy
    def busy_with_arrows(*args,**kwargs):
        original_busy(*args,**kwargs);sync_receipt_arrows()
    w.set_busy=busy_with_arrows
    def navigate_receipt(delta):
        if w.busy:return
        original_row=w.receipt_list.currentRow();original_sheet=w.current_sheet
        w.move_receipt(delta)
        if w.current_sheet==original_sheet and w.receipt_list.currentRow()!=original_row:
            w.receipt_list.blockSignals(True);w.receipt_list.setCurrentRow(original_row);w.receipt_list.blockSignals(False)
            selected(original_row)
        sync_receipt_arrows()
    w.previous.clicked.disconnect();w.next.clicked.disconnect()
    w.previous.clicked.connect(lambda:navigate_receipt(-1));w.next.clicked.connect(lambda:navigate_receipt(1))
    sync_receipt_arrows()
    for button in [w.reload_button]:
        button.setToolTip(button.text());button.setText('');button.setFixedWidth(36)
    w.merge_button.setText('Ghép trang phiếu');w.merge_button.setToolTip('Chọn các ảnh thuộc cùng một phiếu để ghép')
    w.log_button.hide()
    w.root_button.hide();w.inbox_folder.hide();w.inbox_toggle.hide()
    w.root_button.setText('Chọn nơi lưu');w.root_button.setToolTip('Chọn thư mục kế toán để lưu phiếu giao hàng và báo cáo')
    w.inbox_folder.setText('Chọn nguồn ảnh');w.inbox_folder.setToolTip('Chọn thư mục được theo dõi để tự nhận và đọc ảnh')
    bar.addStretch();bar.addWidget(w.publish_button);w.publish_button.show()
    w.receipt_picker=picker;w.receipt_menu=popup
    def selected(index):
        item=w.receipt_list.item(index)
        name=item.data(Qt.UserRole) if item else ''
        rows=w.data_by_sheet.get(name,[])
        supplier=next((str(v.get('Nhà cung cấp')) for _,v in rows if v.get('Nhà cung cấp')), '')
        picker.setText(short_supplier(supplier,w.root) if supplier else (name or 'Chọn phiếu trong ngày'))
        picker.setToolTip(f'{supplier}\n{name}')
    w.receipt_list.currentRowChanged.connect(selected)
    # Only an actual user choice closes the popup, never loading/filtering lists.
    w.receipt_list.itemClicked.connect(lambda _:popup.hide())
    w.image_list.itemClicked.connect(lambda _:popup.hide())
    w.summary.hide()
    for label in w.findChildren(QLabel):
        if label.text().startswith('Rà phiếu, đối chiếu'):label.hide()
    w.findChild(QFrame,'actionPanel').hide()
    w.findChild(QWidget,'inboxHost').hide()
    content_layout=w.centralWidget().layout()
    content_layout.removeItem(bar)
    bar_host=QWidget();bar_host.setLayout(bar)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(bar_host);scroll.setFixedHeight(54)
    content_layout.insertWidget(1,scroll)
    w.toolbar_scroll=scroll
    alert_host=QWidget();w.alert_layout=QVBoxLayout(alert_host)
    w.alert_layout.setContentsMargins(0,0,0,0)
    content_layout.addWidget(alert_host)
    w.alert_host=alert_host;alert_host.hide()
    content=w.takeCentralWidget()
    w.main_pages=QStackedWidget();w.main_pages.addWidget(content)
    w.receipt_page=content;w.directory_page=None
    side=HoverSidebar();side.add_section('REC SOFTWARE')
    callbacks={'Kiểm tra phiếu':lambda:w.main_pages.setCurrentWidget(w.receipt_page),'Tra cứu danh mục':lambda:show_directory(w),
               'Sổ nhận hàng':w.show_shortage_ledger,'Google Sheets':lambda:__import__('rec_sheets_page').show_page(w),'Cài đặt':lambda:show_settings(w),'Giao diện':lambda:show_appearance(w)}
    for key,icon in [('Kiểm tra phiếu','form'),('Tra cứu danh mục','search'),('Sổ nhận hàng','table'),('Google Sheets','cloud'),('Cài đặt','folder'),('Giao diện','palette')]:
        side.add_item(key,icon=icon)
    def navigate(key):
        callbacks[key]()
        if key=='Giao diện':
            side.set_current('Tra cứu danh mục' if w.directory_page is not None and w.main_pages.currentWidget() is w.directory_page else 'Kiểm tra phiếu')
    side.set_current('Kiểm tra phiếu')
    side.current_changed.connect(navigate)
    side.set_collapsed(False)
    side.pin.setChecked(True)
    # Notices belong to the whole app, including Sheets and Settings pages.
    content_layout.removeWidget(alert_host)
    page_area=QWidget();page_layout=QVBoxLayout(page_area)
    page_layout.setContentsMargins(0,0,0,0);page_layout.setSpacing(0)
    page_layout.addWidget(w.main_pages,1)
    alert_host.setParent(page_area)
    w.notice_overlay_parent=page_area
    w.alert_layout.setContentsMargins(22,0,22,8)
    host=OverlayHost(page_area,side);w.setCentralWidget(host)
    w.fluent_nav=side;w.fluent_host=host
    w.shortage_button.hide()
    # Neutral Fluent surfaces with the same business widgets/delegates underneath.
    style=w.styleSheet().replace('#2563d9','#0f6cfe').replace('#1d4ed8','#005bd6')
    style=style.replace('border-radius: 14px','border-radius: 8px').replace('border-radius: 9px','border-radius: 5px')
    style=style.replace('font-size: 22pt','font-size: 18pt').replace('font-size: 18pt','font-size: 16pt')
    style += """
    QWidget { color: #1a1a1a; font-family: 'Segoe UI'; }
    QLabel#title, QLabel#section { color: #1a1a1a; }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #0f6cfe; }
    QLineEdit:read-only, QLineEdit:disabled { background: #f0f0f0; color: #707070; }
    QFrame#actionPanel { border: 0; background: transparent; }
    QToolButton { padding: 7px 10px; }
    """
    for button in w.findChildren(Button):
        button.setObjectName('');button.setStyleSheet('')
    w.setStyleSheet(style + ThemeManager.stylesheet() + '\nQPushButton#titleDate {font-size: 10pt; font-weight: 400; background: white; color: #1a1a1a; border: 1px solid #d1d1d1;}')
    for label in w.findChildren(QLabel):
        if label.objectName()=='total':
            label.setStyleSheet('font-size: 10pt; font-weight: 400; color: #1a1a1a;')
    w.setWindowTitle('REC Software · Kiểm tra phiếu và báo cáo ngày')
    from rec_task_panel import install
    install(w,page_layout,content_layout,scroll,bar)
    from rec_operations_ui import install as install_operations
    install_operations(w,page_layout,content_layout)

def show_appearance(w):
    d=QDialog(w);d.setWindowTitle('Giao diện REC');v=QVBoxLayout(d)
    v.addWidget(Text('Fluent Blue',style='heading-3'))
    v.addWidget(Text('Điều hướng mở phủ lên nội dung. Rê chuột để mở; bấm nút ghim để giữ mở.',wrap=True))
    d.resize(480,180);d.exec()




def short_supplier(value,root=None):
    if root is not None:
        from receiving_preferences import nickname
        custom=nickname(root,value)
        if custom:return custom
    import re
    value=re.sub(r'\s+',' ',str(value)).strip()
    for token,label in [('THẾ VINH','Thế Vinh'),('HUYỀN NAM','Huyền Nam'),('NIPPONHAM','Nipponham'),('HOÀNG KHA','Hoàng Kha'),('PHÁP VIỆT','Pháp Việt'),('FOOD SOURCE','Food Source'),('TRUNG HẬU','Trung Hậu')]:
        if token in value.upper():return label
    prefix=r'^(?:(?:CÔNG TY|CTY|TNHH|TRÁCH NHIỆM HỮU HẠN|CỔ PHẦN|CP|SX|TM|DV|SẢN XUẤT|THƯƠNG MẠI|DỊCH VỤ|VĂN PHÒNG PHẨM)\s+)+'
    value=re.sub(prefix,'',value,flags=re.I).strip()
    return value.title() or 'NCC chưa rõ'

class RECDatePicker(DatePicker):
    """Fluent calendar preserving REC's QDate-based service contract."""
    dateChanged=Signal(object)
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.date_changed.connect(self._emit_qdate)
    def set_date(self,value):
        if value is not None and value.weekday()>4:return
        super().set_date(value)
    def open_popup(self):
        super().open_popup()
        self.calendar.is_enabled_date=lambda day:day.weekday()<5 and (self._minimum is None or day>=self._minimum) and (self._maximum is None or day<=self._maximum)
        self.calendar.grid.update()
    def _chosen(self,day):
        if day.weekday()>4:return
        super()._chosen(day)
    def _emit_qdate(self,value):
        if value:self.dateChanged.emit(QDate(value.year,value.month,value.day))
    def date(self):
        value=super().date()
        return QDate(value.year,value.month,value.day) if value else QDate()
    def setDate(self,value):
        from datetime import date
        self.set_date(date(value.year(),value.month(),value.day()) if isinstance(value,QDate) else value)


def show_directory(w):
    from rec_directory import DirectoryPage
    if w.directory_page is None:
        w.directory_page=DirectoryPage(w)
        w.main_pages.addWidget(w.directory_page)
    w.main_pages.setCurrentWidget(w.directory_page)


class FluentButtonBox(QDialogButtonBox):
    """Fluent buttons retaining the dialog's existing Save/Cancel lookup contract."""
    def __init__(self, standards, parent=None):
        super().__init__(parent);self._standard_map={}
        for key,label,role,variant in [(QDialogButtonBox.Save,'Lưu',QDialogButtonBox.AcceptRole,'primary'),(QDialogButtonBox.Cancel,'Hủy',QDialogButtonBox.RejectRole,'secondary')]:
            if standards & key:
                button=Button(label,variant=variant);super().addButton(button,role);self._standard_map[key]=button
    def button(self,standard):
        return self._standard_map.get(standard) or super().button(standard)
    def addButton(self,button,role):
        if isinstance(button,str):button=Button(button)
        super().addButton(button,role)
        return button


def show_settings(w):
    from rec_settings_design import show
    return show(w)
