"""Two-column edit form retaining original fields, warehouse signals and changes()."""
from PySide6.QtWidgets import QWidget,QGridLayout,QVBoxLayout,QLabel,QScrollArea,QFrame,QDialogButtonBox,QFormLayout
from PySide6.QtCore import Qt

def arrange(dialog,outer,form):
    fields=[];footers=[]
    for i in range(form.rowCount()):
        label=form.itemAt(i,QFormLayout.LabelRole);field=form.itemAt(i,QFormLayout.FieldRole);span=form.itemAt(i,QFormLayout.SpanningRole)
        if field and field.widget():
            text=label.widget().text() if label and label.widget() else ''
            fields.append((text,field.widget()))
            if label and label.widget():label.widget().hide()
        elif span and span.widget():footers.append(span.widget())
    outer.removeItem(form)
    host=QWidget();grid=QGridLayout(host);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(24);grid.setVerticalSpacing(16);grid.setAlignment(Qt.AlignTop)
    for i,(text,editor) in enumerate(fields):
        wrap=QWidget();v=QVBoxLayout(wrap);v.setContentsMargins(0,0,0,0);v.setSpacing(6)
        label=QLabel(text);label.setBuddy(editor);label.setStyleSheet('font-size:12px;color:#8793a8;');v.addWidget(label)
        editor.setParent(wrap);editor.setStyleSheet(editor.styleSheet()+'\nQLineEdit,QComboBox {min-height:0px;max-height:38px;padding:6px 10px;}');editor.setFixedHeight(40);v.addWidget(editor);grid.addWidget(wrap,i//2,i%2)
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setWidget(host);outer.addWidget(scroll,1)
    for widget in footers:
        widget.setParent(dialog);outer.addWidget(widget)
        if isinstance(widget,QDialogButtonBox):
            widget.setStyleSheet('QDialogButtonBox {border-top:1px solid #edf0f5;padding-top:14px;}')
        else:widget.setStyleSheet('background:#f7f5ff;color:#7568aa;padding:12px;border-radius:8px;')
    dialog.setObjectName('receiptEditDialog');dialog.resize(840,650)
