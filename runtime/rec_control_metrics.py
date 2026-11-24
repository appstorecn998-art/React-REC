"""Consistent receipt controls in logical pixels, independent of old theme minima."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton,QToolButton,QLineEdit,QSizePolicy

HEIGHT=36
GAP=8

def normalize(control,icon_only=False):
    # A fixed widget height alone does not cancel min-height/padding specified
    # by the inherited Fluent theme. Reset those on the actual control too.
    control.setStyleSheet(control.styleSheet()+'''
QPushButton,QToolButton,QLineEdit {min-height:34px;max-height:34px;padding:0px 10px;font-size:12px;border-radius:7px;}
''')
    control.setFixedHeight(HEIGHT)
    control.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    if icon_only:control.setFixedWidth(HEIGHT)
    elif isinstance(control,(QPushButton,QToolButton)):
        text='Phiếu giao hàng' if control.objectName()=='receiptReferenceToggle' else control.text()
        width=control.fontMetrics().horizontalAdvance(text)+28
        if not control.icon().isNull():width+=22
        if isinstance(control,QToolButton):width+=14
        control.setFixedWidth(max(54,width))

def install(w):
    filters=w.ops_receipt_actions.widget().layout()
    filters.setSpacing(GAP);filters.setContentsMargins(0,6,0,6)
    controls=[w.receipt_search,w.date_edit,w.previous,w.receipt_picker,w.next,w.reload_button,w.ops_review_button]
    for control in controls:
        normalize(control,control in (w.reload_button,w.previous,w.next))
        filters.setAlignment(control,Qt.AlignVCenter)
    w.ops_review_button.setFixedWidth(142)
    w.date_edit.setFixedWidth(150)
    w.ops_receipt_actions.setFixedHeight(52)
    w.receipt_action_row.setSpacing(GAP);w.receipt_action_row.addStretch()
    exclude=set(controls)
    for control in w.receipt_page.findChildren(QPushButton)+w.receipt_page.findChildren(QToolButton):
        # Preserve page arrows floating over the image: their hit area is
        # deliberately taller, outside the toolbar geometry contract.
        if control in exclude or control.parent() is w.preview:continue
        if control.text() in ('‹','›'):continue
        normalize(control,control is w.next_number or control.objectName()=='copyReceiptImage')
    # Preserve semantic foreground after approve/refresh updates the review label.
    sync=w.receipt_status_sync
    def review_metrics():sync();normalize(w.ops_review_button);w.ops_review_button.setFixedWidth(142)
    w.receipt_status_sync=review_metrics
    w.receipt_list.currentRowChanged.connect(lambda *_:review_metrics())
    w.ops_review_button.clicked.connect(review_metrics)
    refresh=w.refresh_table
    def refreshed(*a,**kw):
        result=refresh(*a,**kw);review_metrics();return result
    w.refresh_table=refreshed
    w.receipt_toolbar_metrics=controls

