from receiving_image_archive import image_name, source_digest
"""Native Operations pages. Real data and original service contracts only."""
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QLineEdit,QFileDialog,
    QMessageBox,QScrollArea,QFrame,QSizePolicy,QCheckBox)
from rec_status_ui import status_item

def action(text,callback,primary=False):
    b=QPushButton(text);b.setObjectName('primary' if primary else 'workspaceAction');b.clicked.connect(callback);return b

def grid(headers):
    t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.verticalHeader().hide()
    t.setShowGrid(False);t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    t.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
    t.setStyleSheet('QHeaderView::section {background:white;color:#929daf;border:0;border-bottom:1px solid #edf0f5;font-size:12px;font-weight:400;padding:14px 10px;} QTableWidget::item {border-bottom:1px solid #edf0f5;padding:12px 10px;}')
    return t

def page(title,subtitle):
    p=QWidget();v=QVBoxLayout(p);v.setContentsMargins(10,10,10,20);v.setSpacing(22)
    return p,v

class WorkspaceData:
    @staticmethod
    def overview(path,destination,day,report,folder,sheets,images,portable=False):
        from receiving_ledger_loader import load
        from receiving_pr_library import library_path
        from receiving_bulk_ledger import prepare
        _,_,_,_,records=load(path,destination,portable)
        today=[r for r in records if r['day']==day.isoformat()]
        counts=[len(today),sum(r['status'] in ('Chưa ghi sổ','Cần kiểm tra lại') for r in today),sum(r['status']=='Đã ghi sổ' for r in today),sum(r['status']=='Không có PR/PO' for r in today)]
        ready=0;review=0;note=''
        if report and Path(report).is_file() and sheets:
            try:
                preview=prepare(folder,report,sheets,images,library_path(path),path,day.isoformat())
                ready=sum(e['status']=='Sẵn sàng ghi sổ' for e in preview['entries'])
                review=sum(e['status']=='Cần rà lại' for e in preview['entries'])
            except (OSError,ValueError,KeyError) as exc:note=str(exc)
        return counts,ready,review,note

