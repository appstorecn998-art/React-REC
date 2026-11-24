"""REC Operations presentation adapter. Existing services own all data and writes."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QTableView,QDialogButtonBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView

STYLE="""
QMainWindow, QStackedWidget, QDialog {background:#ffffff;}
QWidget {font-family:'Segoe UI';color:#34415a;font-size:10pt;background:#ffffff;}
QLabel {background:transparent;}
QLabel#title {font-size:20pt;font-weight:600;color:#25314b;}
QLabel#section {font-weight:600;color:#43506a;}
QLabel#muted {color:#8993a6;}
QFrame[sidebar="true"] {background:#fafafd;border:0;}
QPushButton {background:#ffffff;color:#56647b;border:1px solid #e0e4ee;border-radius:7px;padding:7px 12px;}
QPushButton:hover {background:#f6f3ff;border-color:#bab2eb;}
QPushButton:focus {border:2px solid #9588e6;}
QPushButton:disabled {color:#a3a9b6;background:#f7f8fa;border-color:#edf0f4;}
QPushButton#primary, QPushButton[variant="primary"] {background:#6054d8;border-color:#6054d8;color:white;}
QPushButton#danger {background:#b83d53;color:white;border-color:#b83d53;}
QPushButton[sidebarItem="true"] {background:transparent;border:0;text-align:left;color:#788298;}
QPushButton[sidebarItem="true"]:checked {background:#efedff;color:#5548c3;}
QLineEdit, QComboBox, QDateEdit, QPlainTextEdit {background:white;border:1px solid #dfe4ed;border-radius:6px;padding:7px;color:#4e5d76;}
QLineEdit:focus, QComboBox:focus {border-color:#9588e6;}
QLineEdit:read-only {background:#f8f9fc;color:#8a93a5;}
QTableView {background:white;border:0;gridline-color:#eef0f5;selection-background-color:#efedff;selection-color:#5147ab;}
QTableView::item {padding:8px;border-bottom:1px solid #edf0f5;}
QTableView::item:selected {background:#efedff;color:#5147ab;}
QHeaderView::section {background:#fcfcfe;border:0;border-bottom:1px solid #edf0f5;padding:10px;color:#8993a5;font-weight:400;}
QListWidget {background:white;border:0;}
QListWidget::item:selected {background:#efedff;color:#5147ab;}
QTabWidget::pane {background:white;border:0;border-top:1px solid #eceef5;}
QTabBar::tab {background:white;color:#8a94a8;border:0;padding:10px 16px;}
QTabBar::tab:selected {color:#5a4cc6;border-bottom:2px solid #6054d8;}
QProgressBar {background:#eeecf8;border:0;border-radius:3px;}
QProgressBar::chunk {background:#6054d8;border-radius:3px;}
QFrame#opsBrand {background:white;border-bottom:1px solid #edf0f5;}
QFrame#taskDisplay {background:#f8f6ff;border:1px solid #e6e0fb;border-radius:8px;}
QStatusBar {background:#fcfcfe;color:#8a93a5;border-top:1px solid #edf0f5;}
QMenu {background:white;border:1px solid #e4e7ef;color:#53617a;}
QMenu::item:selected {background:#efedff;color:#5548c3;}
QDialogButtonBox {background:transparent;}
"""

def install(w,page_layout,receipt_layout):
    # Move existing widgets, not their signals/models: no parallel copy of state.
    old=w.global_action_header
    row=old.layout();actions=row.takeAt(0).widget();panel=row.takeAt(0).widget()
    actions.setParent(w.receipt_page);actions.setFixedHeight(146)
    actions.widget().setFixedHeight(124)
    for control in [w.date_edit,w.receipt_picker,w.previous,w.next,w.reload_button,w.add_button,w.read_button,w.merge_button,w.bulk_pr_button,w.publish_button]:
        control.setFixedHeight(34)
        control.setStyleSheet(control.styleSheet()+'\nQPushButton {min-height:0px;max-height:32px;padding:3px 10px;}')
    receipt_layout.insertWidget(0,actions);w.ops_receipt_actions=actions
    page_layout.removeWidget(old);old.hide()
    for label in actions.findChildren(QLabel):
        if label.text()=='Ngày':label.hide()
        if label.text()=='REC · Nhận hàng và báo cáo':label.setText('Kiểm tra phiếu');label.setStyleSheet('font-size:20px;font-weight:600;color:#25314b;')
    brand=QWidget();brand.setObjectName('opsBrand');top=QHBoxLayout(brand);top.setContentsMargins(24,12,24,12)
    # The native titlebar icon carries the application identity.
    for text,key in [('Công việc','Kiểm tra phiếu'),('Báo cáo','Sổ nhận hàng'),('Cài đặt','Cài đặt')]:
        b=QPushButton(text);b.setFlat(True);b.clicked.connect(lambda checked=False,k=key:w.fluent_nav.set_current(k));top.addWidget(b)
    top.addStretch();w.ops_profile=QLabel('Hồ sơ REC');top.addWidget(w.ops_profile)
    page_layout.insertWidget(0,brand);w.global_action_header=brand
    # Keep operation progress accessible across pages, expanded during actual work.
    panel.setParent(w.notice_overlay_parent);panel.setMinimumWidth(0);panel.setMaximumWidth(16777215)
    panel.setStyleSheet('');panel.hide();page_layout.addWidget(panel)
    w.task_display.title.setStyleSheet('font-weight:600;color:#5a4cc6;')
    toggle=QPushButton('Tác vụ / nhật ký');toggle.setCheckable(True);toggle.toggled.connect(panel.setVisible)
    w.statusBar().addPermanentWidget(toggle);w.ops_task_toggle=toggle
    begin=w.task_display.begin
    def start(*args,**kwargs):
        # Progress is shown by the operation banner; keep the workspace geometry stable.
        begin(*args,**kwargs)
    w.task_display.begin=start
    notice=w.show_top_notice
    def show_notice(title,message,variant='info'):
        notice(title,message,variant)
        if variant in ('warning','error'):toggle.setChecked(True)
    w.show_top_notice=show_notice
    # New shell retains the real leave-PR guard before a navigation changes pages.
    from rec_fluent_ui import show_directory,show_settings,show_appearance
    callbacks={'Kiểm tra phiếu':lambda:w.main_pages.setCurrentWidget(w.receipt_page),
               'Tra cứu danh mục':lambda:show_directory(w),'Sổ nhận hàng':w.show_shortage_ledger,
               'Google Sheets':lambda:__import__('rec_sheets_page').show_page(w),
               'Cài đặt':lambda:show_settings(w),'Giao diện':lambda:show_appearance(w)}
    w.fluent_nav.current_changed.disconnect()
    state={'key':'Kiểm tra phiếu'}
    def navigate(key):
        if key not in callbacks:return
        if key!=state['key'] and w.main_pages.currentWidget() is w.receipt_page and not w._leave_pr():
            side=w.fluent_nav;side.blockSignals(True)
            try:side.set_current(state['key'])
            finally:side.blockSignals(False)
            return
        callbacks[key]();state['key']=key
    w.fluent_nav.current_changed.connect(navigate)
    w.ops_navigate=navigate
    w.setStyleSheet(w.styleSheet()+'\n'+STYLE)
    # This property is used only by the stylesheet, independent of button text.
    for key in w.fluent_nav.keys():
        item=w.fluent_nav.item(key);item.setProperty('sidebarItem',True)
        item.setStyleSheet('QPushButton {background:transparent;border:0;border-radius:8px;color:#788298;text-align:left;padding:12px;} QPushButton:checked {background:#efedff;color:#5548c3;font-weight:600;} QPushButton:focus {border:1px solid #9588e6;}')
    for table in w.findChildren(QTableView):table.setShowGrid(False)
    from pathlib import Path
    from PySide6.QtGui import QIcon
    w.setWindowIcon(QIcon(str(Path(__file__).with_name('rec-package-check.ico'))))
    w.setWindowTitle('REC – Quản lý nhận hàng')
    install_aligned_pages(w,callbacks,state,page_layout,receipt_layout)


def install_aligned_pages(w,callbacks,state,page_layout,receipt_layout):
    """Native layout matching the approved Operations reference, using live models."""
    from PySide6.QtCore import QTimer
    from fluent_blue.icons import icon as make_icon
    side=w.fluent_nav
    # Reorder the real navigation items, retaining the live key/signal contract.
    while side._body.count():
        item=side._body.takeAt(0)
        if item.widget():item.widget().hide()
    side._section_labels=[]
    side.add_item('Tổng quan',icon='home');side.add_item('Thư viện PR',icon='file')
    side.add_item('Xuất phiếu',icon='download')
    groups=[('CÔNG VIỆC',['Tổng quan','Kiểm tra phiếu','Thư viện PR']),('THEO DÕI',['Sổ nhận hàng','Google Sheets','Xuất phiếu']),('QUẢN LÝ',['Tra cứu danh mục','Cài đặt','Giao diện'])]
    for group,keys in groups:
        label=QLabel(group);label.setStyleSheet('color:#98a1b1;font-size:9px;padding:18px 12px 6px;background:#fafafd;');side._section_labels.append(label);side._body.addWidget(label)
        for key in keys:
            item=side.item(key);side._body.addWidget(item);item.show()
            item.setStyleSheet('QPushButton {background:#fafafd;border:0;border-radius:8px;color:#778399;text-align:left;padding:12px;} QPushButton:checked {background:#eeebff;color:#5548c3;font-weight:600;} QPushButton:focus {border:1px solid #9588e6;}')
    side._body.addStretch()
    side.setStyleSheet('QFrame {background:#fafafd;border:0;}');side.setFixedWidth(224)
    w.fluent_host.sync_side()
    # Overview is generated from the current report, never invented ledger totals.
    home=QWidget();home.setObjectName('operationsOverview');lv=QVBoxLayout(home);lv.setContentsMargins(34,28,34,28);lv.setSpacing(20)
    crumb=QLabel('Công việc / Tổng quan');crumb.setStyleSheet('font-size:11px;color:#98a1b1;');lv.addWidget(crumb)
    head=QHBoxLayout();words=QVBoxLayout();title=QLabel('Tổng quan công việc');title.setStyleSheet('font-size:26px;font-weight:600;color:#25314b;');words.addWidget(title)
    subtitle=QLabel('Những việc cần bạn xử lý trong ngày đang chọn.');subtitle.setStyleSheet('color:#919bad;font-size:12px;');words.addWidget(subtitle);head.addLayout(words,1)
    refresh=QPushButton('Làm mới');add=QPushButton('Thêm ảnh');add.setObjectName('primary');head.addWidget(refresh);head.addWidget(add);lv.addLayout(head)
    stats=QHBoxLayout();numbers=[]
    for text in ['Phiếu trong ngày','Đã kiểm tra','Chưa kiểm tra','Dòng hàng']:
        group=QVBoxLayout();n=QLabel('—');n.setStyleSheet('font-size:27px;color:#25314b;font-weight:600;');label=QLabel(text);label.setStyleSheet('color:#929dae;font-size:11px;');group.addWidget(n);group.addWidget(label);stats.addLayout(group);numbers.append(n)
    stats.addStretch();lv.addLayout(stats)
    notice=QWidget();notice.setStyleSheet('QWidget {background:#f7f5ff;border:1px solid #e8e2ff;border-radius:10px;} QLabel {border:0;color:#5e51b7;background:transparent;}')
    nl=QHBoxLayout(notice);nl.setContentsMargins(18,16,18,16);nl.addWidget(QLabel('Rà soát phiếu trước khi ghi sổ'),1);review=QPushButton('Duyệt ghi sổ');review.setObjectName('primary');nl.addWidget(review);lv.addWidget(notice)
    entries=QTableWidget(0,4);entries.setObjectName('overviewReceipts');entries.setHorizontalHeaderLabels(['PHIẾU / NHÀ CUNG CẤP','SỐ DÒNG','KIỂM TRA','THAO TÁC'])
    entries.verticalHeader().hide();entries.setShowGrid(False);entries.setEditTriggers(QAbstractItemView.NoEditTriggers);entries.setSelectionBehavior(QAbstractItemView.SelectRows);entries.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
    entries.setColumnWidth(1,100);entries.setColumnWidth(2,145);entries.setColumnWidth(3,105);lv.addWidget(entries,1)
    truth=QLabel('Đã kiểm tra không đồng nghĩa đã ghi sổ. Xem trạng thái ghi sổ tại Sổ nhận hàng.');truth.setWordWrap(True);truth.setStyleSheet('color:#929bad;font-size:11px;');lv.addWidget(truth)
    def receipt():side.set_current('Kiểm tra phiếu')
    def open_item(name):
        if not w._leave_pr():return
        w.select_sheet(name);receipt()
    def fill():
        sheets=list(w.data_by_sheet.items());checked=sum(w.approved(name) for name,_ in sheets)
        for label,value in zip(numbers,[len(sheets),checked,len(sheets)-checked,sum(len(rows) for _,rows in sheets)]):label.setText(str(value))
        entries.setRowCount(len(sheets))
        for i,(name,rows) in enumerate(sheets):
            supplier=next((str(v.get('Nhà cung cấp')) for _,v in rows if v.get('Nhà cung cấp')),'NCC chưa rõ')
            for j,text in enumerate([supplier+' · '+name,str(len(rows)),'Đã kiểm tra' if w.approved(name) else 'Cần kiểm tra']):entries.setItem(i,j,QTableWidgetItem(text))
            b=QPushButton('Mở phiếu →');b.clicked.connect(lambda checked=False,n=name:open_item(n));entries.setCellWidget(i,3,b);entries.setRowHeight(i,52)
        entries.setProperty('sheetNames',[name for name,_ in sheets])
    def show_home():fill();w.main_pages.setCurrentWidget(home)
    w.main_pages.addWidget(home);w.ops_overview=home;w.ops_refresh_overview=fill
    callbacks['Tổng quan']=show_home
    callbacks['Thư viện PR']=lambda:w.choose_saved_pr()
    callbacks['Xuất phiếu']=lambda:w.publish()
    refresh.clicked.connect(fill);add.clicked.connect(lambda:(receipt(),w.add_images()))
    review.setStyleSheet('QPushButton {background:#6054d8;color:white;border:1px solid #6054d8;border-radius:7px;padding:8px 13px;} QPushButton:disabled {background:#e8e4fa;color:#9e96bf;}')
    review.clicked.connect(w.refresh_all_pr)
    entries.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    # Reuse the date/receipt selectors but separate page identity from commands.
    control=w.ops_receipt_actions;left=control.widget();left.layout().setSpacing(10)
    left.layout().setContentsMargins(0,0,0,0)
    for label in left.findChildren(QLabel):
        if label.text()=='Kiểm tra phiếu':label.hide()
    w.receipt_picker.setText('Chọn nhà cung cấp / phiếu')
    w.image_title.hide();w.review_label.hide()
    w.image_header.setAlignment(Qt.AlignLeft)
    # Keep the selected line crop available, below the table rather than an empty
    # fixed-height band above every table header.
    data_layout=w.region_view.parentWidget().layout()
    data_layout.removeWidget(w.region_view);data_layout.insertWidget(max(0,data_layout.count()-1),w.region_view)
    w.approve_button.setText('Đánh dấu đã kiểm');w.approve_button.setToolTip('Xác nhận hoặc bỏ xác nhận đã rà phiếu. Không tự ghi sổ.')
    w.receipt_page.layout().setContentsMargins(10,10,10,10)
    heading=QWidget();hl=QVBoxLayout(heading);hl.setContentsMargins(0,0,0,0);hl.setSpacing(8)
    hl.addWidget(QLabel('Kiểm tra phiếu',objectName='opsPageTitle'))
    receipt_layout.insertWidget(0,heading)
    w.setStyleSheet(w.styleSheet()+'''\nQLabel#opsCrumb {font-size:11px;color:#98a1b1;} QLabel#opsPageTitle {font-size:24px;color:#25314b;font-weight:600;} QLabel#opsPageHint {font-size:12px;color:#909bad;} QFrame#panel {border:0;border-radius:0;background:white;} QScrollBar:horizontal {height:9px;background:#f7f7fc;} QScrollBar::handle:horizontal {background:#d2cce9;min-width:48px;border-radius:4px;}''')
    w.ops_profile.setText('Ngày '+w.day.strftime('%d/%m/%Y'))
    install_receipt_workspace(w,receipt_layout,heading)
    from rec_workspace_v2 import install as install_workspace
    install_workspace(w,callbacks,page_layout)


def install_receipt_workspace(w,receipt_layout,heading):
    """Use the approved list/detail workspace instead of the old two-panel image UI."""
    from PySide6.QtWidgets import QDialog,QScrollArea,QFrame,QSizePolicy
    # The source viewer becomes an independent helper. It retains the live preview,
    # page arrows, magnifier and image processing switches, not a copied image.
    image_panel=w.work_split.widget(0)
    viewer=QDialog(w);viewer.setObjectName('receiptSourceViewer');viewer.setWindowTitle('Ảnh nguồn · Phiếu đang chọn');viewer.resize(740,860)
    viewer.setModal(False);vl=QVBoxLayout(viewer);vl.setContentsMargins(16,16,16,16)
    image_panel.setParent(viewer);vl.addWidget(image_panel)
    close=QPushButton('Đóng ảnh');close.clicked.connect(viewer.close);vl.addWidget(close)
    w.ops_source_dialog=viewer
    # Bring the authoritative receipt list out of the old picker popup.
    w.receipt_menu.layout().removeWidget(w.receipt_panel)
    w.receipt_panel.setParent(w.work_split);w.receipt_panel.setMinimumWidth(200);w.receipt_panel.setMaximumWidth(300)
    w.receipt_panel.setMinimumHeight(0);w.work_split.insertWidget(0,w.receipt_panel);w.receipt_panel.show()
    w.image_list.hide();w.work_split.setStretchFactor(0,0);w.work_split.setStretchFactor(1,1);w.work_split.setSizes([240,900])
    w.receipt_list.itemClicked.disconnect()
    # Selection/currentRowChanged still uses the original guarded select_sheet.
    # Disable only the obsolete popup's close-on-click callback above.
    w.receipt_picker.hide();w.previous.hide();w.next.hide()
    w.receipt_menu.hide()
    # Rebuild the page's command and filter rows; no stacked old toolbar remains.
    old=w.ops_receipt_actions;receipt_layout.removeWidget(old);old.hide()
    title_layout=heading.layout();title=heading.findChild(QLabel,'opsPageTitle');title_layout.removeWidget(title)
    title_row=QHBoxLayout();title_row.addWidget(title,1)
    for control in [w.add_button,w.read_button,w.bulk_pr_button]:
        title_row.addWidget(control);control.show()
    title_layout.insertLayout(1,title_row)
    filters=QWidget();filters.setObjectName('receiptWorkspaceFilters');fl=QHBoxLayout(filters);fl.setContentsMargins(0,0,0,0);fl.setSpacing(10)
    fl.addWidget(w.date_edit);fl.addWidget(w.reload_button)
    source=QPushButton('Xem ảnh nguồn');source.setObjectName('showReceiptSource');source.clicked.connect(viewer.show);fl.addWidget(source)
    fl.addWidget(w.merge_button);w.merge_button.show();fl.addStretch()
    fl.addWidget(w.show_all);w.show_all.show()
    w.table.model().compact=['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Thực nhận','Đơn giá','Thành tiền']
    w.show_all.setChecked(False)
    fl.addWidget(w.publish_button);w.publish_button.show()
    filter_scroll=QScrollArea();filter_scroll.setWidgetResizable(True);filter_scroll.setFrameShape(QFrame.NoFrame)
    filter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    filter_scroll.setWidget(filters);filter_scroll.setFixedHeight(62)
    receipt_layout.insertWidget(1,filter_scroll);w.ops_receipt_actions=filter_scroll
    # Keep edit and lookup actions visible below the currently selected receipt.
    data_layout=w.region_view.parentWidget().layout()
    row=QHBoxLayout()
    for control in [w.table_edit_button,w.table_lookup_button,w.bulk_department]:control.setParent(w);row.addWidget(control);control.show()
    row.addStretch();data_layout.addLayout(row)
    w.approve_button.hide()  # Source helper has no independent accounting action.
    review=QPushButton('Đánh dấu đã kiểm');review.setObjectName('receiptReviewAction');review.clicked.connect(w.approve)
    fl.insertWidget(2,review)
    remove=QPushButton('Xóa ảnh / phiếu');fl.insertWidget(3,remove)
    remove.clicked.connect(lambda:__import__('rec_remove_receipt').show(w))
    def sync_review(*_):
        review.setText('Bỏ xác nhận kiểm tra' if w.approved(w.current_sheet) else 'Đánh dấu đã kiểm')
        review.setEnabled(not w.busy and bool(w.current_sheet))
    w.receipt_list.currentRowChanged.connect(sync_review)
    busy=w.set_busy
    def set_busy(*args,**kwargs):busy(*args,**kwargs);sync_review()
    w.set_busy=set_busy
    review.clicked.connect(sync_review);sync_review()
    w.ops_review_button=review
    w.setStyleSheet(w.styleSheet()+'''\nQWidget#receiptWorkspaceFilters {border-bottom:1px solid #edf0f5;padding-bottom:10px;} QFrame#receiptCard {border:0;background:#fafafd;border-radius:8px;} QFrame#receiptCard[selected="true"] {background:#efedff;border:0;} QTabWidget::pane {border:0;}''')
