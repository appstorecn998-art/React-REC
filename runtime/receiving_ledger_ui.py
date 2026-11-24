from receiving_image_archive import image_name, source_digest
"""Dialogs for the local ledger; no API calls or spreadsheet writes."""
import json
from fractions import Fraction
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QDialogButtonBox,QTableWidget,QTableWidgetItem,
    QListWidget,QListWidgetItem,QSplitter,QAbstractItemView,QMessageBox,QInputDialog,QTabWidget,QPushButton,QComboBox,QCheckBox,QWidget)
from receiving_service import digest,invoice_images,sheet_signature,snapshot,accounting_root,atomic_json
import receiving_ledger as ledger
from fluent_blue import Button,Select,Checkbox

class LedgerUI:
    def ledger_path(self):
        return accounting_root(self.destination)/'.receiving'/'receiving-ledger.sqlite'

    def record_ledger(self,items,rows,images,links,conversions=None,on_recorded=None):
        try:
            from rec_department_guard import require_departments
            require_departments(rows)
            if digest(self.report)!=self.source_hash:raise ValueError('Excel đã đổi. Tải lại và xác nhận lại phiếu.')
            if rows!=self.data_by_sheet.get(self.current_sheet):raise ValueError('Phiếu đã đổi. Mở lại đối chiếu.')
            from receiving_pr_image_identity import same_pr_images
            if not same_pr_images(images,self.receipt_references()):raise ValueError('PR đã đổi. Mở lại đối chiếu.')
            from receiving_pr import compare
            from rec_pr_review import eligible
            checked=compare(items,rows,links,conversions)
            if not eligible(checked):raise ValueError('Còn cảnh báo hoặc dòng chưa ghép; hoàn tất xử lý trước khi ghi sổ.')
            effective=dict(links)
            for result in compare(items,rows,links,conversions):
                if 'pr_index' in result and result.get('row') is not None:effective.setdefault(result['pr_index'],result['row'])
            lines=ledger.order_lines(items,conversions);alloc=ledger.allocations(items,rows,effective,conversions)
            corrections=[r for r in compare(items,rows,links,conversions) if 'receipt_correction' in r.get('alerts',[])]
            if corrections:
                message='\n'.join(str(r['name'])+': '+str(r['status']) for r in corrections)
                if QMessageBox.warning(self,'Thực nhận đã xác nhận, tiền còn cần rà',message+'\n\nChỉ ghi số thực nhận; lượng PR vẫn giữ nguyên và không xác nhận đúng thanh toán. Tiếp tục?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return

            refs=invoice_images(self.current_sheet,rows)
            source_images={str(p):digest(p) for p in self.images if image_name(p) in refs}
            if not source_images:raise ValueError('Thiếu ảnh nguồn của lần nhận.')
            from receiving_document_identity import receipt_identity
            from receiving_pr_library import identity
            rid=receipt_identity([Path(p) for p in source_images],self.ledger_path())
            pr_identity=identity(images,self.pr_library_directory())
            oid=ledger.resolve_order(self.ledger_path(),pr_identity)
            path=self.ledger_path();orders=ledger.list_orders(path)
            from receiving_pr_number_identity import check_new_order
            check_new_order(self.pr_library_directory(),path,pr_identity,oid,orders,lines)
            choices=['Theo bộ ảnh PR hiện tại (tạo hoặc cập nhật đúng PR này)']+[f'{title} · {key[:8]}' for key,title,_ in orders]
            choice,ok=(choices[0],True)
            if any(key!=oid and existing==lines for key,_,existing in orders):choice,ok=QInputDialog.getItem(self,'Ghi sổ hàng thiếu / giao bù','Ghi lần nhận này vào PR nào?\nNếu chụp lại cùng PR bằng ảnh khác, chọn đúng PR đã theo dõi bên dưới.',choices,0,False)
            if not ok:return
            references=sorted({str(item.get('pr_reference_id') or '').strip() for item in items}-{''})
            title=('PR '+', '.join(references)+' · ' if references else '')+', '.join(p.name for p in images)
            from receiving_pr_library import load, title as pr_title
            record=load(self.pr_library_directory()).get(oid)
            if record:title=pr_title(record)
            if choice!=choices[0]:
                oid,title,existing=orders[choices.index(choice)-1]
                if existing!=lines:raise ValueError('Các dòng PR không giống PR đã chọn (tên/lượng/đơn vị/giá/thứ tự). Không tự cộng chung; cần rà lại ảnh PR.')
            from receiving_cumulative import context,apply as cumulative_view
            totals,uncertain,count=context(path,oid,rid,lambda value:self._ledger_valid(value,{}))
            if not eligible(cumulative_view(compare(items,rows,links,conversions),totals,uncertain,count)):
                raise ValueError('Tổng nhận hoặc duyệt nhận dư đã đổi; mở lại đối chiếu trước khi ghi sổ.')
            revision=ledger.receipt_revision(path,rid)
            payload={'pr_identity':pr_identity,'day':self.day.isoformat(),'sheet':self.current_sheet,'report':str(self.report),
                'supplier_name':' / '.join(sorted({str(v.get('Nhà cung cấp') or '').strip() for _,v in rows if v.get('Nhà cung cấp')})) or 'Chưa xác định nhà cung cấp',
                'signature':sheet_signature(self.current_sheet,rows),'source_rows':json.loads(json.dumps(rows,default=str)),'reviews_path':str(self.folder/'reviewed.json'),
                'source_images':source_images,'pr_images':{str(p):digest(p) for p in images},'allocations':alloc,'allocation_rows':{str(i):row for i,row in effective.items()},'conversions':conversions or {},'no_topup_items':items}
            from receiving_price_approval import audit
            audit(self.reference_link_path().with_suffix('.comparison.json'),conversions or {})
            from receiving_link_memory import remember
            remember(self.root,items,rows,links,'Gán tay trước xác nhận ghi sổ')
            payload['pr_link_path']=str(self.reference_link_path());payload['pr_link_hash']=digest(self.reference_link_path())
            warnings=ledger.receipt_warnings(path,oid,lines,rid,payload)
            if warnings and QMessageBox.warning(self,'Cảnh báo ghi trùng hoặc nhận vượt lượng đặt','\n'.join(warnings)+'\n\nBạn đã kiểm tra đây là lần nhận thật, khác lần trước và vẫn muốn ghi?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            expected_comparison=json.dumps([items,links,conversions],sort_keys=True,default=str)
            expected_sheet=self.current_sheet
            def commit():
                check_new_order(self.pr_library_directory(),path,pr_identity,oid,ledger.list_orders(path),lines)
                if self.current_sheet!=expected_sheet or json.dumps([items,links,conversions],sort_keys=True,default=str)!=expected_comparison:raise ValueError('Đối chiếu đã thay đổi. Mở lại trước khi ghi.')
                if digest(self.report)!=self.source_hash or rows!=self.data_by_sheet.get(self.current_sheet) or any(not Path(name).is_file() or digest(name)!=key for name,key in {**source_images,**payload['pr_images']}.items()) or digest(self.reference_link_path())!=payload['pr_link_hash']:
                    raise ValueError('Nguồn đã đổi trong lúc duyệt. Mở lại và kiểm tra.')
                reviews=dict(self.reviews);reviews[self.current_sheet]=payload['signature']
                atomic_json(self.folder/'reviewed.json',reviews);self.reviews=reviews
                if not self._ledger_valid(payload,{}):raise ValueError('Không xác minh được nguồn đã duyệt.')
                atomic_json(self.reference_link_path().with_suffix('.comparison.json'),json.loads(json.dumps({'version':1,'signature':payload['signature'],'images':{image_name(p):source_digest(p) for p in images},'links':links,'conversions':conversions or {},'pr_items':items,'results':compare(items,rows,links,conversions)},default=str)))
                ledger.save_receipt(path,oid,title,lines,rid,payload,revision,acknowledged=warnings)
                from rec_pr_review import review_record,marker_path
                from datetime import datetime,timezone
                comparison_path=self.reference_link_path().with_suffix('.comparison.json')
                saved=json.loads(comparison_path.read_text(encoding='utf-8'))
                try:atomic_json(marker_path(comparison_path),review_record(self,saved,'receipt',datetime.now(timezone.utc).isoformat()))
                except Exception as exc:raise ValueError('Đã ghi sổ nhưng chưa lưu được dấu hoàn tất rà. Không ghi thêm lần nhận; mở lại để cập nhật. '+str(exc))
                if on_recorded:on_recorded()
                self.review_label.setText('Đã kiểm tra');self.approve_button.setText('Bỏ xác nhận')
                self.statusBar().showMessage('Đã hoàn tất rà và ghi sổ. Đang đồng bộ Sheets…')
                from rec_auto_sheets import start
                start(self)
            if revision:
                from rec_update_receipt_page import open_page
                def confirmed_update():
                    try:commit();self.show_shortage_ledger()
                    except Exception as exc:raise ValueError(str(exc))
                open_page(self,path,oid,rid,revision,title,lines,payload,confirmed_update)
                return
            if not self.confirm_ledger_receipt(lines,alloc,title,payload['supplier_name'],False):return
            commit()
        except Exception as exc:QMessageBox.warning(self,'Chưa ghi sổ',str(exc))

    def confirm_ledger_receipt(self,lines,alloc,title,supplier,updating):
        from PySide6.QtGui import QColor
        dialog=QDialog(self);dialog.setWindowTitle('Cập nhật lần nhận đã ghi sổ' if updating else 'Xác nhận ghi lần nhận');dialog.resize(1050,650)
        layout=QVBoxLayout(dialog)
        heading=QLabel('Cập nhật lần nhận cũ — không cộng thêm' if updating else 'Xác nhận phiếu, PR và ghi sổ');heading.setObjectName('total');layout.addWidget(heading)
        meta=QLabel(f'{supplier}\n{self.current_sheet} · {self.day:%d/%m/%Y}\n{title}');meta.setWordWrap(True);layout.addWidget(meta)
        note=QLabel('Chỉ thay số liệu của lần nhận đã lưu. Tổng đã nhận không bị cộng hai lần.' if updating else 'Ghi số thực nhận của phiếu này. Phần còn thiếu được giữ để chờ giao bù.');note.setText(note.text()+'\nXác nhận đã kiểm tra tên, mã, ngày, giá, thực nhận và quy đổi. Ghi sổ xong sẽ tự cập nhật Google Sheets.');note.setWordWrap(True);note.setObjectName('rowReview');layout.addWidget(note)
        table=QTableWidget(len(lines),6);table.setObjectName('receiptConfirmation');table.setHorizontalHeaderLabels(['Mặt hàng','Đơn vị','SL đặt','Nhận lần này','Thiếu trong phiếu','Dư trong phiếu'])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setAlternatingRowColors(True);table.verticalHeader().hide();table.setWordWrap(True)
        short=over=0
        for i,line in enumerate(lines):
            qty=Fraction(alloc[str(i)]);remaining=Fraction(line['ordered'])-qty
            short+=remaining>0;over+=remaining<0
            values=[line['name']+((' · PR '+line['requested']+' → duyệt '+line['ordered']) if line.get('purchase_approval') else ''),line['unit'],line['ordered'],ledger.exact_text(qty),ledger.exact_text(max(0,remaining)),ledger.exact_text(max(0,-remaining))]
            for j,value in enumerate(values):
                cell=QTableWidgetItem(str(value));cell.setToolTip(str(value))
                if j>=2:cell.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                if remaining:cell.setBackground(QColor('#fff7ed' if remaining>0 else '#faf5ff'))
                table.setItem(i,j,cell)
        summary=QLabel(f'{len(lines)} mặt hàng · Thiếu: {short} · Dư: {over} · Đủ: {len(lines)-short-over} (trong phiếu này)');summary.setObjectName('section');layout.addWidget(summary)
        layout.addWidget(table,1)
        for j,width in enumerate([360,80,100,120,140,140]):table.setColumnWidth(j,width)
        table.resizeRowsToContents();table.horizontalHeader().setStretchLastSection(True)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Xác nhận cập nhật và đồng bộ' if updating else 'Xác nhận và ghi sổ');buttons.button(QDialogButtonBox.Save).setObjectName('primary')
        buttons.button(QDialogButtonBox.Cancel).setText('Hủy');buttons.button(QDialogButtonBox.Cancel).setDefault(True)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        return dialog.exec()==QDialog.Accepted

    def _ledger_valid(self,p,cache):
        from receiving_validation import check
        if getattr(self,'portable_workspace',False):
            from rec_workspaces import ledger_source
            p=ledger_source(self.destination)(p)
        return check(p,cache)

    def show_shortage_ledger(self):
        self.ledger_ready=False
        if self.busy:return
        if getattr(self,'ledger_page',None) is not None and self.ledger_page_path==self.ledger_path():
            try:self.ledger_refresh()
            except Exception as exc:QMessageBox.warning(self,'Chưa tải được sổ',str(exc));return
            self.main_pages.setCurrentWidget(self.ledger_page);self.fluent_nav.blockSignals(True);self.fluent_nav.set_current('Sổ nhận hàng');self.fluent_nav.blockSignals(False);self.ledger_ready=True;return
        if getattr(self,'ledger_page',None) is not None:
            self.main_pages.removeWidget(self.ledger_page);self.ledger_page.deleteLater()
        dialog=QWidget();dialog.setObjectName('ledgerPage')
        self.ledger_page=dialog;self.ledger_page_path=self.ledger_path()
        self.main_pages.addWidget(dialog)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(22,18,22,14);layout.setSpacing(12)
        heading=QLabel('Sổ nhận hàng');heading.setObjectName('total');layout.addWidget(heading)
        note=QLabel('Tra cứu phiếu nhận, theo dõi giao bù và kiểm tra các phiếu cần xử lý. Bấm đúp một phiếu để mở lại.');note.setWordWrap(True);layout.addWidget(note)
        overview=QLabel();overview.setObjectName('receivingOverview');overview.setWordWrap(True)
        overview.setStyleSheet('padding:12px; background:#edf5ff; color:#184579; border-radius:8px; font-weight:600;')
        layout.addWidget(overview)
        tabs=QTabWidget();layout.addWidget(tabs,1)
        all_page=QWidget();all_layout=QVBoxLayout(all_page);all_controls=QHBoxLayout()
        from fluent_blue import Input
        search=Input();search.setPlaceholderText('Tìm NCC, tên phiếu hoặc ngày YYYY-MM-DD');all_controls.addWidget(search,1)
        date_from=Input();date_from.setMaximumWidth(185);date_from.setPlaceholderText('Từ ngày YYYY-MM-DD');all_controls.addWidget(date_from)
        date_to=Input();date_to.setMaximumWidth(185);date_to.setPlaceholderText('Đến ngày YYYY-MM-DD');all_controls.addWidget(date_to)
        register_mode=Select()
        for label,value in [('Tất cả trạng thái','all'),('Chưa ghi sổ','unposted'),('Không có PR/PO','no_po'),('Đã ghi sổ','posted'),('Cần kiểm tra lại','invalid')]:register_mode.addItem(label,value)
        all_controls.addWidget(register_mode);all_layout.addLayout(all_controls)
        register_table=QTableWidget();register_table.setObjectName('allReceivingReceipts');all_layout.addWidget(register_table,1)
        register_note=QLabel();all_layout.addWidget(register_note);tabs.addTab(all_page,'Tất cả phiếu')
        action_needed=QWidget();action_layout=QVBoxLayout(action_needed);action_table=QTableWidget();action_table.setObjectName('receivingActionNeeded');action_layout.addWidget(action_table)

        page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(0,0,0,0)
        filters=QHBoxLayout();filters.addWidget(QLabel('Nhà cung cấp:'))
        supplier_choice=Select();supplier_choice.setObjectName('ledgerSupplier');filters.addWidget(supplier_choice,1)
        order_choice=Select();order_choice.setObjectName('ledgerOrderFilter');order_choice.hide()
        show_complete=Checkbox('Hiện PR đã hoàn tất');filters.addWidget(show_complete);page_layout.addLayout(filters)
        item_filter=Select();item_filter.setObjectName('ledgerItemFilter')
        for text,key in [('Tất cả mặt hàng','all'),('Chỉ còn thiếu','short'),('Đã nhận đủ','complete'),('Nhận dư','over'),('Cần kiểm tra','unknown')]:item_filter.addItem(text,key)
        filters.addWidget(item_filter)
        group_summary=QLabel();group_summary.setObjectName('section');group_summary.setWordWrap(True);page_layout.addWidget(group_summary)
        totals=QTableWidget();totals.setObjectName('ledgerShortages')
        split=QSplitter(Qt.Horizontal);order_list=QListWidget();order_list.setObjectName('ledgerOrderList');order_list.setWordWrap(True);order_list.setSpacing(6);order_list.setMinimumWidth(210);order_list.setMaximumWidth(340);split.addWidget(order_list);split.addWidget(totals);split.setSizes([270,1000]);page_layout.addWidget(split,1)
        history=QTableWidget();history.setObjectName('ledgerReceipts');tabs.addTab(page,'Chờ giao bù');tabs.addTab(action_needed,'Cần xử lý');history_page=QWidget();history.setParent(history_page);history.hide();tabs.addTab(history_page,'Lịch sử giao hàng')
        complete_page=QWidget();tabs.insertTab(2,complete_page,'Đã nhận đủ')
        def populate(table,headers,rows):
            table.setUpdatesEnabled(False);table.blockSignals(True)
            table.clear();table.setColumnCount(len(headers));table.setHorizontalHeaderLabels(headers);table.setRowCount(len(rows))
            table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection);table.setAlternatingRowColors(True);table.setShowGrid(False);table.verticalHeader().hide()
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            for i,row in enumerate(rows):
                for j,value in enumerate(row):table.setItem(i,j,QTableWidgetItem('Chưa đủ dữ liệu' if value is None else str(value)))
            table.setWordWrap(True)
            # Fixed widths avoid measuring every cell on each keystroke.
            for col in range(len(headers)):table.setColumnWidth(col,180)
            for col in range(len(headers)):table.setColumnWidth(col,min(320,max(100,table.columnWidth(col))))
            table.horizontalHeader().setStretchLastSection(True);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            table.verticalHeader().setDefaultSectionSize(56)
            for i in range(table.rowCount()):
                table.setRowHeight(i,56)
                for j in range(table.columnCount()):table.item(i,j).setToolTip(table.item(i,j).text())
            table.blockSignals(False);table.setUpdatesEnabled(True)
        all_records=[];register_visible=[];action_visible=[]
        records=[];summary_rows=[];visible_rows=[];supplier_by_order={};order_catalog={}
        def display_group():
            nonlocal visible_rows
            supplier=supplier_choice.currentText()
            selected=order_choice.currentData()
            group=[r for r in summary_rows if supplier_by_order.get(r['order_id'])==supplier and selected is not None and r['order_id']==selected]
            mode=item_filter.currentData()
            def matches(r):
                q=None if r['remaining'] is None else Fraction(r['remaining'])
                return mode=='stopped' and r.get('item_stopped') or mode=='all' or mode=='short' and q is not None and q>0 or mode=='complete' and q==0 or mode=='over' and q is not None and q<0 or mode=='unknown' and q is None
            visible_rows=[r for r in group if matches(r)]
            short=sum(r['remaining'] is not None and Fraction(r['remaining'])>0 for r in group)
            over=sum(r['remaining'] is not None and Fraction(r['remaining'])<0 for r in group)
            unknown=sum(r['remaining'] is None for r in group)
            group_summary.setText(f'{order_choice.currentText()} · Thiếu: {short} mặt hàng · Dư: {over} mặt hàng · Cần kiểm tra lại: {unknown}'+(' · Không có hàng thiếu/dư.' if not visible_rows else ''))
            populate(totals,['Mặt hàng','Đơn vị','SL đặt','Tổng đã nhận','Còn thiếu','Nhận dư','PR','Trạng thái / lý do'],[(r['name'],r['unit'],r['ordered'],(r['received'] if r['remaining'] is not None else 'Đã ghi '+r.get('recorded_received',r['received'])+'; đang xác minh'),None if r['remaining'] is None else ledger.exact_text(max(0,Fraction(r['remaining']))) if Fraction(r['remaining'])>=0 else '0', None if r['remaining'] is None else ledger.exact_text(-Fraction(r['remaining'])) if Fraction(r['remaining'])<0 else '0',__import__('receiving_ledger_display').short_order(r['title'],r['order_id']),r['status']+(' · '+r['reason'] if r['reason'] else '')) for r in visible_rows])
            totals.horizontalHeader().moveSection(totals.horizontalHeader().visualIndex(6),0)
            totals.setColumnWidth(0,280);totals.setColumnHidden(6,True)
            from PySide6.QtGui import QColor
            for i,r in enumerate(visible_rows):
                q=None if r['remaining'] is None else Fraction(r['remaining'])
                bg,fg=('#fff7d6','#854d0e') if q is None else ('#fff0df','#9a3412') if q>0 else ('#f5eaff','#7e22ce') if q<0 else ('#edf9ee','#166534')
                for j in range(totals.columnCount()):totals.item(i,j).setBackground(QColor(bg))
                for j in (4,7):
                    totals.item(i,j).setForeground(QColor(fg));font=totals.item(i,j).font();font.setBold(True);totals.item(i,j).setFont(font)
            if hasattr(dialog,'render_shortage'):dialog.render_shortage(visible_rows,group)
        def in_scope(r):
            mode=item_filter.currentData();q=None if r['remaining'] is None else Fraction(r['remaining'])
            return mode=='stopped' and r.get('item_stopped') or mode=='all' or mode=='unknown' and q is None or mode=='short' and q is not None and q>0 or mode=='complete' and q==0 or mode=='over' and q is not None and q<0
        def filter_orders():
            previous=order_choice.currentData();order_choice.blockSignals(True);order_list.blockSignals(True);order_choice.clear();order_list.clear()
            for oid,title,lines in order_catalog.values():
                if supplier_by_order.get(oid)!=supplier_choice.currentText():continue
                group=[r for r in summary_rows if r['order_id']==oid]
                if not any(in_scope(r) for r in group):continue
                if tabs.currentWidget() is complete_page and any(r['remaining'] is None or Fraction(r['remaining'])!=0 or r.get('reason') for r in group):continue
                if not show_complete.isChecked() and item_filter.currentData()!='stopped' and not any(r['remaining'] is None or Fraction(r['remaining'])!=0 for r in group):continue
                from receiving_ledger_display import short_order
                order_choice.addItem(short_order(title,oid),oid)
                missing=sum(r['remaining'] is not None and Fraction(r['remaining'])>0 for r in group)
                unclear=sum(r['remaining'] is None for r in group)
                extra=sum(r['remaining'] is not None and Fraction(r['remaining'])<0 for r in group)
                status=('Cần rà '+str(unclear)+' món') if unclear else ('Còn thiếu '+str(missing)+' món') if missing else ('Nhận dư '+str(extra)+' món') if extra else '✓ Đã hoàn tất'
                count=sum(p['active'] and p['order_id']==oid for p in records)
                item=QListWidgetItem(short_order(title,oid)+'\n'+status+' · '+str(len(group))+' món\n'+str(count)+' lần giao');item.setData(Qt.UserRole,oid);item.setToolTip(title);item.setSizeHint(__import__('PySide6.QtCore',fromlist=['QSize']).QSize(240,84));order_list.addItem(item)
                from PySide6.QtGui import QColor
                item.setForeground(QColor('#854d0e' if unclear else '#9a3412' if missing else '#7e22ce' if extra else '#166534'))
                item.setBackground(QColor('#fff7d6' if unclear else '#fff0df' if missing else '#f5eaff' if extra else '#edf9ee'))
            index=order_choice.findData(previous)
            index=index if index>=0 else 0
            order_choice.setCurrentIndex(index);order_list.setCurrentRow(index)
            order_list.blockSignals(False);order_choice.blockSignals(False);display_group()
        def filter_suppliers():
            previous=supplier_choice.currentText()
            eligible={supplier_by_order[r['order_id']] for r in summary_rows if in_scope(r) and (show_complete.isChecked() or item_filter.currentData()=='stopped' and r.get('item_stopped') or r['remaining'] is None or Fraction(r['remaining'])!=0)}
            supplier_choice.blockSignals(True);supplier_choice.clear();supplier_choice.addItems(sorted(eligible))
            restore_index=supplier_choice.findText(previous)
            if restore_index>=0:supplier_choice.setCurrentIndex(restore_index)
            supplier_choice.setEnabled(bool(eligible));supplier_choice.blockSignals(False)
            filter_orders()
            if not eligible:group_summary.setText('Không có nhà cung cấp còn hàng thiếu, dư hoặc cần kiểm tra lại.' if not show_complete.isChecked() else 'Chưa có lần nhận nào trong sổ.')
        item_filter.addItem('Đã ngừng giao bù','stopped')
        order_list.currentRowChanged.connect(lambda i:order_choice.setCurrentIndex(i));supplier_choice.currentIndexChanged.connect(filter_orders);order_choice.currentIndexChanged.connect(display_group);show_complete.toggled.connect(filter_suppliers);item_filter.currentIndexChanged.connect(filter_suppliers)
        def filter_register():
            nonlocal register_visible,action_visible
            from rec_register_layout import search_text,parse_date
            q=search.text().strip().casefold();start=parse_date(date_from.text());end=parse_date(date_to.text());mode=register_mode.currentData()
            register_visible=[r for r in all_records if (not q or q in search_text(r,order_catalog)) and (not start or r['day']>=start) and (not end or r['day']<=end) and (mode=='all' or mode=='attention' and r['status'] in ('Chưa ghi sổ','Cần kiểm tra lại') or mode=='unposted' and r['status']=='Chưa ghi sổ' or mode=='posted' and r['status']=='Đã ghi sổ' or mode=='invalid' and r['status']=='Cần kiểm tra lại' or mode=='no_po' and r['status']=='Không có PR/PO')]
            action_visible=[r for r in all_records if r['status'] in ('Chưa ghi sổ','Cần kiểm tra lại')]
            for table,values in [(register_table,register_visible),(action_table,action_visible)]:
                populate(table,['Ngày nhận','Nhà cung cấp','Phiếu','Số món','Trạng thái'],[(r['day'],r['supplier'],r['sheet'],r['count'],r['status']) for r in values])
                table.setColumnWidth(0,120);table.setColumnWidth(1,300);table.setColumnWidth(2,250)
            from PySide6.QtGui import QColor
            colors={'Đã ghi sổ':('#edf9ee','#166534'),'Không có PR/PO':('#edf5ff','#184579'),'Chưa ghi sổ':('#fff0df','#9a3412'),'Cần kiểm tra lại':('#fff7d6','#854d0e')}
            for table,values in [(register_table,register_visible),(action_table,action_visible)]:
                for i,r in enumerate(values):
                    cell=table.item(i,4);bg,fg=colors[r['status']];cell.setBackground(QColor(bg));cell.setForeground(QColor(fg));font=cell.font();font.setBold(True);cell.setFont(font)
            counts={status:sum(r['status']==status for r in all_records) for status in colors}
            overview.setText(f"{len(all_records)} phiếu nhận    •    {counts['Đã ghi sổ']} đã ghi sổ    •    {counts['Không có PR/PO']} không PR/PO    •    {len(action_visible)} cần xử lý")
            register_note.setText(str(len(register_visible))+' phiếu phù hợp · Không PR/PO: theo dõi thủ công. Chưa ghi sổ không đồng nghĩa chưa nhận hàng.')
            tabs.setTabText(tabs.indexOf(all_page),'Tất cả phiếu ('+str(len(all_records))+')');tabs.setTabText(tabs.indexOf(action_needed),'Cần xử lý ('+str(len(action_visible))+')')
            if hasattr(dialog,'render_register'):dialog.render_register(register_visible,order_catalog)
        from PySide6.QtCore import QTimer
        filter_timer=QTimer(dialog);filter_timer.setSingleShot(True);filter_timer.setInterval(220);filter_timer.timeout.connect(filter_register)
        search.textChanged.connect(lambda *_:filter_timer.start());date_from.textChanged.connect(lambda *_:filter_timer.start());date_to.textChanged.connect(lambda *_:filter_timer.start());register_mode.currentIndexChanged.connect(filter_register)
        def switch_register_tab(index):
            current=tabs.widget(index)
            if current is page:
                filter_suppliers()
        tabs.currentChanged.connect(switch_register_tab)
        loading=[False]
        def refresh():
            if loading[0]:return
            loading[0]=True;dialog.setEnabled(False)
            overview.setText('Đang tải và xác minh phiếu nhận… Bạn có thể chuyển sang mục khác.')
            if hasattr(dialog,'register_load_state'):dialog.register_load_state('Đang tải và xác minh phiếu nhận…')
            from receiving_qt import Worker
            from receiving_ledger_loader import load
            job=Worker(load,self.ledger_path(),accounting_root(self.destination),getattr(self,'portable_workspace',False))
            def ready(data):
                if getattr(self,'ledger_page',None) is not dialog:return
                apply_snapshot(data)
                callback=getattr(dialog,'item_closure_refresh_done',None)
                if callback:
                    dialog.item_closure_refresh_done=None;callback()
            def failed(message):
                if getattr(self,'ledger_page',None) is dialog:
                    callback=getattr(dialog,'item_closure_refresh_done',None)
                    if callback:
                        dialog.item_closure_refresh_done=None
                        self.show_top_notice('Quyết định đã lưu, bảng chưa làm mới',message)
                    overview.setText('Chưa tải được sổ: '+message+' · Mở lại Sổ nhận hàng để thử lại.')
                    if hasattr(dialog,'register_load_state'):dialog.register_load_state(overview.text())
            def finished():
                loading[0]=False
                if getattr(self,'ledger_page',None) is dialog:dialog.setEnabled(True)
            job.signals.result.connect(ready);job.signals.error.connect(failed);job.signals.finished.connect(finished)
            self._start_worker(job)
        def apply_snapshot(data):
            nonlocal records,summary_rows,all_records
            catalog,summary_rows,records,suppliers,all_records=data
            order_catalog.clear();order_catalog.update(catalog)
            supplier_by_order.clear();supplier_by_order.update(suppliers)
            filter_register();filter_suppliers()
            records.sort(key=lambda p:(p['day'],p['sheet']),reverse=True)
            if hasattr(dialog,'render_complete'):dialog.render_complete(summary_rows,order_catalog,supplier_by_order,records)
            from receiving_ledger_display import received_items,short_order
            entries=[]
            for receipt in records:
                oid=receipt['order_id'];_,title,lines=order_catalog.get(oid,(oid,'PR chưa rõ',[]))
                products=received_items(receipt,lines)
                description='; '.join(name+' — '+quantity+' '+unit for name,quantity,unit in products[:3])
                if len(products)>3:description+='; và '+str(len(products)-3)+' món khác'
                entries.append((receipt['day'],receipt['supplier_name'] if receipt.get('supplier_name') else supplier_by_order.get(oid,''),short_order(title,oid),receipt['sheet'],str(len(products))+' món','Đã ghi nhận' if receipt['active'] and receipt['valid'] else 'Cần kiểm tra lại' if receipt['active'] else 'Đã gỡ',description or 'Không nhận thêm hàng'))
            populate(history,['Ngày nhận','Nhà cung cấp','Thuộc PR','Phiếu giao','Hàng nhận lần này','Trạng thái','Món đã nhận'],entries)
            history.setColumnWidth(0,110);history.setColumnWidth(1,180);history.setColumnWidth(2,190);history.setColumnWidth(3,170);history.setColumnWidth(4,130);history.setColumnWidth(5,150)
            for i,p in enumerate(records):
                history.item(i,3).setToolTip('Nguồn: '+p['report']+'\nBấm đúp để xem chi tiết và mở phiếu')
            if hasattr(dialog,'render_history'):dialog.render_history(records,order_catalog)

        QTimer.singleShot(0,refresh)
        inspect_button=Button('Xem chi tiết / mở phiếu');inspect_button.setObjectName('inspectLedgerReceipt')
        def inspect_selected():
            candidates=[]
            if tabs.currentWidget() in (all_page,action_needed):
                table,values=(register_table,register_visible) if tabs.currentWidget() is all_page else (action_table,action_visible)
                i=table.currentRow()
                if not 0<=i<len(values):return
                entry=values[i]
                if not self._leave_pr():return
                try:
                    from datetime import date
                    from PySide6.QtCore import QDate
                    from receiving_service import day_images
                    from receiving_service import paths
                    day=date.fromisoformat(entry['day']);folder,local=paths(self.root,day,self.destination)
                    report=Path(entry['report'])
                    if getattr(self,'portable_workspace',False) and not report.resolve().is_relative_to(self.destination.resolve()):
                        if local.name!=report.name or not local.is_file():
                            raise ValueError('Phiếu nguồn chưa có trong dữ liệu React REC.')
                        report=local
                    h,data=snapshot(report)
                    reviews=json.loads((folder/'reviewed.json').read_text(encoding='utf-8')) if (folder/'reviewed.json').exists() else {}
                    self.day=day;self.date_edit.blockSignals(True);self.date_edit.setDate(QDate(day.year,day.month,day.day));self.date_edit.blockSignals(False)
                    self._day_loaded((folder,report,h,data,day_images(report.parent),{n:sheet_signature(n,r) for n,r in data},reviews));self.select_sheet(entry['sheet']);self.main_pages.setCurrentWidget(self.receipt_page)
                    self.fluent_nav.set_current('Kiểm tra phiếu')
                except (OSError,ValueError,KeyError) as exc:QMessageBox.warning(dialog,'Chưa mở được phiếu',str(exc))
                return

            if tabs.currentWidget() is history_page:
                index=history.currentRow()
                if 0<=index<len(records):candidates=[records[index]]
            else:
                index=totals.currentRow()
                if 0<=index<len(visible_rows):
                    selected=visible_rows[index];oid=selected['order_id'];line=str(selected['index'])
                    all_receipts=[p for p in records if p['order_id']==oid and p['active']]
                    candidates=[p for p in all_receipts if Fraction(p.get('allocations',{}).get(line,'0'))>0]
                    if not candidates:
                        QMessageBox.information(dialog,'Chưa có lần nhận của món này','Mặt hàng đang chọn chưa có lần nhận với lượng dương.');return
            if not candidates:
                QMessageBox.information(dialog,'Chọn lần nhận hoặc PR','Chọn một dòng trong Các lần nhận hoặc PR trong Thiếu / dư.');return
            if len(candidates)>1:
                options=[p['day']+' · '+p['sheet']+(' · Cần kiểm tra' if not p['valid'] else ' · Hợp lệ') for p in candidates]
                choice,ok=QInputDialog.getItem(dialog,'Kiểm tra lần nhận','Chọn lần nhận cần kiểm tra:',options,0,False)
                if not ok:return
                payload=candidates[options.index(choice)]
            else:payload=candidates[0]
            from rec_receipt_source_page import show as show_source
            show_source(self,payload)
        inspect_button.clicked.connect(inspect_selected)
        register_table.cellDoubleClicked.connect(lambda *_:inspect_selected());action_table.cellDoubleClicked.connect(lambda *_:inspect_selected())
        history.cellDoubleClicked.connect(lambda *_:inspect_selected())
        totals.cellClicked.connect(lambda *_:inspect_selected())
        remove=Button('Gỡ lần nhận đã chọn…')
        def revoke():
            index=history.currentRow()
            if index<0 or tabs.currentWidget()!=history_page:
                QMessageBox.information(dialog,'Chọn lần nhận','Mở Các lần nhận và chọn dòng cần gỡ.');return
            p=records[index]
            from rec_revoke_receipt_page import open_page
            open_page(self,p,lambda changed:None)
        remove.clicked.connect(revoke)
        cancel=Button('Ngừng chờ giao bù…')
        def close(expected=None):
            index=totals.currentRow()
            if index<0 or tabs.currentWidget() not in (page,complete_page):
                QMessageBox.information(dialog,'Chọn PR','Chọn nhà cung cấp và mặt hàng thuộc PR cần xử lý. Bật Hiện cả hàng đã đủ / đã hủy để mở lại PR đã hủy.');return
            row=visible_rows[index];same=[r for r in summary_rows if r['order_id']==row['order_id']]
            if any(r['remaining'] is None for r in same):
                QMessageBox.warning(dialog,'Cần kiểm tra lại phiếu','Cập nhật các lần nhận có nguồn đã đổi trước khi chốt hủy.');return
            reopen=bool(row['reason'])
            if expected is not None and reopen!=expected:
                QMessageBox.information(dialog,'Trạng thái PR','Chọn PR đã ngừng nhận để mở lại.' if expected else 'PR này đã ngừng nhận. Bấm Mở lại PR nếu cần.');return
            if reopen:
                from rec_reopen_order_page import open_page
                open_page(self,row['order_id'],order_choice.currentText(),same);return
            reason,ok=QInputDialog.getText(dialog,'Mở lại PR' if reopen else 'Bộ phận báo hủy','Nhập bộ phận/người báo và lý do:')
            if not ok:return
            message=('Mở lại để tiếp tục theo dõi giao bù?' if reopen else 'Ngừng theo dõi giao bù TOÀN BỘ phần chưa nhận của PR này? Chỉ dùng khi bộ phận đã báo không nhận tiếp. Các lượng đã nhận giữ nguyên.')
            if QMessageBox.question(dialog,'Xác nhận',message)!=QMessageBox.Yes:return
            try:ledger.close_order(self.ledger_path(),row['order_id'],reason,reopen);refresh();__import__('rec_auto_sheets').start(self)
            except Exception as exc:QMessageBox.warning(dialog,'Chưa cập nhật',str(exc))
        cancel.clicked.connect(lambda:close(False))
        reopen_button=Button('Mở lại PR');reopen_button.clicked.connect(lambda:close(True))
        sync=Button('Xem trước cập nhật Google Sheets')
        sync.setToolTip('Đọc bảng trực tuyến và xem các dòng hàng thiếu sẽ thêm/cập nhật. Chưa ghi dữ liệu cho đến khi bạn xác nhận.')
        sync.clicked.connect(lambda:__import__('rec_sheets_page').show_page(self,load=True))
        audit_button=Button('Rà soát toàn bộ dữ liệu nhận hàng')
        def audit_all():
            from rec_audit_page import show
            show(self)
        audit_button.clicked.connect(audit_all)
        footer=QHBoxLayout();footer.addWidget(audit_button);footer.addWidget(inspect_button);footer.addWidget(cancel);footer.addWidget(reopen_button);footer.addWidget(remove);footer.addStretch()
        reload_button=Button('Làm mới',icon='refresh');reload_button.clicked.connect(refresh);footer.addWidget(reload_button);layout.addLayout(footer)
        filters.addWidget(sync)
        from rec_register_layout import install as install_register
        install_register(self,dialog,all_page,tabs,register_table,search,date_from,date_to,register_mode,register_note,heading,note,overview,footer,inspect_selected,audit_button)
        from rec_shortage_layout import install as install_shortage
        install_shortage(self,dialog,page,complete_page,tabs,supplier_choice,show_complete,item_filter,order_choice,order_list,totals,group_summary,heading,note,overview,footer,inspect_selected,cancel)
        from rec_history_layout import install as install_history
        install_history(self,dialog,history_page,tabs,history,heading,note,overview,footer,inspect_selected,remove,reopen_button,sync)
        from rec_complete_orders_layout import install as install_complete
        install_complete(self,dialog,complete_page,tabs,heading,note,overview,footer,order_choice,supplier_choice,show_complete,item_filter,totals,inspect_selected)
        self.ledger_ready=True
        self.ledger_refresh=refresh
        self.ledger_snapshot=lambda:(summary_rows,records,dict(supplier_by_order))
        self.main_pages.setCurrentWidget(dialog);self.fluent_nav.blockSignals(True);self.fluent_nav.set_current('Sổ nhận hàng');self.fluent_nav.blockSignals(False)

    def preview_shortages_sheets(self,parent,summary_rows,records,suppliers):
        from receiving_qt import Worker
        from receiving_sheets import SheetsClient,plan,apply,file_signature
        import copy
        local_path=self.ledger_path();local_signature=file_signature(local_path)
        summary_rows=copy.deepcopy(summary_rows);records=copy.deepcopy(records)
        from rec_sync_results_page import read_events
        valid_revisions={p['receipt_id']:p['revision'] for p in records if p['active'] and p['valid']}
        synced_ids=[e['id'] for e in read_events(local_path) if e['state']!='synced' and e['receipt_id'] in valid_revisions and e['revision']<=valid_revisions[e['receipt_id']]]
        def prepare():
            client=SheetsClient(self.root)
            from receiving_department_sheets import preview as plan_departments
            from receiving_pr_library import load
            return client,plan_departments(client,summary_rows,records,suppliers,load(self.pr_library_directory()),progress=job.signals.progress.emit)
        from rec_sheets_page import show_page
        parent=show_page(self);parent.running=True;parent.save.setEnabled(False);parent.reload.setEnabled(False);parent.status.setText('Đang đọc Google Sheets…')
        parent.loading_state.title.setText('Đang đọc Google Sheets');parent.loading_state.description.setText('Đang đối chiếu dữ liệu để tạo bảng xem trước.');parent.loading_state.progress.setRange(0,0);parent.loading_state.progress.show();parent.loading_state.skeleton.show();parent.loading_state.retry.hide();parent.loading_state.show()
        self.set_busy(True,'Đang đọc Google Sheets để xem trước…')
        job=Worker(prepare)
        def ready(result):
            parent.setEnabled(True)
            from rec_sheets_page import show_page
            page=show_page(self);client,preview=result
            page.loading_state.hide()
            page.preview=preview
            page.show_plan(preview)
            page.summary.setText(f"{len(preview['changes'])} thay đổi · {preview['skipped']} dòng chưa đủ điều kiện")
            page.set_sync_progress('Đã đọc Google Sheets. Kiểm tra bảng trước khi xác nhận cập nhật.')
            table=page.table;table.setRowCount(len(preview['changes']))
            for i,c in enumerate(preview['changes']):
                values=[c.get('tab','')+' · '+c['supplier'],c['name'],c['values'][5],c['values'][8],c['values'][10],c['action']]
                for j,value in enumerate(values):
                    cell=QTableWidgetItem(str(value));cell.setToolTip(str(value));table.setItem(i,j,cell)
            table.verticalHeader().setDefaultSectionSize(56)
            for i in range(table.rowCount()):table.setRowHeight(i,max(44,table.rowHeight(i)))
            page.save.setEnabled(bool(preview['changes']) or any(p.get('create') for p in preview.get('parts',[])))
            def submit():
                if not page.save.isEnabled():return
                page.save.setEnabled(False);page.reload.setEnabled(False);page.running=True
                def write():
                    if self.ledger_path()!=local_path or file_signature(local_path)!=local_signature:raise ValueError('Sổ nhận hàng đã thay đổi. Xem trước lại.')
                    cache={}
                    if any(p['active'] and p['valid'] and not self._ledger_valid(p,cache) for p in records):raise ValueError('Phiếu hoặc xác nhận đã thay đổi. Cập nhật sổ và xem trước lại.')
                    from receiving_department_sheets import apply_preview
                    return apply_preview(client,preview,progress=task.signals.progress.emit)
                task=Worker(write);written_ok=[False]
                task.signals.progress.connect(page.set_sync_progress)
                task.signals.result.connect(lambda _:written_ok.__setitem__(0,True))
                def completed(count):
                    ledger.sync_result(local_path,synced_ids)
                    self.sheets_last_status=f'Đã cập nhật {count} dòng Google Sheets.'
                    page.set_sync_progress(self.sheets_last_status)
                    __import__('rec_sync_results_page').show(self,manual_result=self.sheets_last_status)
                task.signals.result.connect(completed)
                task.signals.error.connect(lambda message:(page.status.setText('Chưa xác nhận cập nhật: '+message+' · Bấm Làm mới xem trước để kiểm tra lại.'),__import__('rec_sync_results_page').show(self,manual_result='Chưa đồng bộ: '+message)))
                def written():
                    page.sync_progress.hide()
                    page.running=False;page.reload.setEnabled(True)
                    if getattr(self,'sheets_sync_pending',False):
                        self.sheets_sync_pending=False
                        if written_ok[0]:__import__('rec_auto_sheets').start(self)
                task.signals.finished.connect(written);self._start_worker(task)
            page.submit=submit
        job.signals.progress.connect(parent.set_sync_progress)
        read_ok=[False]
        job.signals.result.connect(lambda _:read_ok.__setitem__(0,True))
        job.signals.result.connect(ready)
        job.signals.error.connect(lambda message:(parent.status.setText('Chưa đọc được Google Sheets: '+message),parent.loading_state.fail('Chưa đọc được Google Sheets: '+message)))
        def finish():
            parent.sync_progress.hide()
            parent.setEnabled(True);parent.reload.setEnabled(True);parent.running=False;self.set_busy(False)
            if getattr(self,'sheets_sync_pending',False):
                self.sheets_sync_pending=False
                if read_ok[0]:__import__('rec_auto_sheets').start(self)
        job.signals.finished.connect(finish);self._start_worker(job)