class Home(QWidget):
    def __init__(self,w):
        super().__init__();self.w=w;self.loading=False
        p,v=page('Tổng quan công việc','Những việc cần bạn xử lý trong ngày đang chọn.')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(p)
        stats=QHBoxLayout();stats.setSpacing(32);self.counts=[]
        for text in ['Phiếu trong ngày','Chưa ghi sổ','Đã ghi sổ','Không PR/PO']:
            col=QVBoxLayout();n=QLabel('—');n.setStyleSheet('font-size:28px;color:#25314b;font-weight:600;');label=QLabel(text);label.setStyleSheet('color:#8e99ab;font-size:12px;');col.addWidget(n);col.addWidget(label);stats.addLayout(col);self.counts.append(n)
        stats.addStretch();v.addLayout(stats)
        banner=QFrame();banner.setObjectName('overviewReady');banner.setStyleSheet('QFrame#overviewReady {background:#f7f5ff;border:1px solid #e7e1ff;border-radius:10px;} QLabel {background:transparent;color:#6558bb;}')
        bl=QHBoxLayout(banner);bl.setContentsMargins(18,18,18,18);self.ready=QLabel('Đang kiểm tra dữ liệu…');self.ready.setWordWrap(True);self.ready.setMinimumWidth(320);self.ready.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Preferred);bl.addWidget(self.ready)
        self.review=action('Duyệt danh sách',w.refresh_all_pr,True);bl.addWidget(self.review);bl.addStretch();v.addWidget(banner)
        self.activity=grid(['Hoạt động gần đây','Thời gian','Kết quả','']);self.activity.setObjectName('operationsActivity');self.activity.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);v.addWidget(self.activity,1)
        self.empty=QLabel('Chưa có hoạt động trong phiên này.');self.empty.setStyleSheet('color:#929cad;font-size:12px;');v.addWidget(self.empty)
        task=action('▸ Tác vụ và lịch sử gần đây',lambda:w.ops_task_toggle.toggle());task.setFlat(True);v.addWidget(task,0,Qt.AlignLeft)
        bottom=QHBoxLayout();bottom.addWidget(action('Làm mới',self.refresh));bottom.addStretch();bottom.addWidget(action('Thêm ảnh',lambda:w.fluent_nav.set_current('Tiếp nhận ảnh'),True));v.addLayout(bottom)
    def refresh_activity(self):
        events=self.w.workspace_events;self.activity.setRowCount(len(events));self.empty.setVisible(not events)
        for i,(stamp,title,message,variant) in enumerate(reversed(events)):
            for j,text in enumerate([title,stamp,message]):self.activity.setItem(i,j,QTableWidgetItem(text))
            status_item(self.activity.item(i,2),message,'error' if variant=='error' else 'warning' if variant=='warning' else 'done' if variant=='success' else 'neutral')
            b=action('Nhật ký',lambda:self.w.ops_task_toggle.setChecked(True));self.activity.setCellWidget(i,3,b);self.activity.setRowHeight(i,58)
    def refresh(self):
        if self.loading:return
        self.loading=True;self.review.setEnabled(False);self.ready.setText('Đang xác minh nguồn và trạng thái ghi sổ…')
        from receiving_qt import Worker
        import copy
        w=self.w;context=(w.day,str(w.destination),str(w.report))
        job=Worker(WorkspaceData.overview,w.ledger_path(),w.destination,w.day,w.report,w.folder,copy.deepcopy(list(w.data_by_sheet.items())),list(w.images),getattr(w,'portable_workspace',False))
        def ready(result):
            if context!=(w.day,str(w.destination),str(w.report)):return
            counts,count,review,note=result
            for label,value in zip(self.counts,counts):label.setText(str(value))
            self.ready.setText(note or f'{count} phiếu sẵn sàng ghi sổ · {review} phiếu cần rà.');self.review.setEnabled(count>0 and not self.w.busy)
        def failed(message):
            for n in self.counts:n.setText('—')
            self.ready.setText('Chưa tải được dữ liệu. '+message)
        job.signals.result.connect(ready);job.signals.error.connect(failed);job.signals.finished.connect(lambda:setattr(self,'loading',False));self.w._start_worker(job);self.refresh_activity()

