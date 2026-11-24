"""Receipt review backed exclusively by the debt workspace."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QSplitter,QTableView,QLineEdit,QAbstractItemView,QInputDialog,QDialog,QFormLayout,QCheckBox,QDialogButtonBox,QMessageBox,QHeaderView,QTableWidget,QTableWidgetItem,QMenu
from receiving_service import paths,snapshot,invoice_pages,edit_row
from receiving_image_archive import archived_images
from receiving_qt import PreviewView,ReceiptTableModel,EditDialog,Worker,DepartmentDelegate,CleanCellDelegate,ReceivingWindow

class DebtTableModel(ReceiptTableModel):
    """Cache stable cell roles until the receipt is replaced."""
    def set_rows(self,*args,**kwargs):
        self._cells={}
        super().set_rows(*args,**kwargs)
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid():return None
        key=(index.row(),index.column(),role)
        if key not in self._cells:self._cells[key]=super().data(index,role)
        return self._cells[key]


class DebtReview(QWidget):
    def __init__(self,page):
        super().__init__(page);self.page=page;self.saving=False;self.report=None;self.data={};self.expected=None;self.images=[];self.catalog=None;self.root=page.owner.root
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        bar=QHBoxLayout();self.receipts=QComboBox();self.receipts.setMinimumWidth(240)
        self.supplier_totals=QPushButton('Tổng theo NCC');self.supplier_totals.clicked.connect(self.show_supplier_totals);self.delete_receipt_button=QPushButton('Xóa phiếu');self.delete_receipt_button.clicked.connect(self.delete_receipt);self.lookup=QPushButton('Tra mã hàng');self.lookup.clicked.connect(self.lookup_code);self.department=QPushButton('Bộ phận');self.department.clicked.connect(self.set_department);self.vat=QPushButton('Tách VAT');self.vat.clicked.connect(self.vat_dialog);self.bulk_date=QPushButton('Đổi ngày');self.bulk_date.clicked.connect(lambda:__import__('rec_debt_bulk_date').show(self));self.reload=QPushButton('Tải lại');self.edit=QPushButton('Sửa dòng chọn')
        self.previous=QPushButton('←');self.next=QPushButton('→');self.position=QLabel();self.add_line=QPushButton('Thêm dòng')
        self.previous.setToolTip('Phiếu trước');self.next.setToolTip('Phiếu sau')
        self.previous.clicked.connect(lambda:self.receipts.setCurrentIndex(self.receipts.currentIndex()-1));self.next.clicked.connect(lambda:self.receipts.setCurrentIndex(self.receipts.currentIndex()+1));self.add_line.clicked.connect(lambda:self.manual_line(False))
        bar.addWidget(QLabel('Kiểm phiếu'));bar.addWidget(self.previous);bar.addWidget(self.receipts,1);bar.addWidget(self.next);bar.addWidget(self.position);bar.addWidget(self.add_line);bar.addWidget(self.supplier_totals);bar.addWidget(self.lookup);bar.addWidget(self.department);bar.addWidget(self.vat);bar.addWidget(self.bulk_date);bar.addWidget(self.reload);bar.addWidget(self.edit);bar.addWidget(self.delete_receipt_button);layout.addLayout(bar)
        split=QSplitter(Qt.Horizontal);layout.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,0,0)
        self.pages=QComboBox();lv.addWidget(self.pages);self.preview=PreviewView();lv.addWidget(self.preview,1);split.addWidget(left)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(0,0,0,0)
        self.search=QLineEdit();self.search.setPlaceholderText('Tìm tên hàng / mã hàng trong phiếu…');rv.addWidget(self.search)
        self.model=DebtTableModel(self);self.table=QTableView();self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setWordWrap(True);self.table.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed);self.table.setItemDelegate(DepartmentDelegate(self));self.table.setShowGrid(False);self.table.setAlternatingRowColors(True);self.model.editRequested.connect(self.save_row_changes);self.table.setContextMenuPolicy(Qt.CustomContextMenu);self.table.customContextMenuRequested.connect(self.show_row_menu)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel);self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed);self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.verticalHeader().hide();rv.addWidget(self.table,1)
        footer=QHBoxLayout();self.receipt_total=QLabel();self.ncc_total=QLabel();self.receipt_total.setWordWrap(True);self.ncc_total.setWordWrap(True);footer.addWidget(self.receipt_total,1);footer.addWidget(self.ncc_total,1);rv.addLayout(footer)
        split.addWidget(right);split.setSizes([420,700])
        self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.receipts.currentIndexChanged.connect(lambda _:self.select_receipt(self.receipts.currentData() or ''));self.pages.currentIndexChanged.connect(self.select_page)
        self.search.textChanged.connect(self.filter_rows);self.edit.clicked.connect(self.edit_selected)
        self.reload.clicked.connect(lambda:self.load_day(self.day) if self.report else None)
    def load_day(self,day):
        if getattr(self.page,'reading',False) and getattr(self.page,'active',{}).get('day')==day.isoformat():
            self.page.feedback('Ngày này đang được đọc. Chọn một ngày đã hoàn tất để kiểm hoặc sửa.');return
        try:
            _,report=paths(self.page.root/'CauHinh',day,self.page.root/'DuLieu')
            expected,data=snapshot(report);data=[(name,rows) for name,rows in data if rows];images=archived_images(report.parent)
        except Exception as exc:self.page.status.setText('Chưa tải được: '+str(exc));return
        self.setVisible(bool(data));self.page.empty.setVisible(not bool(data))
        if not self.page.running:self.page.status.clear()
        self.day=day;self.report=report;self.expected=expected;self.data=dict(data);self.images=images
        previous=(self.receipts.currentData() or '');self.receipts.blockSignals(True);self.receipts.clear();
        for name,rows in self.data.items():
            suppliers=list(dict.fromkeys(str(v.get('Nhà cung cấp') or '').strip() for _,v in rows if str(v.get('Nhà cung cấp') or '').strip()))
            supplier=' / '.join(suppliers) if suppliers else 'Chưa rõ NCC'
            self.receipts.addItem(supplier+' · '+name,name)
            self.receipts.setItemData(self.receipts.count()-1,supplier+' · '+name,Qt.ToolTipRole)
        if previous in self.data:self.receipts.setCurrentIndex(self.receipts.findData(previous))
        self.receipts.blockSignals(False);self.select_receipt((self.receipts.currentData() or ''));self.page.render()
    def select_receipt(self,name):
        rows=self.data.get(name,[])
        index=self.receipts.currentIndex();self.previous.setEnabled(index>0);self.next.setEnabled(0<=index<self.receipts.count()-1);self.position.setText(f'{index+1}/{self.receipts.count()}')
        self.add_line.setEnabled(bool(rows) and 'Phiếu nhập tay' in rows[0][1])
        display=[]
        for row,values in rows:
            value=dict(values);qty=value.get('Thực nhận');price=value.get('Đơn giá')
            value['Thành tiền']=qty*price if isinstance(qty,(int,float)) and isinstance(price,(int,float)) else 'CHƯA RÕ'
            display.append((row,value))
        self.model.set_rows(display,columns=['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Tên chuẩn hệ thống','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Thành tiền','Ngày giao hàng','Thời gian chụp','Bộ phận','Mã kho','Tên kho','Nhà cung cấp','Ngày giao hàng','Ngày nhận hàng xác nhận'])
        widths={'Tên hàng trên phiếu (Ảnh)':240,'Tên chuẩn hệ thống':240,'Nhà cung cấp':220,'Bộ phận':120,'Tên kho':180}
        for col,header in enumerate(self.model.visible):self.table.setColumnWidth(col,widths.get(header,110))
        self.filter_rows()
        self.pages.blockSignals(True);self.pages.clear()
        for i,p in enumerate(invoice_pages(name,rows,self.images),1):self.pages.addItem(f'Trang {i} · {p.name}',p)
        self.pages.blockSignals(False);self.pages.setVisible(self.pages.count()>1);self.select_page(0)
        from rec_debt_totals import summarize,label
        current=summarize([(name,rows)]);all_suppliers=summarize(list(self.data.items()))
        if current:
            combined={'total':sum(v['total'] for v in current.values()),'missing':sum(v['missing'] for v in current.values())}
            self.receipt_total.setText('Tổng tiền phiếu: '+label(combined))
            self.ncc_total.setText('NCC trong ngày: '+label(all_suppliers[next(iter(current))]) if len(current)==1 else 'Phiếu có nhiều NCC · Bấm Tổng theo NCC')
        else:self.receipt_total.clear();self.ncc_total.clear()
        self.status.setText(f'{len(rows)} mặt hàng');self.table.setToolTip('Nhấp đúp dòng để sửa')
    def select_page(self,index):
        path=self.pages.itemData(index)
        if path:self.preview.set_image(path)
        else:
            self.preview.request_id+=1;self.preview.source_path=None;self.preview.scene().clear();self.preview.item=None
    def filter_rows(self,*_):
        query=self.search.text().strip().casefold()
        for i,(_,values) in enumerate(self.model.rows):self.table.setRowHidden(i,bool(query) and query not in ' '.join(str(v or '') for v in values.values()).casefold())
    def edit_selected(self):
        index=self.table.currentIndex()
        if not self.report or not index.isValid():return
        row,_=self.model.rows[index.row()];values=dict(self.data[(self.receipts.currentData() or '')])[row];dialog=EditDialog(values,self)
        if dialog.warehouse_choice is not None:dialog.warehouse_choice.setItemText(0,'Chưa rõ / Không chọn kho')
        if not dialog.exec():return
        changes=dialog.changes(values)
        if not changes:return
        report,expected,sheet=self.report,self.expected,(self.receipts.currentData() or '')
        def work():
            catalog={}
            if 'Mã vật tư' in changes:
                import AutoWatcher as aw
                catalog,_=aw.load_catalog_data(self.page.owner.root/'DanhMuc.xlsm')
            edit_row(report,expected,sheet,row,changes,catalog,warehouse_directory=self.get_warehouses())
        self.saving=True;self.page.render();self.status.setText('Đang lưu thay đổi…')
        task=Worker(work)
        task.signals.result.connect(lambda _:self.load_day(self.day))
        task.signals.error.connect(lambda message:self.status.setText('Chưa lưu được: '+message))
        def finished():self.saving=False;self.page.render()
        task.signals.finished.connect(finished);self.page.owner._start_worker(task)

    def manual_line(self,create=True):
        from receiving_service import digest
        from rec_debt_manual import save_line
        from pathlib import Path
        day=self.page.day.date().toPython() if create else self.day
        if getattr(self.page,'reading',False) and self.page.active['day']==day.isoformat():self.page.feedback('Chờ ngày này đọc xong trước khi tạo hoặc sửa phiếu.');return
        _,report=paths(self.page.root/'CauHinh',day,self.page.root/'DuLieu')
        try:
            expected,data=snapshot(report);data=[(name,rows) for name,rows in data if rows];images=archived_images(report.parent)
        except Exception as exc:self.page.feedback(str(exc),'error');return
        title=(self.receipts.currentData() or '')
        if create:
            title,ok=QInputDialog.getText(self,'Tạo phiếu mới','Tên phiếu (ví dụ: Tay - NCC A):')
            if not ok:return
        values={key:'' for key in ['Nhà cung cấp','Ngày giao hàng','Ngày nhận hàng xác nhận','Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Mã kho','Ghi chú']}
        values['Ngày nhận hàng xác nhận']=day.strftime('%d/%m/%Y')
        if not create:
            old=dict(data).get(title,[])
            if old:
                for key in ('Nhà cung cấp','Ngày giao hàng','Ngày nhận hàng xác nhận','Mã kho'):values[key]=old[0][1].get(key) or ''
        dialog=EditDialog(values,self);dialog.setWindowTitle('Nhập mặt hàng đầu tiên' if create else 'Thêm mặt hàng')
        if dialog.warehouse_choice is not None:dialog.warehouse_choice.setItemText(0,'Chưa rõ / Không chọn kho')
        if not dialog.exec():return
        changes={key:editor.text() for key,editor in dialog.fields.items()}
        image=''
        if create and images:
            choices=['Không kèm ảnh']+[p.name for p in images]
            choice,ok=QInputDialog.getItem(self,'Ảnh phiếu','Chọn ảnh để đối chiếu (không chạy OCR):',choices,0,False)
            if not ok:return
            if choice!=choices[0]:image=choice
        elif not create and old:image=old[0][1].get('Ảnh nguồn') or ''
        if image:changes['Ảnh nguồn']=image
        def work():
            import AutoWatcher as aw
            from rec_debt_data import profile
            cfg=self.page.root/'CauHinh'
            if not all((cfg/name).is_file() for name in ('DanhMuc.xlsm','NhaCungCap.json','Phieu giao hang ngay X.xlsx')):cfg=profile(self.page.root,self.page.owner.root)
            catalog,_=aw.load_catalog_data(cfg/'DanhMuc.xlsm')
            save_line(report,expected,title,changes,catalog,day,image,create,warehouse_directory=self.get_warehouses())
        self.saving=True;self.page.render();self.page.feedback('Đang lưu phiếu nhập tay…','busy',True)
        task=Worker(work)
        def saved(_):
            self.load_day(day);self.receipts.setCurrentIndex(self.receipts.findData(title))
            job=next((j for j in self.page.jobs if j['day']==day.isoformat()),None)
            if job is None:
                job=dict(day=day.isoformat(),count=0,status='Đã đọc');self.page.jobs.append(job)
            job['result']=f'{len(self.data)} phiếu · {sum(len(rows) for rows in self.data.values())} dòng';self.page.persist()
            self.page.feedback('Đã lưu phiếu nhập tay. Có thể bấm Thêm dòng để nhập tiếp.','success')
        task.signals.result.connect(saved);task.signals.error.connect(lambda message:self.page.feedback('Chưa lưu được: '+message,'error'))
        def finished():self.saving=False;self.page.render()
        task.signals.finished.connect(finished);self.page.owner._start_worker(task)

    def vat_dialog(self):
        if not self.report or not (self.receipts.currentData() or ''):return
        name=(self.receipts.currentData() or '');rows=self.data.get(name,[])
        suppliers={str(v.get('Nhà cung cấp') or '').strip() for _,v in rows}
        supplier=next(iter(suppliers)) if len(suppliers)==1 else ''
        dialog=QDialog(self);dialog.setWindowTitle('Tách giá đã gồm VAT');form=QFormLayout(dialog)
        rate=QComboBox();rate.addItem('VAT 8%',8);rate.addItem('VAT 10%',10);rate.addItem('Khôi phục giá gốc',0)
        scope=QComboBox();scope.addItem('Toàn bộ phiếu đang xem','receipt');scope.addItem('Các dòng đã chọn','rows')
        if supplier:scope.addItem('Các phiếu cùng NCC trong ngày đang xem','supplier')
        remember=QCheckBox('Áp dụng cho phiếu mới của NCC này (toàn bộ dòng)');remember.setEnabled(bool(supplier))
        form.addRow('Thuế suất',rate);form.addRow('Áp dụng',scope);form.addRow(remember)
        info=QLabel('Giá trước VAT = giá gốc ÷ (1 + thuế suất). Giữ giá gốc để khôi phục; bấm lặp không chia thêm.');info.setWordWrap(True);form.addRow(info)
        def options():
            allowed=bool(supplier) and scope.currentData()!='rows'
            remember.setText('Bỏ mặc định VAT của NCC này' if rate.currentData()==0 else 'Áp dụng cho phiếu mới của NCC này (toàn bộ dòng)')
            remember.setEnabled(allowed)
            if not allowed:remember.setChecked(False)
        rate.currentIndexChanged.connect(options);scope.currentIndexChanged.connect(options)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if not dialog.exec():return
        selected_rate=rate.currentData();mode=scope.currentData()
        if mode=='receipt':selection={name:[row for row,_ in rows]}
        elif mode=='rows':selection={name:[self.model.rows[i.row()][0] for i in self.table.selectionModel().selectedRows()]}
        else:selection={n:[r for r,v in rs if str(v.get('Nhà cung cấp') or '').strip()==supplier] for n,rs in self.data.items()}
        selection={n:rs for n,rs in selection.items() if rs}
        count=sum(map(len,selection.values()))
        if not count:self.page.feedback('Chọn các dòng cần tách VAT trước.','error');return
        action='Khôi phục giá gốc' if selected_rate==0 else f'Tách VAT {selected_rate}%'
        text=f'{action} cho {count} dòng trong {len(selection)} phiếu?'
        if remember.isChecked():text+='\nLưu mặc định cho các phiếu mới của NCC: '+supplier
        if QMessageBox.question(self,'Xác nhận',text)!=QMessageBox.Yes:return
        report,expected,day=self.report,self.expected,self.day;save_rule=remember.isChecked()
        def work():
            from rec_debt_vat import apply
            return apply(report,expected,selection,selected_rate)
        self.saving=True;self.page.render();self.page.feedback('Đang xử lý VAT…','busy',True)
        task=Worker(work)
        def done(count):
            rule_error=''
            if save_rule:
                try:
                    import json
                    from receiving_service import atomic_json
                    path=self.page.root/'vat-ncc.json';rules=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {};rules.pop(supplier,None) if selected_rate==0 else rules.update({supplier:selected_rate});atomic_json(path,rules)
                except Exception as exc:rule_error=' Chưa lưu được mặc định NCC: '+str(exc)
            self.load_day(day);self.page.feedback(f'Đã {action.lower()} cho {count} dòng.'+rule_error,'error' if rule_error else 'success')
        task.signals.result.connect(done);task.signals.error.connect(lambda message:self.page.feedback('Chưa đổi giá: '+message,'error'))
        def finished():self.saving=False;self.page.render()
        task.signals.finished.connect(finished);self.page.owner._start_worker(task)

    def get_warehouses(self):
        from warehouse_directory import load_warehouse_directory
        catalog=self.page.root/'CauHinh'/'DanhMuc.xlsm'
        if not catalog.exists():catalog=self.page.owner.root/'DanhMuc.xlsm'
        stamp=(str(catalog),catalog.stat().st_mtime_ns,catalog.stat().st_size)
        cached=getattr(self,'_warehouses',None)
        if cached is None or cached[0]!=stamp:self._warehouses=(stamp,load_warehouse_directory(catalog))
        return self._warehouses[1]

    def set_department(self):
        if not self.report or not (self.receipts.currentData() or ''):return
        try:directory=self.get_warehouses()
        except Exception as exc:self.page.feedback('Chưa đọc được DanhMucKho: '+str(exc),'error');return
        choices=['Chưa rõ / Không chọn kho']+[f'{department or "Chưa có bộ phận"} · {name} · {code}' for code,(name,department) in directory.items()]
        chosen,ok=QInputDialog.getItem(self,'Bộ phận / Kho','Chọn từ DanhMucKho:',choices,0,False)
        if not ok:return
        code=([""]+list(directory))[choices.index(chosen)]
        selected=[self.model.rows[i.row()][0] for i in self.table.selectionModel().selectedRows()]
        scopes=['Toàn bộ phiếu']+(['Các dòng đã chọn'] if selected else [])
        scope,ok=QInputDialog.getItem(self,'Áp dụng bộ phận','Áp dụng cho:',scopes,0,False)
        if not ok:return
        report,expected,sheet,day=self.report,self.expected,(self.receipts.currentData() or ''),self.day
        rows=selected if scope=='Các dòng đã chọn' else [r for r,_ in self.data[sheet]]
        from receiving_service import mutate_invoice
        task=Worker(mutate_invoice,report,expected,sheet,'warehouse',rows,warehouse_code=code,directory=directory)
        self.saving=True;self.page.render();self.page.feedback('Đang lưu bộ phận / kho…','busy',True)
        def done(_):
            self.load_day(day);self.page.feedback(f'Đã cập nhật bộ phận cho {len(rows)} dòng.','success')
        task.signals.result.connect(done);task.signals.error.connect(lambda message:self.page.feedback('Chưa lưu được: '+message,'error'))
        def finished():self.saving=False;self.page.render()
        task.signals.finished.connect(finished);self.page.owner._start_worker(task)

    @property
    def busy(self):return self.saving

    def set_busy(self,value,message=''):
        self.saving=value;self.page.render()
        if message:self.page.feedback(message,'busy' if value else 'info',value)

    def _start_worker(self,task):self.page.owner._start_worker(task)

    def lookup_code(self):return ReceivingWindow.lookup_code(self)

    def save_row_changes(self,payload):
        if self.saving or not self.report:return
        row,changes=payload;report,expected,sheet,day=self.report,self.expected,(self.receipts.currentData() or ''),self.day
        def work():
            import AutoWatcher as aw
            catalog=self.catalog or {}
            if 'Mã vật tư' in changes and self.catalog is None:catalog,_=aw.load_catalog_data(self.root/'DanhMuc.xlsm')
            edit_row(report,expected,sheet,row,changes,catalog,warehouse_directory=self.get_warehouses() if 'Mã kho' in changes else None)
        self.set_busy(True,'Đang lưu dòng…');task=Worker(work)
        task.signals.result.connect(lambda _:self.load_day(day))
        task.signals.error.connect(lambda message:self.page.feedback('Chưa lưu được: '+message,'error'))
        task.signals.finished.connect(lambda:self.set_busy(False));self._start_worker(task)

    def show_supplier_totals(self):
        from rec_debt_totals import summarize,label
        dialog=QDialog(self);dialog.setWindowTitle('Tổng tiền theo nhà cung cấp');dialog.setWindowFlags(dialog.windowFlags()|Qt.WindowMaximizeButtonHint|Qt.WindowMinimizeButtonHint)
        screen=self.screen().availableGeometry();dialog.resize(int(screen.width()*.95),int(screen.height()*.90));layout=QVBoxLayout(dialog)
        dialog.setStyleSheet('QTableWidget {font-size:15px;} QHeaderView::section {font-size:14px;font-weight:600;padding:10px;}')
        scope=QComboBox();scope.addItem('Nhóm ngày đang xem','day');scope.addItem('Tất cả nhóm ngày công nợ','all');layout.addWidget(scope)
        note=QLabel('Tính theo thực nhận × đơn giá đang lưu. Chỉ là trước VAT khi giá đã được tách hoặc vốn chưa gồm VAT. Không tự suy thuế.');note.setWordWrap(True);layout.addWidget(note)
        table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Nhà cung cấp','Số phiếu','Số dòng','Tổng tiền']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True);table.setColumnWidth(0,max(400,int(dialog.width()*.48)));table.setColumnWidth(1,95);table.setColumnWidth(2,95);table.setColumnWidth(3,400)
        table.setWordWrap(True);table.setTextElideMode(Qt.ElideNone);table.setAlternatingRowColors(True);table.setEditTriggers(QAbstractItemView.NoEditTriggers);layout.addWidget(table,1)
        state=QLabel();state.setWordWrap(True);layout.addWidget(state)
        def fill(totals):
            table.setRowCount(len(totals))
            for i,(supplier,entry) in enumerate(sorted(totals.items())):
                for col,value in enumerate((supplier,len(entry['receipts']),entry['rows'],label(entry))):
                    cell=QTableWidgetItem(str(value));cell.setToolTip(str(value));table.setItem(i,col,cell)
                table.setRowHeight(i,70)
        def refresh():
            if scope.currentData()=='day':fill(summarize(list(self.data.items())));state.setText('Nhóm ngày '+self.day.strftime('%d/%m/%Y'));return
            scope.setEnabled(False);state.setText('Đang cộng các nhóm ngày…');table.setRowCount(0)
            root=self.page.root
            def work():
                data=[]
                from rec_debt_data import reports
                for report in reports(root):
                    for sheet,rows in snapshot(report)[1]:data.append((str(report)+'::'+sheet,rows))
                return summarize(data)
            task=Worker(work);task.signals.result.connect(fill);task.signals.error.connect(lambda message:state.setText('Chưa cộng được: '+message))
            task.signals.result.connect(lambda _:state.setText('Tất cả nhóm ngày · Kết quả đã lưu tại lúc đọc; nhóm đang chạy có thể chưa đầy đủ.'))
            task.signals.finished.connect(lambda:scope.setEnabled(True));self._start_worker(task)
        scope.currentIndexChanged.connect(refresh);refresh();dialog.exec()

    def build_row_menu(self,pos):
        index=self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isRowSelected(index.row(),index.parent()):self.table.setCurrentIndex(index)
        menu=QMenu(self);available=not self.saving and self.isEnabled();valid=index.isValid() and available
        for text,callback in [('Sửa dòng',self.edit_selected),('Tra mã cho dòng',self.lookup_code),('Xóa dòng',self.delete_selected_row)]:
            action=menu.addAction(text);action.setEnabled(valid);action.triggered.connect(callback)
        menu.addSeparator()
        for text,callback in [('Gán bộ phận / kho…',self.set_department),('Đổi NCC cho cả phiếu…',self.assign_supplier),('Đổi ngày hàng loạt…',lambda:__import__('rec_debt_bulk_date').show(self)),('Tách VAT…',self.vat_dialog),('Tổng tiền theo NCC…',self.show_supplier_totals),('Xóa cả phiếu…',self.delete_receipt)]:
            action=menu.addAction(text);action.setEnabled(bool(self.receipts.currentData()) and available);action.triggered.connect(callback)
        return menu

    def show_row_menu(self,pos):
        menu=self.build_row_menu(pos);menu.exec(self.table.viewport().mapToGlobal(pos));menu.deleteLater()

    def mutate_receipt(self,action,rows,**kwargs):
        from receiving_service import mutate_invoice
        report,expected,sheet,day=self.report,self.expected,self.receipts.currentData(),self.day
        task=Worker(mutate_invoice,report,expected,sheet,action,rows,**kwargs)
        self.set_busy(True,'Đang lưu thay đổi phiếu…')
        def done(_):
            self.load_day(day);self.page.feedback('Đã lưu thay đổi phiếu.','success')
        task.signals.result.connect(done);task.signals.error.connect(lambda message:self.page.feedback('Chưa lưu được: '+message,'error'))
        task.signals.finished.connect(lambda:self.set_busy(False));self._start_worker(task)

    def assign_supplier(self):
        if self.saving or not self.receipts.currentData():return
        import json
        rows=self.data[self.receipts.currentData()];current=sorted({str(v.get('Nhà cung cấp') or '').strip() for _,v in rows}-{''});names=set(current)
        for _,rs in self.data.items():names.update(str(v.get('Nhà cung cấp') or '').strip() for _,v in rs if v.get('Nhà cung cấp'))
        rules=self.page.root/'CauHinh'/'NhaCungCap.json'
        if not rules.exists():rules=self.root/'NhaCungCap.json'
        try:names.update(v['name'] for v in json.loads(rules.read_text(encoding='utf-8-sig')).get('suppliers',[]) if v.get('name'))
        except (OSError,ValueError):pass
        options=sorted(names);initial=options.index(current[0]) if len(current)==1 and current[0] in options else 0
        name,ok=QInputDialog.getItem(self,'Đổi NCC cho cả phiếu',f'Nhà cung cấp · áp dụng tất cả {len(rows)} dòng:',options,initial,True)
        if not ok:return
        name=name.strip()
        if not name:self.page.feedback('Nhập tên nhà cung cấp.','error');return
        if QMessageBox.question(self,'Xác nhận đổi NCC',f'Đổi NCC của toàn bộ {len(rows)} dòng thành:\n{name}?\nSố lượng, đơn giá và kho được giữ nguyên.')!=QMessageBox.Yes:return
        self.mutate_receipt('supplier',[r for r,_ in rows],supplier_name=name)

    def delete_selected_row(self):
        index=self.table.currentIndex();sheet=self.receipts.currentData()
        if self.saving or not index.isValid() or not sheet:return
        row=self.model.source_row(index.row());rows=self.data[sheet]
        if len(rows)<=1:self.page.feedback('Không xóa dòng cuối cùng của phiếu.','error');return
        if QMessageBox.question(self,'Xóa dòng',f'Xóa dòng {row-1} khỏi phiếu? Báo cáo được sao lưu trước khi xóa.')!=QMessageBox.Yes:return
        self.mutate_receipt('delete',[row])

    def delete_receipt(self):
        sheet=self.receipts.currentData()
        if self.saving or not self.isEnabled() or not self.report or not sheet:return
        rows=self.data.get(sheet,[]);images=invoice_pages(sheet,rows,self.images)
        text=f'Xóa toàn bộ phiếu {self.receipts.currentText()}?\n{len(rows)} dòng sẽ được gỡ khỏi công nợ. Ảnh gốc và bản sao lưu được giữ.'
        if QMessageBox.question(self,'Xác nhận xóa phiếu công nợ',text)!=QMessageBox.Yes:return
        # Do not exclude an image still referenced by another retained receipt.
        shared={str(p) for name,rs in self.data.items() if name!=sheet for p in invoice_pages(name,rs,self.images)}
        excluded=[p for p in images if str(p) not in shared]
        if QMessageBox.question(self,'Xóa phiếu công nợ',f'Xóa toàn bộ {len(rows)} dòng của phiếu:\n{self.receipts.currentText()}?\nẢnh gốc và bản sao lưu được giữ; tổng NCC sẽ được tính lại.')!=QMessageBox.Yes:return
        from rec_remove_receipt import remove
        report,expected,day=self.report,self.expected,self.day
        task=Worker(remove,report,expected,sheet,excluded,allow_no_images=True)
        self.set_busy(True,'Đang xóa phiếu công nợ…')
        def done(backup):
            self.load_day(day)
            for job in self.page.jobs:
                if job['day']==day.isoformat():
                    job['receipts']=len(self.data);job['rows']=sum(len(rs) for rs in self.data.values());job['result']=f"{job['receipts']} phiếu · {job['rows']} dòng"
            self.page.persist();self.page.feedback('Đã xóa phiếu công nợ. Ảnh gốc và bản sao lưu được giữ.','success')
        task.signals.result.connect(done);task.signals.error.connect(lambda message:self.page.feedback('Chưa xóa được: '+message,'error'))
        task.signals.finished.connect(lambda:self.set_busy(False));self._start_worker(task)
