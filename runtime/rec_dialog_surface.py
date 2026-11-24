"""Shared native surface matching the approved review designs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QDialogButtonBox

def surface(dialog,title,subtitle,table,notice,buttons,extras=None):
    layout=dialog.layout()
    while layout.count():
        item=layout.takeAt(0)
        if item.widget():item.widget().hide()
    layout.setContentsMargins(28,24,28,24);layout.setSpacing(8)
    dialog.setStyleSheet(dialog.styleSheet()+'''
        QDialog {background:white;}
        QFrame#reviewBackdrop {background:#eef0f7;border:0;border-radius:12px;}
        QFrame#reviewCard {background:white;border:1px solid #e2e6ef;border-radius:12px;}
        QTableWidget {background:white;border:0;color:#475569;font-size:12px;outline:0;}
        QTableWidget::item {border:0;border-bottom:1px solid #f0f2f7;padding:10px;}
        QHeaderView::section {background:white;color:#94a0b5;border:0;border-bottom:1px solid #e9edf5;padding:10px;font-weight:400;font-size:12px;}
    ''')
    backdrop=QFrame();backdrop.setObjectName('reviewBackdrop');outer=QVBoxLayout(backdrop);outer.setContentsMargins(24,24,24,24)
    card=QFrame();card.setObjectName('reviewCard');inner=QVBoxLayout(card);inner.setContentsMargins(24,24,24,30);inner.setSpacing(16)
    heading=QLabel(title);heading.setStyleSheet('font-size:18px;font-weight:600;color:#27334a;');inner.addWidget(heading)
    if extras:
        inner.addWidget(extras);extras.show()
    inner.addWidget(table,1);table.show()
    notice.setStyleSheet('background:#f7f5ff;color:#8b80b1;border:1px solid #ece5ff;border-radius:9px;padding:15px;font-size:12px;');notice.setWordWrap(True);inner.addWidget(notice);notice.show()
    buttons.setLayoutDirection(Qt.RightToLeft)
    buttons.setStyleSheet('QDialogButtonBox {border:0;padding:0;}')
    for button in buttons.buttons():
        primary=button==(buttons.button(QDialogButtonBox.Save) or buttons.button(QDialogButtonBox.Ok))
        button.setFixedSize(button.fontMetrics().horizontalAdvance(button.text())+36,36)
        base=('background:#6552df;color:white;border:1px solid #6552df;font-weight:600;' if primary else 'background:white;color:#7e899c;border:1px solid #e4e8f2;')
        button.setStyleSheet('QPushButton {'+base+'border-radius:6px;padding:0px;min-height:34px;max-height:34px;} QPushButton:disabled {background:#e2def7;color:#aaa2ca;border-color:#e2def7;}')
    buttons.setFixedWidth(sum(b.width() for b in buttons.buttons())+12)
    footer=QWidget();row=QHBoxLayout(footer);row.setContentsMargins(0,0,0,0);row.addStretch();row.addWidget(buttons)
    inner.addWidget(footer);buttons.show();outer.addWidget(card);layout.addWidget(backdrop,1)
    dialog.resize(1400,620)
