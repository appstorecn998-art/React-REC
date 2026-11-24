"""Eight primary entries; existing route keys remain valid for contextual actions."""
from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton

GROUPS = {
    'Phiếu giao': [('Nhận ảnh', 'Tiếp nhận ảnh'), ('Kiểm phiếu', 'Kiểm tra phiếu'), ('Tra cứu nhiều ngày', 'Tra cứu phiếu'), ('Xuất phiếu', 'Xuất phiếu')],
    'Sổ nhận hàng': [('Tất cả phiếu', 'Sổ nhận hàng'), ('Chờ giao bù', 'Chờ giao bù'), ('Nguồn cần rà', 'Nguồn cần rà')],
    'Danh mục': [('Hàng hóa và kho', 'Tra cứu danh mục'), ('Nhà cung cấp', 'Nhà cung cấp')],
}
PRIMARY = ['Tổng quan', 'Phiếu giao', 'Thư viện PR', 'Sổ nhận hàng', 'Đối chiếu công nợ', 'Giá mua', 'Google Sheets', 'Danh mục', 'Cài đặt']


def install(w, callbacks):
    side = w.fluent_nav
    callbacks['Đối chiếu công nợ']=lambda:__import__('rec_debt_page').show(w)
    original = dict(callbacks)
    for key, icon in [('Phiếu giao', 'form'), ('Danh mục', 'search'), ('Đối chiếu công nợ','form')]:
        if key not in side.keys():
            item = side.add_item(key, icon=icon)
            item = side.item(key)
            if hasattr(side, 'compact_painter'): item.installEventFilter(side.compact_painter)
            item.setAccessibleName(key)
    parent = {route: group for group, routes in GROUPS.items() for _, route in routes}
    state = {'route': None}
    # One header outside the page stack: page-specific margins cannot move it.
    bar = QWidget(w.main_pages.parentWidget()); bar.setObjectName('groupedNavigation')
    bar.setFixedHeight(58)
    layout = QHBoxLayout(bar); layout.setContentsMargins(20, 8, 20, 14); layout.setSpacing(6)
    host_layout = w.main_pages.parentWidget().layout()
    host_layout.insertWidget(host_layout.indexOf(w.main_pages), bar)
    bar.hide()

    def refresh():
        page = w.main_pages.currentWidget()
        route = state['route']
        if page is getattr(w, 'receipt_page', None) and parent.get(route) != 'Phiếu giao':
            route = 'Kiểm tra phiếu'; state['route'] = route
        group = parent.get(route)
        bar.hide()
        if group and page:
            layout = bar.layout()
            while layout.count():
                item = layout.takeAt(0)
                if item.widget(): item.widget().hide(); item.widget().deleteLater()
            for label, target in GROUPS[group]:
                button = QPushButton(label); button.setFixedHeight(36); button.setCheckable(True); button.setChecked(target == route)
                button.setStyleSheet('QPushButton {min-height:36px;max-height:36px;padding:0 16px;border:0;border-radius:6px;background:#f1f3f8;color:#64748b;} QPushButton:checked {background:#eeebff;color:#5548c3;font-weight:600;}')
                button.clicked.connect(lambda checked=False, key=target: side.set_current(key))
                layout.addWidget(button)
            layout.addStretch(); bar.show()
        with QSignalBlocker(side):
            side.set_current(group or route) if (group or route) in PRIMARY else None

    def wrapped(route, callback):
        def run():
            before = w.main_pages.currentWidget()
            callback()
            # Existing callbacks retain validation and unsaved-edit guards.
            if w.main_pages.currentWidget() is not before or not w.busy:
                state['route'] = route; refresh()
        return run

    for key, callback in original.items(): callbacks[key] = wrapped(key, callback)
    callbacks['Phiếu giao'] = callbacks['Kiểm tra phiếu']
    callbacks['Danh mục'] = callbacks['Tra cứu danh mục']
    while side._body.count():
        item = side._body.takeAt(0)
        if item.widget(): item.widget().hide()
    side._section_labels = []
    for key in PRIMARY:
        item = side.item(key); side._body.addWidget(item); item.show()
    side._body.addStretch()
    side.set_collapsed(side.is_collapsed())
    # Async page transitions still keep the current contextual routes reachable.
    w.main_pages.currentChanged.connect(lambda _: QTimer.singleShot(0, refresh))
    w.grouped_navigation = dict(primary=PRIMARY, groups=GROUPS, refresh=refresh, bar=bar)

