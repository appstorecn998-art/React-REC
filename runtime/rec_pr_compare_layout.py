from rec_pr_outcome import receipt_outcome,has_previous_receipts,review_outcome,outcome_color
"""Screen 11 from the served design; calculation and write callbacks stay original."""
from pathlib import Path
from decimal import Decimal
from PySide6.QtGui import QFont,QColor,QIcon,QFontMetrics
from PySide6.QtCore import Qt,QModelIndex,QRect,QEvent,QSize,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMenu,QSizePolicy,QScrollArea,QFrame,QCompleter,QStyledItemDelegate,QLineEdit,QListWidget,QListWidgetItem

class QuickLinkCombo(QComboBox):
    """Editable picker that only commits after an explicit user gesture."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._user_gesture=False
        self.view().installEventFilter(self)
    def setEditable(self,value):
        super().setEditable(value)
        if value:self.lineEdit().installEventFilter(self)
    def showPopup(self):self._user_gesture=True;super().showPopup()
    def event(self,event):
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.KeyPress):self._user_gesture=True
        return super().event(event)
    def eventFilter(self,obj,event):
        if obj is self.lineEdit() and event.type()==QEvent.Type.MouseButtonPress and event.button()==Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason);self.showPopup();return True
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.KeyPress):self._user_gesture=True
        return super().eventFilter(obj,event)
    def allow_commit(self):
        value=self._user_gesture;self._user_gesture=False;return value

class WrappedChoiceDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        width=max(360,option.rect.width() or 560)
        metrics=option.fontMetrics
        height=metrics.boundingRect(QRect(0,0,width-32,2000),Qt.TextWordWrap,str(index.data() or '')).height()+20
        return QSize(width,max(40,height))

class WrappedLinkButton(QPushButton):
    """Show the entire assignment; search lives only in the opened picker."""
    def __init__(self,combo,parent=None):
        super().__init__(parent);self.combo=combo;self.setObjectName('wrappedPRLink')
        self.setStyleSheet('QPushButton#wrappedPRLink {min-height:0px;max-height:16777215px;padding:0;background:white;border:1px solid #e0e4ee;border-radius:7px;text-align:left;}')
        box=QHBoxLayout(self);box.setContentsMargins(10,9,10,9);box.setSpacing(8)
        self.caption=QLabel(combo.currentText());self.caption.setObjectName('wrappedPRLinkText');self.caption.setWordWrap(True);self.caption.setTextFormat(Qt.PlainText)
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents);self.caption.setStyleSheet('background:transparent;border:0;padding:0;color:#59657a;font-size:12px;')
        self.caption.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        arrow=QLabel('⌄');arrow.setFixedWidth(12);arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        box.addWidget(self.caption,1);box.addWidget(arrow)
        self.setToolTip(combo.currentText());self.clicked.connect(self.open_picker)
    def fit_width(self,width):
        key=(width,self.caption.text(),self.caption.font().toString())
        if key==getattr(self,'_fit_key',None):return self.height()
        self._fit_key=key
        text_width=max(20,width-48)
        self.caption.ensurePolished()
        height=self.caption.fontMetrics().boundingRect(QRect(0,0,text_width,100000),Qt.TextWordWrap,self.caption.text()).height()
        total=max(44,height+24)
        self.caption.setFixedHeight(height+2)
        self.setStyleSheet('QPushButton#wrappedPRLink {min-height:'+str(total)+'px;max-height:'+str(total)+'px;padding:0;background:white;border:1px solid #e0e4ee;border-radius:7px;text-align:left;}')
        self.setFixedHeight(total)
        return total
    def open_picker(self):
        popup=QFrame(self,Qt.Popup);popup.setObjectName('prAssignmentPicker');popup.setStyleSheet('QFrame#prAssignmentPicker {background:white;border:1px solid #dcdfea;border-radius:8px;}')
        layout=QVBoxLayout(popup);search=QLineEdit();search.setPlaceholderText('Tìm tên hàng hoặc số dòng…');search.setClearButtonEnabled(False);layout.addWidget(search)
        listing=QListWidget();listing.setObjectName('prAssignmentChoices');listing.setWordWrap(True);listing.setTextElideMode(Qt.ElideNone);listing.setUniformItemSizes(False);listing.setSpacing(3);listing.setItemDelegate(WrappedChoiceDelegate(listing));layout.addWidget(listing)
        def fill(text=''):
            listing.clear()
            for index in range(self.combo.count()):
                title=self.combo.itemText(index)
                if text.casefold() in title.casefold():
                    item=QListWidgetItem(title);item.setData(Qt.UserRole,index);listing.addItem(item)
            if listing.count():listing.setCurrentRow(0)
        def choose(item):
            index=item.data(Qt.UserRole);combo=self.combo
            popup.close()
            combo.setCurrentIndex(index);combo.activated.emit(index)
        search.textChanged.connect(fill);listing.itemClicked.connect(choose);listing.itemActivated.connect(choose)
        search.returnPressed.connect(lambda:choose(listing.currentItem()) if listing.currentItem() else None)
        fill();screen=self.screen().availableGeometry();width=min(620,max(280,screen.width()-24));popup.resize(width,min(380,screen.height()-40))
        point=self.mapToGlobal(self.rect().bottomLeft());point.setX(max(screen.left()+8,min(point.x(),screen.right()-width-8)))
        if point.y()+popup.height()>screen.bottom():point.setY(max(screen.top()+8,self.mapToGlobal(self.rect().topLeft()).y()-popup.height()))
        popup.move(point);popup.show();search.setFocus();self.picker=popup

class DesignTable(QTableWidget):
    def fit_rows(self):
        for row in range(self.rowCount()):
            height=84
            for col in range(5):
                item=self.item(row,col)
                if item is not None and not self.isColumnHidden(col):
                    width=max(20,self.columnWidth(col)-24)
                    height=max(height,QFontMetrics(item.font()).boundingRect(QRect(0,0,width,100000),Qt.TextWordWrap,item.text()).height()+26)
            holder=self.cellWidget(row,5)
            if holder is not None:
                button=holder.findChild(WrappedLinkButton)
                if button is not None:height=max(height,button.fit_width(max(20,self.columnWidth(5)-16))+16)
                height=max(height,holder.sizeHint().height()+8)
            self.setRowHeight(row,height)
        self.doItemsLayout()
        for row in range(self.rowCount()):
            holder=self.cellWidget(row,5)
            if holder is not None:holder.layout().invalidate();holder.layout().activate()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        width=self.viewport().width()
        ratios=[.28,.07,.11,.09,.20,.25]
        total=sum(r for c,r in enumerate(ratios) if not self.isColumnHidden(c))
        for col,ratio in enumerate(ratios):
            if not self.isColumnHidden(col):self.setColumnWidth(col,int(width*ratio/total))
        self.fit_rows()
        if not getattr(self,"_fit_pending",False):
            self._fit_pending=True
            def settle():
                self._fit_pending=False;self.fit_rows()
            QTimer.singleShot(0,settle)

def install(w,panel,source,results,items,prior_count,order,only_review,expanded,actions,save,record,detail,vocab_status,vocab_apply):
    layout=panel.layout()
    def conceal(item):
        if item.widget():item.widget().hide()
        elif item.layout():
            child=item.layout()
            while child.count():conceal(child.takeAt(0))
    while layout.count():conceal(layout.takeAt(0))
    panel.setObjectName('prComparePage');layout.setContentsMargins(30,10,38,0);layout.setSpacing(0)
    panel.setStyleSheet('''QWidget#prComparePage {background:white;color:#53617a;font-family:"Segoe UI";font-size:15px;}
    QTableWidget#prCompareSummary {background:white;border:0;outline:0;color:#53617a;}
    QTableWidget#prCompareSummary::item {border:0;border-bottom:1px solid #edf0f5;padding:10px;font-size:15px;}
    QTableWidget#prCompareSummary::item:selected {background:#f8f7ff;color:#40506c;}
    QHeaderView::section {background:white;border:0;border-bottom:1px solid #e9edf4;color:#96a0b1;font-size:14px;padding:10px;font-weight:400;}
    QPushButton,QComboBox {font-size:12px;background:white;border:1px solid #e0e4ee;border-radius:7px;padding:0 12px;min-height:34px;max-height:34px;color:#59657a;}
    QPushButton {font-size:11px;}
    QPushButton:disabled {color:#afb5c2;border-color:#edf0f5;}
    ''')
    arrow=Path(__file__).with_name('design-combo-arrow.svg').as_posix()
    panel.setStyleSheet(panel.styleSheet()+f'QComboBox::drop-down {{border:0;width:24px;}} QComboBox::down-arrow {{image:url("{arrow}");width:10px;height:6px;}}')
    supplier=next((str(x.get('pr_supplier_name')) for x in items if x.get('pr_supplier_name')),'')
    number=next((str(x.get('pr_reference_id')) for x in items if x.get('pr_reference_id')),'Chưa rõ số PR')
    tools=QHBoxLayout();tools.setSpacing(10);
    if hasattr(panel,'vat_button'):tools.addWidget(panel.vat_button);panel.vat_button.show()
    tools.addWidget(order);order.setFixedSize(137,38);order.show()
    filtering=QComboBox();filtering.setObjectName('prCompareFilter');filtering.addItems(['Tất cả dòng','Chỉ cảnh báo']);only_review.setChecked(False)
    filtering.currentIndexChanged.connect(lambda i:only_review.setChecked(i==1));filtering.setFixedSize(120,38);tools.addWidget(filtering)
    tools.addStretch()
    bulk=panel.findChild(QPushButton,'bulkUnreceived')
    if bulk:
        bulk.setText('Xác nhận các món còn lại chưa giao lần này');bulk.setMinimumWidth(250);tools.insertWidget(2,bulk);bulk.show()
    details_button=QPushButton('Chi tiết / giá');details_button.setFixedSize(112,36);tools.insertWidget(tools.count()-1,details_button)
    tools_host=QWidget();tools_host.setLayout(tools);tools.setContentsMargins(0,0,0,0)
    tools_scroll=QScrollArea();tools_scroll.setFrameShape(QFrame.NoFrame);tools_scroll.setWidgetResizable(True);tools_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);tools_scroll.setWidget(tools_host);tools_scroll.setFixedHeight(58)
    bulk_links=QPushButton('Duyệt ghép hàng loạt');bulk_links.clicked.connect(panel.bulk_link);tools.insertWidget(0,bulk_links)
    layout.addWidget(tools_scroll);layout.addSpacing(8)
    view=DesignTable(0,6);view.setObjectName('prCompareSummary');view.setHorizontalHeaderLabels(['Hàng PR / dòng giao','Đặt','Nhận trước','Lần này','Kết quả nhận hàng','Gán nhanh'])
    view.verticalHeader().hide();view.setShowGrid(False);view.setWordWrap(True);view.setTextElideMode(Qt.ElideNone);view.setEditTriggers(QAbstractItemView.NoEditTriggers);view.setSelectionBehavior(QAbstractItemView.SelectRows);view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);view.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed);view.horizontalHeader().setFixedHeight(44)
    menu=QMenu(view);details_action=menu.addAction('Chi tiết số lượng / giá')
    def show_details():
        from rec_pr_price_detail_modal import show
        show(w,source,detail)
    details_button.clicked.connect(show_details);details_action.triggered.connect(show_details)
    view.setContextMenuPolicy(Qt.CustomContextMenu)
    view.setToolTip('Nhấp chuột phải vào dòng để ghép hàng, quy đổi hoặc điều chỉnh.')
    from rec_pr_warning_navigation import install as warning_navigation
    refresh_warnings=warning_navigation(panel,layout,view,source,results,items,actions)
    layout.addWidget(view,1);layout.addWidget(source);layout.addWidget(detail);source.hide();detail.hide()
    status=QLabel();status.setWordWrap(True);status.setStyleSheet('font-size:13px;color:#a16207;padding:6px 0;');layout.addWidget(status)
    def commit_quick(quick,p,value,reverse=False):
        if quick.currentIndex()<0:return
        actual=panel.quick_link(p,value)
        if actual!=value:
            quick.setCurrentIndex(0 if reverse else quick.findData(actual))
    def refresh():
        from rec_pr_review import inspection
        try:
            diagnostic=dict(state='stale',reason='Đối chiếu đang thay đổi, chưa lưu') if w.pr_dirty() else inspection(w,w.reference_link_path().with_suffix('.comparison.json'),False);value=diagnostic['state']
        except (OSError,ValueError):diagnostic=dict(state='pending',reason='Chưa xác nhận');value='pending'
        from rec_pr_review import decorate_tab
        decorate_tab(w,w.review_tabs.tabText(1),diagnostic)
        current=view.currentRow();view.blockSignals(True);view.setUpdatesEnabled(False)
        view.setColumnHidden(2,not has_previous_receipts(results,prior_count))
        view.setRowCount(len(results))
        for i,result in enumerate(results):
            unit=str(result.get('unit') or '')
            def number(value):
                if value is None:return '—'
                text=format(Decimal(str(value)),'f')
                if '.' in text:text=text.rstrip('0').rstrip('.')
                return text.replace('.',',')
            def quantity(value):return '—' if value is None else number(value)+(' '+unit if unit else '')
            p=result.get('pr_index');name=str(items[p].get('item_name') or result.get('name') or '') if p is not None else str(result.get('name') or '')
            row=result.get('row');name+=' → '+('dòng '+str(row-1) if row is not None else 'Chưa giao' if 'đã xác định' in str(result.get('status','')).lower() else 'Chưa gán dòng' if result.get('pr_index') is not None else 'Chưa gán PR')
            if p is None and row is not None:name+=(' · Tiền cọc ngoài PR' if result.get('deposit') else ' · Chưa gán PR')
            values=[name,quantity(result.get('ordered')),('Chưa xác minh' if 'previous_receipt_invalid' in result.get('alerts',[]) else quantity(result.get('previous_received',0 if prior_count==0 else None))),quantity(0 if row is None and 'đã xác định' in str(result.get('status','')).lower() else result.get('received')),review_outcome(result,prior_count)]
            for col,text in enumerate(values):
                cell=view.item(i,col) or QTableWidgetItem();cell.setText(text);cell.setToolTip(name+'\n'+str(result.get('status') or '')+'\n'+str(result.get('source') or ''))
                if col==0:
                    font=cell.font();font.setWeight(QFont.DemiBold);cell.setFont(font)
                if col==4:
                    flags=set(result.get('alerts',[]))
                    cell.setForeground(QColor(outcome_color(result,prior_count)))
                    font=cell.font();font.setWeight(QFont.DemiBold);cell.setFont(font)
                if view.item(i,col) is not cell:view.setItem(i,col,cell)
            editor=w.pr_editors.get(i)
            original=editor if isinstance(editor,QComboBox) else editor.findChild(QComboBox) if editor else None
            choices=tuple((original.itemText(n),original.itemData(n)) for n in range(original.count())) if original else ()
            candidates=tuple((r.get('pr_index'),r.get('row')) for r in results)
            signature=(p,row,choices,candidates if p is None else (),bool(result.get('deposit')),bool(w.busy),bool(result.get('no_topup')),str(result.get('no_topup',{}).get('action','')),str(result.get('remaining')),tuple(result.get('alerts',[])))
            old=view.cellWidget(i,5)
            if old is not None and getattr(old,'content_signature',None)==signature:
                view.setRowHidden(i,source.isRowHidden(i));continue
            quick=QuickLinkCombo();quick.setObjectName('quickPRLink');quick.setMinimumWidth(130);quick.setEditable(True);quick.setInsertPolicy(QComboBox.NoInsert)
            if result.get('deposit'):quick.setEnabled(False)
            quick.addItem('Chọn hàng PR…' if p is None else 'Chọn dòng giao…','unknown')
            if p is not None:
                quick.addItem('Không giao lần này',None)
                editor=w.pr_editors.get(i)
                # Use the original editor's labels/data; no duplicate matcher.
                combo=editor if isinstance(editor,QComboBox) else editor.findChild(QComboBox) if editor else None
                if combo:
                    for n in range(combo.count()):
                        value=combo.itemData(n)
                        if value not in ('unknown',None):quick.addItem(combo.itemText(n),value)
                target=row if row is not None else (None if 'đã xác định' in str(result.get('status','')).lower() else 'unknown')
                quick.setCurrentIndex(max(0,quick.findData(target)));quick.lineEdit().setCursorPosition(0);quick.lineEdit().deselect()
                quick.activated.connect(lambda index,p=p,quick=quick:commit_quick(quick,p,quick.itemData(index)))
            else:
                for candidate in results:
                    cp=candidate.get('pr_index')
                    if cp is not None and candidate.get('row') is None:
                        quick.addItem(str(cp+1)+' · '+str(items[cp].get('item_name') or 'Hàng PR'),cp)
                quick.activated.connect(lambda index,row=row,quick=quick:commit_quick(quick,quick.itemData(index),row,True) if index>0 else None)
            quick.lineEdit().setStyleSheet('QLineEdit {border:0;background:transparent;padding:0px 2px;min-height:0px;max-height:16777215px;}');quick.lineEdit().setTextMargins(0,0,0,0)
            quick.lineEdit().setPlaceholderText('Gõ để tìm tên…');quick.lineEdit().setClearButtonEnabled(False)
            quick.setEnabled(not w.busy and quick.count()>1)
            quick.setToolTip('Chọn để gán ngay. Chưa lưu hoặc ghi sổ. Có thể đổi lại trước khi lưu.')
            quick.setFixedHeight(36)
            holder=QWidget();holder.setObjectName('quickPRLinkHolder')
            holder.setStyleSheet('QWidget#quickPRLinkHolder {background:transparent;border:0;}')
            stack=QVBoxLayout(holder);stack.setContentsMargins(8,8,8,8);stack.setSpacing(4);stack.setAlignment(Qt.AlignVCenter)
            quick.setParent(holder);quick.hide()
            button=WrappedLinkButton(quick,holder);button.setEnabled(quick.isEnabled());stack.addWidget(button)
            quick.setToolTip(quick.currentText()+'\nGõ để tìm; chọn hàng để xem đầy đủ tên PR và phiếu giao bên dưới bảng.')
            if p is not None and (result.get('no_topup') or (result.get('remaining') is not None and Decimal(str(result['remaining']))>0 and not (set(result.get('alerts',[]))-{'short'}))):
                stop=QPushButton('Tiếp tục giao bù' if result.get('no_topup') and result['no_topup'].get('action')!='reopen' else 'Không cần giao bù')
                stop.setObjectName('noTopup_'+str(p));stop.setToolTip('Quyết định theo từng món; lưu nháp rồi Kiểm xong phiếu để áp dụng vào sổ. Không đổi số thực nhận.')
                stop.clicked.connect(lambda checked=False,p=p:panel.no_topup(p));stack.addWidget(stop)
            holder.content_signature=signature
            view.setCellWidget(i,5,holder)
            view.setRowHidden(i,source.isRowHidden(i))
        view.fit_rows()
        if current>=0:view.setCurrentCell(current,0)
        else:
            view.clearSelection();view.setCurrentIndex(QModelIndex())
        flags={flag for r in results for flag in r.get('alerts',[])}
        badges=[]
        for flag,text,color in [('specification','Cần rà quy cách','#b07c1b'),('unit','Cần quy đổi ĐVT','#b07c1b'),('price','Lệch giá','#b13f51'),('previous_receipt_invalid','Nguồn lần nhận khác thay đổi; cần cập nhật phiếu','#b07c1b'),('unlinked','Chưa gán dòng','#b07c1b'),('code','Khác mã hàng','#b13f51'),('unknown_quantity','Chưa rõ lượng','#b07c1b'),('unknown_price','Chưa rõ giá','#b07c1b')]:
            if flag in flags:badges.append(f'<span style="color:{color}">• {text}</span>')
        if any('đã gán và lưu' in str(r.get('match_reason','')) for r in results):badges.append('<span style="color:#7e8ba1">• Cặp gán đã nhớ</span>')
        pending=sum(r.get('pr_index') is not None and r.get('row') is None and 'đã xác định' not in str(r.get('status','')).lower() for r in results)
        outside=sum(r.get('pr_index') is None and r.get('row') is not None and not r.get('deposit') and (r.get('received') is None or r.get('received')!=0) for r in results)
        if pending or outside:badges.insert(0,f'{pending} món PR chưa xác định · {outside} dòng giao chưa gán PR')
        status.setVisible(bool(badges));status.setText('　'.join(badges));status.setToolTip('\n'.join(str(r.get('status','')) for r in results))
        visible=sum(not view.isRowHidden(i) for i in range(view.rowCount()))
        view.setMinimumHeight(120);view.setMaximumHeight(16777215);view.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        view.blockSignals(False);view.setUpdatesEnabled(True)
        refresh_warnings()
    def select(row,*_):
        if row>=0:
            source.setCurrentCell(row,0);source.cellClicked.emit(row,0)
            if row<len(results):
                result=results[row];p=result.get('pr_index');delivery=dict(w.data_by_sheet.get(w.current_sheet,[])).get(result.get('row'),{})
                pr_name=str(items[p].get('item_name') or '') if p is not None else 'Chưa gán PR'
                delivery_name=str(delivery.get('Tên hàng trên phiếu (Ảnh)') or ('Không giao lần này' if 'đã xác định' in str(result.get('status','')).lower() else 'Chưa gán dòng'))
                view.item(row,0).setToolTip('PR: '+pr_name+'\nPhiếu giao: '+delivery_name)
    view.cellClicked.connect(select);only_review.toggled.connect(lambda _:refresh())
    def refresh_no_topup(index):
        # Patch the existing row only: no model reset, image reload or source I/O.
        for row,result in enumerate(results):
            if result.get('pr_index')!=index:continue
            cell=view.item(row,4)
            if cell:cell.setText(review_outcome(result,prior_count))
            button=view.findChild(QPushButton,'noTopup_'+str(index))
            if button:button.setText('Tiếp tục giao bù' if result.get('no_topup') and result['no_topup'].get('action')!='reopen' else 'Không cần giao bù')
        from rec_pr_review import decorate_tab
        decorate_tab(w,w.review_tabs.tabText(1),dict(state='stale',reason='Quyết định giao bù đang thay đổi, cần lưu và kiểm xong phiếu'))
    panel.refresh_no_topup=refresh_no_topup
    panel.refresh_compare_view=refresh
    layout.addSpacing(9)
    def size_button(button,text,primary=False):
        button.setText(text)
        font=QFont('Segoe UI');font.setPixelSize(12);font.setWeight(QFont.DemiBold if primary else QFont.Normal)
        button.setFont(font)
        # State selectors must share the same box metrics, including focus.
        button.setStyleSheet(button.styleSheet()+"""
