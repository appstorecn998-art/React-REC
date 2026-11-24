"""Flat PR pages, based on template.html r-main/r-two/r-form (not r-dialog)."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel,QWidget,QVBoxLayout,QHBoxLayout,QDialogButtonBox

def flat_page(dialog,title,subtitle,content,notice,buttons):
    layout=dialog.layout()
    while layout.count():
        item=layout.takeAt(0)
        if item.widget():item.widget().hide()
    layout.setContentsMargins(10,10,10,20);layout.setSpacing(16)
    dialog.setStyleSheet('''QDialog,QWidget#savedPRPicker {background:white;color:#53617a;font-family:"Segoe UI";font-size:12px;}
    QTableWidget {background:white;border:0;color:#53617a;outline:0;}
    QTableWidget::item {border:0;border-bottom:1px solid #edf0f5;padding:10px;}
    QTableWidget::item:selected {background:#f8f7ff;color:#40506c;}
    QHeaderView::section {background:white;border:0;border-bottom:1px solid #e9edf4;color:#96a0b1;font-size:11px;font-weight:400;padding:10px;}
    QLineEdit {background:white;color:#526079;border:1px solid #dfe4ed;border-radius:7px;padding:0 11px;min-height:36px;max-height:36px;}
    QPushButton {background:white;border:1px solid #e0e4ee;color:#59657a;border-radius:7px;padding:0 12px;min-height:34px;max-height:34px;}
    QPushButton:disabled {color:#b2b7c4;border-color:#edf0f5;}
    ''')
    arrow=Path(__file__).with_name('design-combo-arrow.svg').as_posix()
    dialog.setStyleSheet(dialog.styleSheet()+f'QComboBox::drop-down {{border:0;width:24px;}} QComboBox::down-arrow {{image:url("{arrow}");width:10px;height:6px;}}')
    layout.addWidget(content,1);content.show()
    notice.setWordWrap(True);notice.setStyleSheet('background:#f7f5ff;border:1px solid #e8e3ff;border-radius:9px;color:#746d9c;padding:14px 16px;font-size:12px;');layout.addWidget(notice);notice.show()
    buttons.setLayoutDirection(Qt.RightToLeft)
    primary=buttons.button(QDialogButtonBox.Ok) or buttons.button(QDialogButtonBox.Save)
    for button in buttons.buttons():
        button.setFixedSize(button.fontMetrics().horizontalAdvance(button.text())+30,36)
        if button==primary:button.setStyleSheet('QPushButton {background:#6054d8;border:1px solid #6054d8;color:white;font-weight:600;} QPushButton:disabled {background:#c8c3ed;border-color:#c8c3ed;color:#f8f7ff;}')
    buttons.setFixedWidth(sum(x.width() for x in buttons.buttons() if not x.isHidden())+24)
    footer=QWidget();row=QHBoxLayout(footer);row.setContentsMargins(0,0,0,0);row.addStretch();row.addWidget(buttons);layout.addWidget(footer);buttons.show()
    dialog.resize(1440,900)