class ImportPage(QWidget):
    """A visible queue, not a file picker disguised as a page."""
    def __init__(self,w):
        super().__init__();self.w=w;self.queue=[];self.context=None
        p,v=page('Tiếp nhận ảnh','Chọn nguồn → kiểm tra ảnh → bắt đầu đọc')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(p)
        self.setObjectName('receivingImportPage')
        self.setStyleSheet('QWidget#receivingImportPage {background:white;color:#334155;font-family:Segoe UI;font-size:13px;} QFrame#importSettingsCard {background:#f8fafc;border:1px solid #dce4ee;border-radius:10px;} QLineEdit {min-height:36px;padding:0 10px;color:#334155;} QPushButton {min-height:36px;padding:0 14px;} QHeaderView::section {color:#475569;background:#f1f5f9;font-weight:600;padding:10px;}')
        heading=QLabel('Tiếp nhận ảnh');heading.setStyleSheet('font-size:22px;font-weight:600;color:#24334b;');v.addWidget(heading)
        subtitle=QLabel('Ảnh mới được đọc tự động khi bật theo dõi. Muốn chọn ảnh và đọc thủ công, hãy tắt tự nhận.');subtitle.setWordWrap(True);v.addWidget(subtitle)
        setup=QHBoxLayout();setup.setSpacing(24);left=QVBoxLayout();right=QVBoxLayout();setup.addLayout(left,3);setup.addLayout(right,2)
        self.auto=QCheckBox('Tự nhận và đọc ảnh mới');self.auto.setObjectName('importAutoRead');self.auto.setChecked(w.inbox_toggle.isChecked());self.auto.toggled.connect(w.inbox_toggle.setChecked);w.inbox_toggle.toggled.connect(self.auto.setChecked);left.addWidget(self.auto)
        self.auto_status=QLabel();self.auto_status.setWordWrap(True);left.addWidget(self.auto_status)
        self.auto_source=QLabel();self.auto_source.setWordWrap(True);self.auto_source.setTextInteractionFlags(Qt.TextSelectableByMouse);left.addWidget(self.auto_source)
        self.last_summary=QLabel();self.last_summary.setWordWrap(True);left.addWidget(self.last_summary)
        source_actions=QHBoxLayout();source_actions.addWidget(action('Thiết lập tự nhận',lambda:__import__('rec_inbox_page').show(w)))
        def open_source():
            source=Path(w.inbox_source)
            if source.is_dir():__import__('os').startfile(str(source))
            else:QMessageBox.information(self,'Chưa có thư mục','Thư mục nhận ảnh chưa tồn tại. Kiểm tra Thiết lập tự nhận.')
        source_actions.addWidget(action('Mở thư mục ảnh',open_source));source_actions.addStretch();left.addLayout(source_actions)
        right.addWidget(QLabel('Ngày lưu và nơi lưu',objectName='section'))
        fields=QHBoxLayout();self.day=QLineEdit();self.day.setReadOnly(True);self.day.setMaximumWidth(145);fields.addWidget(self.day)
        self.destination=QLineEdit();self.destination.setReadOnly(True);fields.addWidget(self.destination,1);right.addLayout(fields)
        destination_actions=QHBoxLayout();destination_actions.addWidget(action('Đổi ngày / nơi lưu',lambda:w.fluent_nav.set_current('Cài đặt')))
        def open_saved():
            from receiving_service import day_directory
            folder=day_directory(w.destination,w.day)
            if folder.is_dir():__import__('os').startfile(str(folder))
            else:QMessageBox.information(self,'Chưa có thư mục','Chưa có thư mục cho ngày đang chọn.')
        destination_actions.addWidget(action('Mở thư mục ngày',open_saved));right.addLayout(destination_actions)
        hint=QLabel('Ngày lưu báo cáo không thay đổi ngày trên chứng từ.');hint.setWordWrap(True);hint.setStyleSheet('color:#64748b;font-size:12px;');right.addWidget(hint);right.addStretch();v.addLayout(setup)
        table_heading=QHBoxLayout();self.queue_summary=QLabel('Danh sách ảnh');self.queue_summary.setStyleSheet('font-size:14px;font-weight:600;');table_heading.addWidget(self.queue_summary);table_heading.addStretch()
        self.add=action('Thêm ảnh',self.choose);table_heading.addWidget(self.add);table_heading.addWidget(action('Ghép cùng phiếu',self.merge));v.addLayout(table_heading)
        self.table=grid(['Chọn','Tên ảnh','Loại ảnh','Trạng thái']);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Fixed);self.table.setColumnWidth(0,52);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);self.table.setColumnWidth(2,140);self.table.setColumnWidth(3,200);self.table.setMinimumHeight(220);v.addWidget(self.table,1)
        self.table.itemChanged.connect(lambda *_:self.selection_summary())
        self.message=QLabel();self.message.setWordWrap(True);v.addWidget(self.message)
        bottom=QHBoxLayout();self.read_hint=QLabel();bottom.addWidget(self.read_hint,1);self.read=action('Đọc ảnh đã chọn',self.start,True);bottom.addWidget(self.read);v.addLayout(bottom)
        self.auto.toggled.connect(lambda *_:self.refresh())
    def selection_summary(self):
        count=sum(self.table.item(i,0) is not None and self.table.item(i,0).checkState()==Qt.Checked for i in range(self.table.rowCount()))
        self.queue_summary.setText(f'Danh sách ảnh · {self.table.rowCount()} ảnh · Đang chọn {count}')
        if hasattr(self,'read'):
            self.read.setEnabled(count>0 and not self.w.busy and not self.w.inbox_toggle.isChecked())
            self.read_hint.setText('Đang tự nhận ảnh mới; không cần bấm Đọc.' if self.w.inbox_toggle.isChecked() else 'Chọn ảnh chưa đọc rồi bấm Đọc ảnh đã chọn.')
    def refresh(self):
        context=(self.w.day,str(self.w.destination))
        if context!=self.context:self.queue=[];self.context=context
        self.auto.setChecked(self.w.inbox_toggle.isChecked())
        self.auto_status.setText(('Tự nhận đang bật · '+self.w.inbox_status.text()) if self.w.inbox_toggle.isChecked() else 'Chế độ thủ công · Chọn ảnh rồi bấm Đọc ảnh đã chọn')
        enabled=self.w.inbox_toggle.isChecked()
        self.auto_status.setStyleSheet('background:'+('#ecfdf5;color:#166534;border:1px solid #bbf7d0;' if enabled else '#f1f5f9;color:#475569;border:1px solid #e2e8f0;')+'padding:12px;border-radius:8px;font-weight:600;')
        self.auto_source.setText('Nguồn ảnh: '+Path(self.w.inbox_source).name);self.auto_source.setToolTip(str(self.w.inbox_source));self.last_summary.clear()
        import json
        try:
            last=json.loads((self.w.root/'.receiving/inbox-last-result.json').read_text(encoding='utf-8'))
            self.last_summary.setText('Lượt gần nhất: '+last['day']+' · '+str(len(last['images']))+' ảnh');self.last_summary.setToolTip(str(last.get('report','')))
        except (OSError,ValueError,KeyError):pass
        for image in self.w.images:
            if image not in self.queue:self.queue.append(image)
        self.day.setText(self.w.day.strftime('%d/%m/%Y'));self.destination.setText(str(self.w.destination));self.destination.setToolTip(str(self.w.destination));self.destination.setCursorPosition(0);self.populate()
    def populate(self):
        checks={self.table.item(i,1).data(Qt.UserRole):self.table.item(i,0).checkState() for i in range(self.table.rowCount()) if self.table.item(i,1)}
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.queue))
        try:owners=self.w.pr_image_owners()
        except (OSError,ValueError):owners={}
        self.queue.sort(key=lambda p:(0 if self.w.image_to_sheets.get(image_name(p)) else 1 if owners.get(image_name(p)) else 2,p.name.casefold()))
        for i,p in enumerate(self.queue):
            c=QTableWidgetItem();c.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);c.setCheckState(checks.get(str(p),Qt.Checked));self.table.setItem(i,0,c)
            for j,text in enumerate([p.name,'Chưa phân loại','Sẵn sàng' if p.is_file() else 'Thiếu ảnh'],1):self.table.setItem(i,j,QTableWidgetItem(text))
            linked=bool(self.w.image_to_sheets.get(image_name(p)))
            status_item(self.table.item(i,2),'Phiếu giao' if linked else 'Ảnh PR' if owners.get(image_name(p)) else 'Chưa phân loại','neutral')
            status_item(self.table.item(i,3),'Đã có trong báo cáo' if linked and p.is_file() else 'Đã ghép PR' if owners.get(image_name(p)) and p.is_file() else 'Chờ đọc' if p.is_file() else 'Thiếu ảnh','done' if linked and p.is_file() else 'ready' if p.is_file() else 'error')
            self.table.item(i,1).setData(Qt.UserRole,str(p))
            self.table.setRowHeight(i,52)
        self.table.blockSignals(False);self.selection_summary()
    def choose(self):
        if self.w.busy:return
        paths,_=QFileDialog.getOpenFileNames(self,'Chọn ảnh','','Ảnh (*.jpg *.jpeg *.png *.webp *.heic *.heif)')
        for p in map(Path,paths):
            if p not in self.queue:self.queue.append(p)
        self.populate()
    def merge(self):
        if self.w.busy:return
        self.w.merge_images()
    def start(self):
        if self.w.busy or self.w.inbox_toggle.isChecked():return
        selected=[p for i,p in enumerate(self.queue) if self.table.item(i,0).checkState()==Qt.Checked]
        if not selected:self.message.setText('Chọn ít nhất một ảnh trước khi đọc.');return
        if any(not p.is_file() for p in selected):self.message.setText('Có ảnh không còn tồn tại. Chọn lại nguồn ảnh.');return
        from receiving_service import import_images,digest,day_images,paths
        try:
            import_images(self.w.root,self.w.day,selected,self.w.destination)
            _,report=paths(self.w.root,self.w.day,self.w.destination)
            hashes={source_digest(p) for p in selected}
            actual=[];seen=set()
            for p in day_images(report.parent):
                key=source_digest(p)
                if key in hashes and key not in seen:actual.append(p);seen.add(key)
            if not actual:raise ValueError('Không tìm thấy ảnh đã nhập trong ngày.')
            self.w._workspace_read_selection=actual
            self.w.read_images()
        except Exception as exc:self.message.setText('Chưa đọc được: '+str(exc))
        finally:self.w._workspace_read_selection=None

