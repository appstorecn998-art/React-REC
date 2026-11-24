"""Selecting a previously read PR across receiving days."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QDialogButtonBox, QFormLayout, QMessageBox, QSplitter, QWidget)
from fluent_blue import Button, Input
import receiving_pr_library as library
from receiving_service import atomic_json, digest


class PRLibraryUI:
    def pr_library_directory(self):
        return library.library_path(self.ledger_path())

    def remember_pr(self, items, images):
        return library.register(self.pr_library_directory(), images, items)

    def stored_pr_items(self, images):
        record = library.load(self.pr_library_directory()).get(library.identity(images,self.pr_library_directory()))
        return record['items'] if record else None

    def use_library_pr(self, key, *, expected=None):
        record = library.load(self.pr_library_directory())[key]
        images = library.images_for(record)
        # A stored library selection is verified here, never accepted as arbitrary paths.
        from rec_pr_link_write import write_link
        write_link(self.reference_link_path(), dict(version=2, source='pr-library',
            sheet=self.current_sheet, library_key=key, paths=record['images'],
            images={p.name:digest(p) for p in images}),expected=expected,action='explicit-library-selection')
        return images

    def _pr_library_context(self):
        directory=self.pr_library_directory();ledger_path=self.ledger_path()
        return str(directory),str(ledger_path)

    def choose_saved_pr(self):
        if not self._leave_pr():return False
        from receiving_qt import Worker
        directory=self.pr_library_directory();ledger_path=self.ledger_path()
        context=self._pr_library_context()
        cached=getattr(self,'_pr_library_cached',None)
        if cached and cached[0]==context and cached[1][-1] is not None and file_stamp(cached[1][-2])==cached[1][-1]:
            if getattr(self,'pr_library_page',None) is not None:
                self.main_pages.setCurrentWidget(self.pr_library_page)
            else:self._show_saved_pr(*cached[1][:3])
            return False
        loading=getattr(self,'_pr_library_loading',None)
        if loading and loading[0]==context:
            self.main_pages.setCurrentWidget(loading[1]);return False
        previous_state=getattr(self,'_pr_library_state_page',None)
        if previous_state is not None and not getattr(self,'_pr_library_loading',None):
            from shiboken6 import isValid
            if isValid(previous_state):self.main_pages.removeWidget(previous_state);previous_state.deleteLater()
        page=QWidget();page.setObjectName('prLibraryLoading');self._pr_library_state_page=page
        from rec_loading_state import LoadingState
        layout=QVBoxLayout(page);layout.setContentsMargins(28,24,28,24)
        loading_ui=LoadingState('Thư viện PR','Đang tải thư viện PR','Kiểm tra ảnh nguồn và trạng thái nhận hàng. Bạn vẫn có thể chuyển sang mục khác.',retry=self.choose_saved_pr)
        layout.addWidget(loading_ui);layout.addStretch()
        self.main_pages.addWidget(page);self.main_pages.setCurrentWidget(page)
        self._pr_library_loading=(context,page)
        job=Worker(load_library_data,directory,ledger_path,self.report)
        def ready(data):
            if getattr(self,'_pr_library_loading',None)!=(context,page):return
            if self._pr_library_context()!=context:
                loading_ui.fail('Thư mục dữ liệu đã đổi. Mở lại thư viện để tải dữ liệu mới.');return
            self._pr_library_cached=(context,data)
            if self.main_pages.currentWidget() is page:self._show_saved_pr(*data[:3])
            else:
                # Build on the next visit; do not steal navigation focus.
                old=getattr(self,'pr_library_page',None)
                if old is not None:self.main_pages.removeWidget(old);old.deleteLater();self.pr_library_page=None
        def failed(message):
            loading_ui.fail('Chưa tải được thư viện PR: '+message)
        def finished():
            if getattr(self,'_pr_library_loading',None)==(context,page):self._pr_library_loading=None
            if self.main_pages.currentWidget() is not page:self.main_pages.removeWidget(page);page.deleteLater()
        job.signals.result.connect(ready);job.signals.error.connect(failed);job.signals.finished.connect(finished)
        self._start_worker(job)
        return False

    def _show_saved_pr(self,entries,totals,directory):
        from receiving_qt import PreviewView
        previous=getattr(self,'pr_library_page',None)
        if previous is not None:
            self.main_pages.removeWidget(previous);previous.deleteLater()
        dialog=QWidget();dialog.setObjectName('savedPRPicker');self.pr_library_page=dialog
        dialog.library_owner=self
        self.main_pages.addWidget(dialog)
        layout=QVBoxLayout(dialog)
        hint=QLabel('Chọn đúng số PR, NCC và ngày · Xem ảnh trước khi ghép. PR lần đầu: đóng danh sách này, chọn ảnh và Đối chiếu PR.');hint.setWordWrap(True);layout.addWidget(hint)
        search=Input();search.setPlaceholderText('Tìm số PR, nhà cung cấp, ngày hoặc bộ phận');search.setObjectName('prLibrarySearch');layout.addWidget(search)
        split=QSplitter(Qt.Horizontal);layout.addWidget(split,1)
        listing=QListWidget();listing.setWordWrap(True);listing.setObjectName('savedPRList');split.addWidget(listing)
        panel=QWidget();right=QVBoxLayout(panel);split.addWidget(panel)
        preview=PreviewView();right.addWidget(preview,1)
        pagebar=QHBoxLayout();previous=Button('Trang trước');following=Button('Trang sau');page_label=QLabel();pagebar.addWidget(previous);pagebar.addWidget(page_label);pagebar.addWidget(following);right.addLayout(pagebar)
        edits={};form=QFormLayout()
        for field,label in [('number','Số PR'),('supplier','Nhà cung cấp'),('date','Ngày PR'),('department','Bộ phận')]:
            edit=Input();edit.setObjectName('prMeta_'+field);form.addRow(label,edit);edits[field]=edit
        right.addLayout(form)
        save=Button('Lưu thông tin nhận diện PR');right.addWidget(save)
        note=QLabel('Thông tin nhận diện giúp chọn PR; không thay đổi số lượng đặt hay tự cộng các PR cùng số.');note.setWordWrap(True);right.addWidget(note)
        split.setSizes([470,730])
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Chọn PR này');buttons.button(QDialogButtonBox.Cancel).setText('Hủy');layout.addWidget(buttons)
        context={}
        try:
            selected_items=self.stored_pr_items(self.receipt_references()) or []
            if selected_items:context={'number':selected_items[0].get('pr_reference_id'),'date':selected_items[0].get('pr_document_date')}
            current_key=library.identity(self.receipt_references(),directory) if self.receipt_references() else None
            if current_key:context=library.load(directory).get(current_key,context)
        except (OSError,ValueError,KeyError):pass
        state={'entry':None,'images':[],'page':0}
        def page(delta=0):
            images=state['images']
            if not images:return
            state['page']=(state['page']+delta)%len(images);preview.set_image(images[state['page']]);page_label.setText(f"Trang {state['page']+1}/{len(images)}")
        def selected():
            item=listing.currentItem();entry=item.data(Qt.UserRole) if item else None;state.update(entry=entry,images=[],page=0)
            for field,edit in edits.items():edit.setText(entry['record'].get(field,'') if entry else '')
            buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            if not entry:preview.clear_image('Không có PR phù hợp');return
            try:state['images']=library.images_for(entry['record']);page();buttons.button(QDialogButtonBox.Ok).setEnabled(True)
            except (OSError,ValueError) as exc:preview.clear_image(str(exc))
        def fill():
            from PySide6.QtCore import QSignalBlocker
            current=state.get('entry');key=current.get('key') if current else None
            # Publish one complete list; transient empty rows are not user selections.
            list_block=QSignalBlocker(listing);model_block=QSignalBlocker(listing.model())
            listing.clear();query=search.text().strip().casefold()
            from receiving_pr_number_identity import rank_suggestions
            for entry in rank_suggestions(entries,context,self.data_by_sheet.get(self.current_sheet,[])):
                from supplier_rules import normalize_name
                if query and normalize_name(query) not in normalize_name(entry['title']):continue
                if not getattr(dialog,'pr_category_match',lambda record:True)(entry['record']):continue
                text=f"{entry['title']}\n{entry['count']} món · Đã nhận đủ {entry['received']} món · {entry['status']}"
                item=QListWidgetItem(text);item.setData(Qt.UserRole,entry);item.setToolTip(text);listing.addItem(item)
            row=next((i for i in range(listing.count()) if listing.item(i).data(Qt.UserRole)['key']==key),0 if listing.count() else -1)
            listing.setCurrentRow(row)
            del model_block;del list_block
            selected()
            callback=getattr(dialog,'sync_library_view',None)
            if callback:callback()
        def save_metadata():
            entry=state['entry']
            if not entry:return
            try:
                library.update_metadata(directory,entry['key'],**{name:edit.text() for name,edit in edits.items()})
                entries[:]=library.cards(directory,totals);key=entry['key'];fill()
                for i in range(listing.count()):
                    if listing.item(i).data(Qt.UserRole)['key']==key:listing.setCurrentRow(i);break
            except (OSError,ValueError) as exc:QMessageBox.warning(dialog,'Chưa lưu thông tin PR',str(exc))
        save.clicked.connect(save_metadata);search.textChanged.connect(fill);listing.currentItemChanged.connect(selected)
        previous.clicked.connect(lambda:page(-1));following.clicked.connect(lambda:page(1))
        enlarge=Button('Phóng to ảnh PR');enlarge.setObjectName('enlargePRImage');pagebar.addWidget(enlarge)
        def enlarge_image():
            if state['entry']:
                __import__('rec_pr_image_zoom').show(self,state['entry']['key'],state['page'])
        enlarge.clicked.connect(enlarge_image)
        dialog.select_library_entry=selected
        fill()
        from rec_pr_library_layout import arrange_library
        dialog.pr_all_entries=lambda:entries
        arrange_library(dialog,search,split,listing,panel,save,note,buttons,fill)
        def return_to_receipt():
            self.fluent_nav.set_current('Kiểm tra phiếu')
        buttons.rejected.connect(return_to_receipt)
        enlarge.setFixedHeight(36);enlarge.show()
        dialog.library_preview=preview
        self.main_pages.setCurrentWidget(dialog)
        blocked=self.fluent_nav.blockSignals(True)
        try:self.fluent_nav.set_current('Thư viện PR')
        finally:self.fluent_nav.blockSignals(blocked)
        return False

def file_stamp(paths):
    result=[]
    for raw in sorted(set(map(str,paths))):
        try:
            p=Path(raw);st=p.stat();result.append((raw,st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_ino))
        except OSError:result.append((raw,None))
    return tuple(result)


def load_library_data(directory,ledger_path,report):
    import receiving_ledger as ledger
    from receiving_validation import check
    # Collect dependencies before expensive validation so a concurrent edit
    # prevents reuse of this presentation snapshot on the next navigation.
    records=library.load(directory)
    _,prior=ledger.summary(ledger_path)
    paths=[Path(directory)/'index.json',ledger_path,str(ledger_path)+'-wal']
    for receipt in prior:
        paths.extend(receipt.get(k,'') for k in ('report','reviews_path','pr_link_path'))
        paths.extend(receipt.get('source_images',{}));paths.extend(receipt.get('pr_images',{}))
    from receiving_opening_balance import read as read_opening
    for opening in read_opening(ledger_path).values():
        paths.extend(opening.get('pr_sources',{}));paths.extend(ref.get('path','') for ref in opening.get('attachments',[]))
    for record in records.values():
        for path in record.get('images',{}):paths.extend([path,Path(path).parent/'image-manifest.json'])
    paths=[p for p in paths if p]
    for receipt in prior:
        link=receipt.get('pr_link_path')
        if link:paths.extend([Path(link).with_suffix('.comparison.json'),Path(link).with_suffix('.comparison.review.json')])
    before=file_stamp(paths)
    cache = {}
    known=library.load(directory)
    totals, history = ledger.summary(ledger_path, lambda p:check(p,cache))
    # Backfill old recorded PRs without asking the user to re-read their images.
    for receipt in history:
        if not receipt['active'] or not receipt['valid']:
            continue
        images = [Path(p) for p in receipt.get('pr_images',{})]
        if not images or library.identity(images,directory) in known:
            continue
        import json
        try:
            saved=json.loads(Path(receipt['pr_link_path']).with_suffix('.comparison.json').read_text(encoding='utf-8'))
            key=library.register(directory,images,saved['pr_items']);known[key]=True
        except (OSError,ValueError,KeyError,TypeError):continue
    entries=library.cards(directory,totals)
    stamp=file_stamp(paths)
    return entries,totals,directory,paths,(stamp if stamp==before else None)