QPushButton,QPushButton:hover,QPushButton:pressed,QPushButton:checked,QPushButton:focus,QPushButton:disabled {
 padding:0px 12px;margin:0px;border-width:1px;border-style:solid;min-height:34px;max-height:34px;font-family:'Segoe UI';font-size:12px;
}
""")
        button.ensurePolished()
        width=button.fontMetrics().horizontalAdvance(text)+30
        if not button.icon().isNull():width+=button.iconSize().width()+6
        button.setFixedSize(width,36);button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        button.show()
    # Keep the original buttons as the authority for enabled state and callbacks.
    def original(button,title):
        button.hide()
        return (title,button.click,button)
    groups=[
        ('Ghép hàng',[
            original(actions[0],'Ghép với dòng giao…'),
            ('PR sai tên / hàng thay thế…',panel.edit_substitution,None)]),
        ('Đơn vị / quy cách',[
            original(actions[1],'Quy đổi đơn vị…'),
            original(actions[2],'Duyệt mua nguyên gói…'),
            ('Xác nhận cùng quy cách…',panel.confirm_spec,None)]),
        ('Số lượng',[
            original(actions[3],'Sửa số lượng NCC giao…'),
            original(actions[5],'Duyệt nhận dư…'),
            ('Nhập số lượng trên PR…',panel.edit_pr_quantity,None),
            ('Nhập lượng đã nhận trước khi dùng REC…',lambda:__import__('rec_opening_balance_page').show_for_current(w),None)]),
        ('Thao tác khác',[
            original(actions[4],'Duyệt giá…'),
            ('Xác nhận / bỏ cọc vỏ ngoài PR…',panel.edit_deposit,None)])]
    menu.setObjectName('prRowActions')
    menu.setStyleSheet('QMenu {background:white;color:#334155;border:1px solid #cbd5e1;padding:6px;font-size:14px;} QMenu::item {padding:10px 20px;} QMenu::item:selected {background:#ede9fe;color:#4338ca;} QMenu::item:disabled {color:#94a3b8;}')
    menu.addSeparator()
    bindings=[]
    for title,entries in groups:
        dropdown=menu.addMenu(title);dropdown.setStyleSheet(menu.styleSheet())
        for caption,callback,original_button in entries:
            entry=dropdown.addAction(caption);entry.triggered.connect(lambda checked=False,callback=callback:callback())
            bindings.append((entry,original_button))
    def sync_menu():
        for entry,original_button in bindings:
            entry.setEnabled(not w.busy and (original_button is None or original_button.isEnabled()))
    menu.aboutToShow.connect(sync_menu)
    def open_row_menu(pos):
        row=view.rowAt(pos.y())
        if row<0:return
        view.setCurrentCell(row,0)
        select(row)
        menu.popup(view.viewport().mapToGlobal(pos))
    view.customContextMenuRequested.connect(open_row_menu)
    # Retain the original asynchronous vocabulary review controls when applicable.
    layout.addWidget(vocab_status);layout.addWidget(vocab_apply)
    notice=QLabel('Gợi ý ghép dòng hoặc cặp đã nhớ không tự xác nhận quy cách, giá hay lượng. Lưu đối chiếu không ghi sổ.');notice.setWordWrap(True);notice.setStyleSheet('background:#f7f5ff;border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;color:#746d9c;');notice.hide();save.setToolTip(notice.text());record.setToolTip('Xác nhận và ghi sổ sau khi xử lý cảnh báo. '+notice.text())
    footer=QHBoxLayout()
    footer.addStretch();save.setText('Lưu nháp');record.setText('Kiểm xong phiếu')
    save.setToolTip('Giữ cách ghép và quy đổi đang làm; chưa hoàn tất rà, chưa ghi sổ.')
    record.setToolTip('Lưu xác nhận đã kiểm phiếu vào hàng chờ. Bấm Hoàn tất đợt kiểm ở thanh trên để ghi sổ tất cả phiếu đã kiểm.')
    footer.setSpacing(8)
    for button in (save,record):
        size_button(button,button.text(),button is record);footer.addWidget(button,0,Qt.AlignVCenter)
    record.setStyleSheet('QPushButton {background:#6054d8;border:1px solid #6054d8;color:white;font-size:11px;font-weight:600;border-radius:7px;padding:0;min-height:34px;max-height:34px;} QPushButton:disabled {background:#c8c3ed;border-color:#c8c3ed;}')
    size_button(record,record.text(),True)
    layout.addLayout(footer);refresh()

