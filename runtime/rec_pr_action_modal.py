"""Compact PR dialogs with a stationary action footer and scrollable forms."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QScrollArea,QFrame,QLabel,QLayout,QSizePolicy,QLineEdit,QPlainTextEdit,QComboBox,QPushButton,QDialogButtonBox,QGridLayout,QListWidget,QWidget
from PySide6.QtCore import Qt


def show_modal(w,page):
    dialog=QDialog(w);dialog.setModal(True)
    titles={'unitConversionPage':'Quy đổi đơn vị','packagingPage':'Duyệt đóng gói','quantityCorrectionPage':'Sửa lượng NCC','priceApprovalPage':'Duyệt giá'}
    dialog.setWindowTitle(titles.get(page.objectName(),'Thao tác dòng PR'))
    dialog.setStyleSheet(w.styleSheet())
    layout=QVBoxLayout(dialog);layout.setContentsMargins(12,10,12,10);layout.setSpacing(8)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(page);layout.addWidget(scroll,1)
    page.layout().setContentsMargins(0,0,0,0)
    page.layout().setSizeConstraint(QLayout.SetDefaultConstraint)
    page.setMinimumSize(0,0);page.setMaximumSize(16777215,16777215)
    # Move the original footer, preserving every signal and approval callback.
    box=page.findChild(QDialogButtonBox)
    if box is not None:
        footer=box.parentWidget()
        if footer.layout() is not None:
            parent_layout=footer.parentWidget().layout()
            if parent_layout:parent_layout.removeWidget(footer)
            footer.setParent(dialog);layout.addWidget(footer)
            footer.layout().setContentsMargins(8,6,8,0)
    for frame in page.findChildren(QFrame):
        if frame.objectName()=='reviewBackdrop':frame.layout().setContentsMargins(8,8,8,8)
        elif frame.objectName()=='reviewCard':
            inner=frame.layout();inner.setContentsMargins(16,14,16,14);inner.setSpacing(10)
            for i in range(inner.count()):inner.setStretch(i,0)
            inner.setAlignment(Qt.AlignTop)
    for column in page.findChildren(QVBoxLayout):
        column.setAlignment(Qt.AlignTop);column.setSpacing(min(column.spacing(),8))
    for grid in page.findChildren(QGridLayout):
        grid.setVerticalSpacing(10);grid.setHorizontalSpacing(16)
        for row in range(grid.rowCount()):
            for col in range(grid.columnCount()):
                item=grid.itemAtPosition(row,col)
                if item and item.widget():
                    widget=item.widget();widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
                    if widget.layout():widget.layout().setAlignment(Qt.AlignTop)
    for control in page.findChildren(QLabel)+page.findChildren(QLineEdit)+page.findChildren(QPlainTextEdit)+page.findChildren(QComboBox):
        control.setStyleSheet(control.styleSheet()+';font-size:15px;')
        if isinstance(control,QLabel):
            control.setWordWrap(True);control.setMinimumHeight(0);control.setMaximumHeight(16777215)
            control.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
            if 'padding:15px' in control.styleSheet():control.setStyleSheet(control.styleSheet()+';padding:8px 10px;')
        elif isinstance(control,(QLineEdit,QComboBox)):
            control.setStyleSheet(control.styleSheet()+';min-height:0px;padding:0 10px;');control.setFixedHeight(40)
        elif isinstance(control,QPlainTextEdit):control.setFixedHeight(64)
    # The footer lives outside page now; size its buttons after final font styling.
    for button in dialog.findChildren(QPushButton):
        button.setStyleSheet(button.styleSheet()+';font-size:14px;')
        button.ensurePolished();width=button.fontMetrics().horizontalAdvance(button.text())+36
        if button.parentWidget() is box or (box is not None and button.parentWidget() is box.parentWidget()):
            button.setFixedSize(width,38)
        else:button.setMinimumWidth(width)
    if box is not None:
        box.setFixedWidth(sum(b.width() for b in box.buttons())+max(12,box.layout().spacing()*(len(box.buttons())-1)+12))
    for evidence in page.findChildren(QWidget,'approvalEvidencePanel'):
        evidence.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
        listing=evidence.findChild(QListWidget)
        if listing:listing.setFixedHeight(54)
        history=evidence.findChild(QPushButton,'approvalEvidenceHistory')
        if history:history.setVisible(history.isEnabled())
    screen=w.screen().availableGeometry();width=min(880,screen.width()-40)
    page.ensurePolished();page.resize(width-28,1);page.layout().activate()
    content=page.layout().totalHeightForWidth(width-28) if page.layout().hasHeightForWidth() else page.sizeHint().height()
    footer_height=box.parentWidget().sizeHint().height() if box is not None else 0
    dialog.resize(width,min(max(360,content+footer_height+30),screen.height()-64))
    dialog.setMinimumWidth(min(660,width));dialog.move(screen.center()-dialog.rect().center())
    page.destroyed.connect(dialog.deleteLater);page._pr_modal=dialog;dialog.open()
    return dialog


def close_modal(page):
    dialog=getattr(page,'_pr_modal',None)
    if dialog is not None:dialog.accept()
