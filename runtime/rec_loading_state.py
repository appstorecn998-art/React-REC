"""Visible asynchronous loading/error state without invented percentages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QProgressBar,QPushButton

class LoadingState(QWidget):
    def __init__(self,section,title,description,retry=None,parent=None):
        super().__init__(parent)
        self.setObjectName('dataLoadingState')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(22)
        heading=QLabel(section);heading.setStyleSheet('font-size:22px;font-weight:600;color:#26324b;');layout.addWidget(heading)
        card=QFrame();card.setObjectName('loadingCard');box=QVBoxLayout(card);box.setContentsMargins(24,22,24,22);box.setSpacing(12)
        self.title=QLabel(title);self.title.setWordWrap(True);self.title.setStyleSheet('font-size:16px;font-weight:600;color:#40506c;');box.addWidget(self.title)
        self.description=QLabel(description);self.description.setWordWrap(True);self.description.setStyleSheet('color:#68758d;font-size:13px;');box.addWidget(self.description)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.setFixedHeight(5);box.addWidget(self.progress)
        self.retry=QPushButton('Thử lại');self.retry.setObjectName('retryDataLoading');self.retry.hide()
        if retry:self.retry.clicked.connect(retry)
        self.can_retry=retry is not None
        row=QHBoxLayout();row.addWidget(self.retry);row.addStretch();box.addLayout(row);layout.addWidget(card)
        self.skeleton=QWidget();rows=QVBoxLayout(self.skeleton);rows.setContentsMargins(0,0,0,0);rows.setSpacing(12)
        for width in (460,620,540,620):
            stripe=QFrame();stripe.setFixedHeight(32);stripe.setMaximumWidth(width);stripe.setStyleSheet('background:#f3f4f9;border-radius:6px;');rows.addWidget(stripe)
        layout.addWidget(self.skeleton)
        self.setStyleSheet('QFrame#loadingCard {background:#faf9ff;border:1px solid #e7e3f6;border-radius:10px;} QProgressBar {border:0;background:#edeaf7;border-radius:2px;} QProgressBar::chunk {background:#7968dd;border-radius:2px;} QPushButton#retryDataLoading {background:white;color:#6054c7;border:1px solid #dcd5f3;border-radius:6px;padding:8px 16px;}')
    def fail(self,message):
        self.progress.setRange(0,100);self.progress.setValue(0);self.progress.hide();self.skeleton.hide()
        self.title.setText('Chưa tải được dữ liệu');self.description.setText(message);self.retry.setVisible(self.can_retry)