def install(w,callbacks,page_layout):
    # Header is outside the sidebar host, exactly as the approved reference.
    header=w.global_action_header;page_layout.removeWidget(header);header.setParent(None)
    header.setMinimumHeight(48);header.layout().setContentsMargins(24,6,24,6)
    old=w.takeCentralWidget();old.setParent(None)
    outer=QWidget();lv=QVBoxLayout(outer);lv.setContentsMargins(0,0,0,0);lv.setSpacing(0);lv.addWidget(header);lv.addWidget(old,1);w.setCentralWidget(outer)
    for b in header.findChildren(QPushButton):b.hide()
    ready_status=QLabel('● Sẵn sàng');ready_status.setStyleSheet('color:#168057;font-size:11px;');header.layout().addWidget(ready_status)
    # Place status next to the page title and remove the empty global band.
    title=w.receipt_page.findChild(QLabel,'opsPageTitle')
    title_row=title.parentWidget().layout().itemAt(0).layout()
    for label in [w.ops_profile,ready_status]:
        header.layout().removeWidget(label);title_row.addWidget(label);label.show()
        label.setStyleSheet('font-family:Segoe UI;font-size:12px;color:#56647b;')
    title.hide()
    header.hide()
    old_busy=w.set_busy
    def reflect_busy(value,message=''):
        old_busy(value,message);ready_status.setText('● Đang xử lý' if value else '● Sẵn sàng')
    w.set_busy=reflect_busy
    w.workspace_events=[]
    old_notice=w.show_top_notice
    def notice(title,message,variant='info'):
        w.workspace_events.append((datetime.now().strftime('%H:%M'),title,message,variant));w.workspace_events=w.workspace_events[-100:]
        old_notice(title,message,variant)
        if hasattr(w,'workspace_home'):w.workspace_home.refresh_activity()
    w.show_top_notice=notice
    end=w.task_display.end
    def finished(*a,**kw):
        end(*a,**kw)
        if not w.task_display.active:w.ops_task_toggle.setChecked(False)
    w.task_display.end=finished
    home=Home(w);imports=ImportPage(w);w.main_pages.addWidget(home);w.main_pages.addWidget(imports)
    w.workspace_home=home;w.workspace_import=imports
    if hasattr(w,'ops_overview'):
        previous=w.ops_overview;w.main_pages.removeWidget(previous);previous.deleteLater()
    w.ops_overview=home
    w.ops_refresh_overview=home.refresh
    def show_home():w.main_pages.setCurrentWidget(home);home.refresh()
    def show_import():imports.refresh();w.main_pages.setCurrentWidget(imports)
    callbacks['Tổng quan']=show_home;callbacks['Tiếp nhận ảnh']=show_import
    # All expected primary entries exist; child views remain contextual.
    side=w.fluent_nav
    side.setFixedWidth(182);w.fluent_host.sync_side();side.header_layout.setContentsMargins(0,0,0,0)
    side.pin.hide()
    for label,icon in [('Tra cứu phiếu','search'),('Tiếp nhận ảnh','upload'),('Chờ giao bù','package'),('Nguồn cần rà','alert-circle'),('Nhà cung cấp','building'),('Giá mua','table')]:
        if label not in side.keys():side.add_item(label,icon=icon)
    def open_ledger_tab(tab_name,nav_key):
        from PySide6.QtWidgets import QTabWidget
        from PySide6.QtCore import QSignalBlocker
        if w.busy:return
        current = getattr(w, 'ledger_page', None)
        if current is None or w.main_pages.currentWidget() is not current or w.ledger_page_path != w.ledger_path():
            w.show_shortage_ledger()
        ledger=getattr(w,'ledger_page',None)
        if ledger is None or w.main_pages.currentWidget() is not ledger:return
        tabs=ledger.findChild(QTabWidget)
        if tabs:
            for i in range(tabs.count()):
                if tabs.tabText(i)==tab_name or tabs.tabText(i).startswith(tab_name+' ('):tabs.setCurrentIndex(i);break
        # The shared ledger opener selects its default nav entry. Restore the
        # requested entry without dispatching another navigation/refresh.
        with QSignalBlocker(side):side.set_current(nav_key)
    callbacks['Sổ nhận hàng']=lambda:open_ledger_tab('Tất cả phiếu','Sổ nhận hàng')
    def show_shortage(unknown=False):
        open_ledger_tab('Chờ giao bù','Nguồn cần rà' if unknown else 'Chờ giao bù')
        combo=w.ledger_page.findChild(__import__('PySide6.QtWidgets',fromlist=['QComboBox']).QComboBox,'ledgerItemFilter') if getattr(w,'ledger_page',None) else None
        if combo:combo.setCurrentIndex(combo.findData('unknown' if unknown else 'short'))
    callbacks['Chờ giao bù']=lambda:show_shortage(False)
    callbacks['Nguồn cần rà']=lambda:show_shortage(True)
    callbacks['Giá mua']=lambda:__import__('rec_price_workspace').show(w)
    callbacks['Tra cứu phiếu']=lambda:__import__('rec_receipt_search').show(w)
    callbacks['Nhà cung cấp']=lambda:__import__('rec_supplier_page').show(w)
    while side._body.count():
        it=side._body.takeAt(0)
        if it.widget():it.widget().hide()
    side._section_labels=[]
    for title,keys in [('CÔNG VIỆC',['Tổng quan','Tiếp nhận ảnh','Kiểm tra phiếu','Thư viện PR']),('THEO DÕI',['Tra cứu phiếu','Sổ nhận hàng','Chờ giao bù','Nguồn cần rà','Giá mua','Google Sheets','Xuất phiếu']),('QUẢN LÝ',['Tra cứu danh mục','Nhà cung cấp','Cài đặt'])]:
        if title!='CÔNG VIỆC':
            label=QLabel(title);label.setStyleSheet('font-size:10px;color:#98a1b1;padding:15px 12px 7px;');side._section_labels.append(label);side._body.addWidget(label)
        for key in keys:
            item=side.item(key);side._body.addWidget(item);item.show();item.setStyleSheet('QPushButton {background:transparent;border:0;text-align:left;color:#7e889b;padding:10px 12px;border-radius:8px;} QPushButton:checked {background:#eeebff;color:#5548c3;font-weight:600;}')
    side._body.addStretch()
    from rec_reading_page import install as install_reading
    install_reading(w,callbacks)
    from rec_receipt_page import install as install_receipt
    install_receipt(w)

    from rec_youtube_navigation import install as install_navigation
    install_navigation(w)
    from rec_grouped_navigation import install as install_groups
    install_groups(w, callbacks)
