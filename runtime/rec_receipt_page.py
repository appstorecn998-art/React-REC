"""Receipt/image review layout with original selection and write services."""
from PySide6.QtCore import Qt,QStringListModel
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QLineEdit,QPushButton,QMenu,QToolButton,QCompleter
from rec_status_ui import COLORS

def install(w):
    # Canonical receipt design has the source beside the table. Receipt picking
    # remains the same authoritative list, exposed by the supplier picker.
    viewer=w.ops_source_dialog;image_panel=w.preview.parentWidget()
    while image_panel.parentWidget() is not viewer and image_panel.parentWidget() is not None:
        image_panel=image_panel.parentWidget()
    image_panel.layout().setContentsMargins(0,0,0,0)
    viewer.layout().removeWidget(image_panel);image_panel.setParent(w.work_split)
    w.work_split.widget(0).setParent(w.receipt_menu)
    w.receipt_menu.layout().addWidget(w.receipt_panel)
    w.receipt_panel.setMinimumWidth(350);w.receipt_panel.setMaximumWidth(520)
    w.work_split.insertWidget(0,image_panel);image_panel.show();w.work_split.setSizes([470,760])
    w.work_split.setStretchFactor(0,2);w.work_split.setStretchFactor(1,3)
    source_error=QLabel();source_error.setWordWrap(True);source_error.hide()
    source_error.setStyleSheet('background:#fff0f2;color:#b3364e;padding:12px;border-radius:8px;')
    image_panel.layout().insertWidget(1,source_error)
    def source_state(message):
        from rec_missing_source import refresh
        refresh(w)
        missing=w.preview.source_path is not None and not w.preview.source_path.is_file()
        failed=missing or (bool(message) and ('không' in message.casefold() or 'lỗi' in message.casefold()) and w.preview.item is None)
        source_error.setText('Không mở được ảnh nguồn. Kiểm tra đường dẫn hoặc khôi phục đúng ảnh rồi tải lại; không dùng ảnh khác để xác nhận phiếu.')
        source_error.setVisible(failed)
    w.preview.previewReady.connect(source_state)
    w.receipt_source_error=source_error
    filters=w.ops_receipt_actions.widget().layout()
    source=w.findChild(QPushButton,'showReceiptSource');source.hide()
    w.receipt_picker.show();w.receipt_picker.setFixedWidth(210);filters.insertWidget(1,w.receipt_picker)
    picker_index=filters.indexOf(w.receipt_picker)
    filters.insertWidget(picker_index,w.previous);filters.insertWidget(picker_index+2,w.next)
    for button,text in [(w.previous,'‹'),(w.next,'›')]:
        button.setText(text);button.setFixedWidth(32);button.show()
    w.previous.setToolTip('Phiếu trước');w.next.setToolTip('Phiếu sau')
    search=QLineEdit();search.setObjectName('receiptSearch');search.setPlaceholderText('Tìm NCC / mặt hàng');search.setClearButtonEnabled(True);search.setFixedWidth(280);filters.insertWidget(0,search);filters.insertStretch(1,1)
    empty=QLabel('Không tìm thấy phiếu phù hợp. Xóa từ khóa để hiện lại danh sách; phiếu đang xem được giữ nguyên.')
    empty.setWordWrap(True);empty.setStyleSheet('background:#fff8e8;color:#ad781b;padding:10px;border-radius:7px;');empty.hide()
    w.receipt_page.layout().insertWidget(2,empty)
    import unicodedata
    def normalized(value):
        return ''.join(c for c in unicodedata.normalize('NFD',str(value).casefold().replace('đ','d')) if not unicodedata.combining(c))
    completion_model=QStringListModel(search);completer=QCompleter(completion_model,search);completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion);search.setCompleter(completer)
    from PySide6.QtGui import QPalette,QColor
    popup=completer.popup();popup.setObjectName('receiptSearchSuggestions')
    popup.setFont(search.font());popup.setAutoFillBackground(True)
    palette=popup.palette()
    for role,color in [(QPalette.Base,'#ffffff'),(QPalette.Text,'#34415a'),(QPalette.Highlight,'#eeebff'),(QPalette.HighlightedText,'#5548c3')]:palette.setColor(role,QColor(color))
    popup.setPalette(palette)
    popup.setStyleSheet('QAbstractItemView {background-color:#ffffff;color:#34415a;border:1px solid #dfe4ed;selection-background-color:#eeebff;selection-color:#5548c3;font-family:Segoe UI;font-size:12px;} QAbstractItemView::item {background-color:#ffffff;color:#34415a;padding:8px;} QAbstractItemView::item:selected {background-color:#eeebff;color:#5548c3;}')
    matches_by_label={};all_labels={}
    def filter_names(query):
        from rec_fluent_ui import short_supplier
        from rec_receipt_search import matches,suggestions
        selected=all_labels.get(query)
        entries=[]
        for i in range(w.receipt_list.count()):
            item=w.receipt_list.item(i);name=item.data(Qt.UserRole);rows=w.data_by_sheet.get(name,[])
            supplier=next((str(v.get('Nhà cung cấp')) for _,v in rows if v.get('Nhà cung cấp')),'NCC chưa rõ')
            nickname=short_supplier(supplier,w.root)
            entries.append((name,rows,nickname))
            item.setHidden(name not in selected if selected is not None else not matches(query,name,rows,nickname))
        if selected is None:
            all_labels.clear();all_labels.update(suggestions(query,entries))
        matches_by_label.clear();matches_by_label.update(all_labels)
        count=sum(not w.receipt_list.item(i).isHidden() for i in range(w.receipt_list.count()))
        empty.setVisible(bool(query.strip()) and not count)
        completion_model.setStringList(list(matches_by_label))
        search.setToolTip(f'{count} phiếu phù hợp trong ngày đang chọn. Xóa từ khóa để hiện tất cả.')
    def choose_match(label):
        sheets=all_labels.get(label)
        if sheets and not w.busy:
            search.setText(label);filter_names(label)
            # Keep the supplier/product filter when opening a matching receipt.
            if w.current_sheet not in sheets:
                for i in range(w.receipt_list.count()):
                    name=w.receipt_list.item(i).data(Qt.UserRole)
                    if name in sheets:w.select_sheet(name);break
            completer.popup().hide();w.receipt_menu.hide()
    def suggest(text):
        if text.strip() and matches_by_label:
            completer.setCompletionPrefix('');completer.complete()
        else:completer.popup().hide()
    search.textChanged.connect(filter_names);search.textEdited.connect(suggest)
    completer.activated[str].connect(choose_match)
    def first_match():
        if search.text().strip() and matches_by_label:choose_match(next(iter(matches_by_label)))
    search.returnPressed.connect(first_match)
    w.receipt_list.itemClicked.connect(lambda _:w.receipt_menu.hide())
    for control in [w.merge_button,w.show_all,w.publish_button]:filters.removeWidget(control)
    footer=QHBoxLayout()
    footer.addWidget(w.show_all);footer.addStretch();footer.addWidget(w.publish_button)
    w.region_view.parentWidget().layout().addLayout(footer)
    w.merge_button.hide()
    w.add_button.hide();w.read_button.hide()
    # Review status stays explicit and uses semantic color instead of inferring
    # ledger confirmation from the review marker.
    review=w.ops_review_button
    def sync_status():
        approved=bool(w.current_sheet) and w.approved(w.current_sheet)
        review.setText('● Đã kiểm tra' if approved else '● Chưa kiểm tra')
        color=COLORS['done' if approved else 'warning']
        review.setStyleSheet('QPushButton {color:'+color+';background:white;border:1px solid #e3e6ef;border-radius:7px;padding:8px 12px;}')
        review.setToolTip('Bấm để bỏ xác nhận kiểm tra' if approved else 'Bấm để xác nhận đã kiểm tra; chưa ghi sổ')
    refresh=w.refresh_table
    def refreshed(*args,**kwargs):
        result=refresh(*args,**kwargs);sync_status();filter_names(search.text())
        from rec_missing_source import refresh as source_refresh
        source_refresh(w)
        if not w.show_all.isChecked():
            for i,key in enumerate(w.table.model().visible):
                w.table.setColumnWidth(i,190 if key=='Tên hàng trên phiếu (Ảnh)' else 80)
        return result
    w.refresh_table=refreshed;w.receipt_list.currentRowChanged.connect(lambda *_:sync_status())
    w.table.model().compact=['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị trên phiếu','Đơn vị tính','Thực nhận','Đơn giá','Mã kho']
    w.table.model().labels['Đơn vị trên phiếu']='ĐVT nguồn'
    w.table.model().labels['Đơn vị tính']='ĐVT danh mục'
    # Stable controls for paging/zoom. Original page combo and preview handle
    # document references and source regions.
    pages=QLabel();pages.setObjectName('receiptSourcePage')
    def page_text(*_):pages.setText(f'Trang {w.page_combo.currentIndex()+1} / {w.page_combo.count()}' if w.page_combo.count() else 'Chưa có ảnh')
    w.page_combo.currentIndexChanged.connect(page_text);w.page_combo.model().rowsInserted.connect(page_text);w.page_combo.model().rowsRemoved.connect(page_text)
    w.sync_source_page=page_text
    w.image_header.addWidget(pages);page_text()
    w.reference_toggle.setText('PR');w.image_title.hide();w.review_label.hide()
    w.reference_toggle.setObjectName('receiptReferenceToggle')
    data=w.region_view.parentWidget().layout()
    def detach(layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().hide()
            elif item.layout():detach(item.layout())
    detach(data)
    meta=QHBoxLayout();meta.addWidget(w.invoice_meta,1);meta.addWidget(w.only_numbers);meta.addWidget(w.number_summary);meta.addWidget(w.next_number);data.addLayout(meta)
    for x in [w.invoice_meta,w.only_numbers,w.number_summary,w.next_number]:x.show()
    data.addWidget(w.review_tabs,1);w.review_tabs.show()
    w.region_view.hide();data.addWidget(w.region_view)
    w.row_detail.setMaximumHeight(60);data.addWidget(w.row_detail);w.row_detail.show()
    totals=QHBoxLayout();totals.addWidget(w.paper_total_label,1);totals.addWidget(w.total_label,1);data.addLayout(totals);w.paper_total_label.show();w.total_label.show()
    actions=QHBoxLayout()
    for x in [w.table_edit_button,w.table_lookup_button]:x.hide()
    w.compare_pr_button.show()
    original_menu=w.build_row_menu
    def context_menu(pos):
        menu=original_menu(pos);menu.addSeparator()
        for text,callback in [('Ghép trang',w.merge_images),('Rà số lượng và giá',lambda:__import__('rec_numeric_review_page').show(w))]:
            action=menu.addAction(text);action.setEnabled(bool(w.current_sheet) and not w.busy);action.triggered.connect(callback)
        return menu
    w.build_row_menu=context_menu
    w.receipt_action_row=actions
    footer=actions;footer.addWidget(w.show_all);footer.addStretch();data.addLayout(footer);w.show_all.setChecked(True);w.show_all.hide()
    filters.addWidget(w.compare_pr_button);filters.addWidget(w.publish_button)
    w.compare_pr_button.hide();w.publish_button.setText('Xuất phiếu');w.publish_button.show()
    for x in [w.compare_pr_button,w.publish_button]:
        x.setStyleSheet(x.styleSheet()+'\nQPushButton,QToolButton {min-height:0px;max-height:32px;padding:5px 9px;}');x.setFixedHeight(34)
    w.receipt_search=search;w.receipt_status_sync=sync_status
    # Row-source crop is optional; selecting another row must not reopen it
    # behind the user's back (the original handler clears it on selection).
    clear=w.clear_row_region
    def cleared(*a,**kw):
        result=clear(*a,**kw)
        w.region_view.hide()
        return result
    w.clear_row_region=cleared
    w.table.selectionModel().currentRowChanged.connect(lambda *_:w.region_view.hide())
    refreshed()
    from rec_control_metrics import install as install_metrics
    install_metrics(w)


    def sync_picker(*_):
        from shiboken6 import isValid
        if not isValid(w.receipt_list) or not isValid(w.receipt_picker):return
        available=w.receipt_list.count()>0
        w.receipt_picker.setEnabled(available and (not w.busy or getattr(w,'_reading_progress_active',False)))
        if not available:
            w.receipt_picker.setText('chưa có phiếu')
            w.receipt_picker.setToolTip('chưa có phiếu')
            w.receipt_menu.hide()
        else:
            from rec_fluent_ui import short_supplier
            item=w.receipt_list.currentItem()
            name=item.data(Qt.UserRole) if item else ''
            rows=w.data_by_sheet.get(name,[])
            supplier=next((str(v.get('Nhà cung cấp')) for _,v in rows if v.get('Nhà cung cấp')),'')
            w.receipt_picker.setText(short_supplier(supplier,w.root) if supplier else (name or 'Chọn nhà cung cấp / phiếu'))
            w.receipt_picker.setToolTip(f'{supplier}\n{name}')
    w.receipt_list.currentRowChanged.connect(sync_picker)
    for signal in [w.receipt_list.model().rowsInserted,w.receipt_list.model().rowsRemoved,w.receipt_list.model().modelReset]:signal.connect(sync_picker)
    picker_refresh=w.refresh_table
    def refresh_picker(*a,**kw):
        result=picker_refresh(*a,**kw);sync_picker();return result
    w.refresh_table=refresh_picker
    picker_busy=w.set_busy
    def busy_picker(*a,**kw):
        result=picker_busy(*a,**kw);sync_picker();return result
    w.set_busy=busy_picker
    sync_picker()

    # Reuse the existing controls in the search row and collapse the old band.
    title=w.receipt_page.findChild(QLabel,'opsPageTitle')
    if title:
        heading=title.parentWidget();band=heading.layout().itemAt(0).layout()
        while band.count():
            item=band.takeAt(0);control=item.widget()
            if control:
                if control is w.bulk_pr_button or control is w.ops_profile:continue
                control.hide()
        filters.insertWidget(1,w.bulk_pr_button);w.bulk_pr_button.show()
        filters.insertWidget(2,w.ops_profile);w.ops_profile.show()
        heading.hide()
    filters.setSpacing(8)
    search.setFixedWidth(240)
    search.setPlaceholderText('Tìm NCC / hàng trong ngày')
    search.setToolTip('Chỉ tìm trong ngày đang chọn. Dùng trang Tra cứu phiếu để tìm nhiều ngày.')

    from rec_receipt_toolbar import install as install_toolbar
    install_toolbar(w)
    from rec_monthly_prices import install as install_monthly_prices
    install_monthly_prices(w)


    from rec_image_clipboard import install as install_copy_image
    install_copy_image(w)

    item_search=QLineEdit();item_search.setObjectName('receiptItemSearch');item_search.setPlaceholderText('Tìm mặt hàng / tên chuẩn / mã hàng trong phiếu…');item_search.setClearButtonEnabled(True);item_search.setMinimumHeight(36)
    item_search.setAccessibleName('Tìm mặt hàng trong phiếu giao')
    item_count=QLabel();item_count.setObjectName('receiptItemSearchCount')
    search_host=QWidget();search_row=QHBoxLayout(search_host);search_row.setContentsMargins(0,0,0,0);search_row.setSpacing(10);search_row.addWidget(item_search,1);search_row.addWidget(item_count)
    w.receipt_item_search=item_search;w.receipt_item_count=item_count
    host=w.review_tabs.parentWidget().layout();host.insertWidget(host.indexOf(w.review_tabs),search_host)
    item_search.textChanged.connect(lambda *_:w.apply_number_filter())
    w.review_tabs.currentChanged.connect(lambda index:search_host.setVisible(index==0))
    search_host.setVisible(w.review_tabs.currentIndex()==0)
    w.apply_number_filter()

    from rec_receipt_order import install as install_receipt_order
    install_receipt_order(w)

    from PySide6.QtCore import QTimer
    prefetch_timer=QTimer(w);prefetch_timer.setSingleShot(True);prefetch_timer.setInterval(30)
    def prefetch_next():
        if w.reference_mode or not w.preview.item:return
        if w.preview.workers:
            prefetch_timer.start();return
        from receiving_service import invoice_pages
        row=w.receipt_list.currentRow()
        for index in (row+1,row-1):
            if not 0<=index<w.receipt_list.count():continue
            sheet=w.receipt_list.item(index).data(Qt.UserRole)
            pages=invoice_pages(sheet,w.data_by_sheet.get(sheet,[]),w.images)
            if pages:w.preview.prefetch(pages[0])
            if w.preview.workers:
                prefetch_timer.start();return
    prefetch_timer.timeout.connect(prefetch_next)
    w.preview.previewReady.connect(lambda _:prefetch_timer.start() if w.preview.item else prefetch_timer.stop())
    w.preview_prefetch_timer=prefetch_timer
