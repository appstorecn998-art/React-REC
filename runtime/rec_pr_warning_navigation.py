"""Compact warning navigation and direct corrective action."""
from PySide6.QtWidgets import QWidget,QHBoxLayout,QComboBox,QPushButton,QAbstractItemView


def install(panel,layout,view,source,results,items,actions):
    host=QWidget();host.setObjectName('prWarningNavigation');bar=QHBoxLayout(host);bar.setContentsMargins(0,0,0,8)
    picker=QComboBox();picker.setObjectName('prWarningPicker');picker.setMinimumWidth(180);bar.addWidget(picker,1)
    previous=QPushButton('‹');following=QPushButton('›');fix=QPushButton('Xử lý');fix.setObjectName('prWarningFix')
    previous.setToolTip('Cảnh báo trước');following.setToolTip('Cảnh báo sau')
    for button in (previous,following,fix):bar.addWidget(button)
    for control in (picker,previous,following,fix):control.setStyleSheet('font-size:14px;color:#334155;min-height:36px;')
    layout.addWidget(host)
    def chosen(*_):
        row=picker.currentData()
        if row is None or row>=len(results):return
        view.setCurrentCell(row,0);source.setCurrentCell(row,0);source.cellClicked.emit(row,0);view.cellClicked.emit(row,0)
        view.scrollToItem(view.item(row,0),QAbstractItemView.PositionAtCenter)
        flags=set(results[row].get('alerts',[]))
        label='Quy đổi đơn vị' if 'unit' in flags else 'Duyệt giá' if flags & {'price','unknown_price'} else 'Duyệt nhận dư' if 'over' in flags else 'Ghép dòng' if flags & {'unlinked','duplicate_link'} else 'Xem chi tiết'
        fix.setText(label);fix.setEnabled(True)
    def refresh():
        prior=picker.currentData();picker.blockSignals(True);picker.clear()
        for row,result in enumerate(results):
            flags=set(result.get('alerts',[]))
            if not flags or view.isRowHidden(row):continue
            p=result.get('pr_index');name=str(items[p].get('item_name') or '') if p is not None else str(result.get('name') or '')
            labels=[label for flag,label in [('unit','Quy đổi ĐVT'),('price','Lệch giá'),('unknown_price','Thiếu giá'),('short','Thiếu'),('over','Dư'),('unlinked','Chưa ghép'),('specification','Quy cách'),('code','Mã hàng')] if flag in flags]
            picker.addItem(' · '.join(labels or ['Cần rà'])+' — '+name,row)
        if prior is not None and picker.findData(prior)>=0:picker.setCurrentIndex(picker.findData(prior))
        picker.setToolTip(str(picker.count())+' dòng cần rà · chọn cảnh báo rồi bấm Xử lý')
        picker.blockSignals(False);host.setVisible(picker.count()>0);fix.setEnabled(picker.count()>0)
        previous.setEnabled(picker.count()>1);following.setEnabled(picker.count()>1)
    def move(delta):
        if picker.count():picker.setCurrentIndex((picker.currentIndex()+delta)%picker.count());chosen()
    def apply():
        chosen();row=picker.currentData()
        if row is None:return
        flags=set(results[row].get('alerts',[]))
        index=1 if 'unit' in flags else 4 if flags & {'price','unknown_price'} else 5 if 'over' in flags else 0 if flags & {'unlinked','duplicate_link'} else None
        if index is not None and actions[index].isEnabled():actions[index].click()
        else:
            from PySide6.QtWidgets import QPushButton
            button=next((b for b in panel.findChildren(QPushButton) if b.text()=='Chi tiết / giá'),None)
            if button:button.click()
    picker.activated.connect(chosen);previous.clicked.connect(lambda:move(-1));following.clicked.connect(lambda:move(1));fix.clicked.connect(apply)
    return refresh
