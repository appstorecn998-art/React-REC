"""Offline checks for the new desktop view and non-destructive previews."""
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.append(str(Path.home() / "Desktop" / "Auto"))
from PIL import Image, ImageDraw, ImageStat
from openpyxl import Workbook, load_workbook
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from receiving_preview import brighten, document_crop, prepare_preview
from receiving_qt import PreviewView, ReceiptTableModel, ReceivingWindow, CatalogModel, DepartmentDelegate, ReadingProgress
from receiving_service import digest
from receiving_review import numeric_issues, choose_region, ranked_codes, crop_region

APP = QApplication.instance() or QApplication([])


def pump_until(condition, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if condition(): return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for Qt background work")


class PreviewTests(unittest.TestCase):
    def test_spotlight_dims_only_outside_row_and_lens_can_be_toggled(self):
        from PySide6.QtCore import QPointF
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'page.png';Image.new('RGB',(600,800),'white').save(path)
            before=digest(path);view=PreviewView();view.resize(420,550);view.crop=False;view.light=False;view.show()
            try:
                view.set_image(path);pump_until(lambda:view.item is not None)
                view.set_focus_region(path,(0,300,600,400));APP.processEvents()
                image=view.viewport().grab().toImage()
                outside=view.mapFromScene(QPointF(300,150));inside=view.mapFromScene(QPointF(300,350))
                self.assertLess(image.pixelColor(outside).red(),150)
                self.assertGreater(image.pixelColor(inside).red(),220)
                view.set_magnifier(True);view.lens_point=inside
                view.viewport().grab();self.assertTrue(view.magnifier)
                view.set_magnifier(False);self.assertIsNone(view.lens_point)
                view.set_focus_region();self.assertIsNone(view.focus_rect())
                self.assertEqual(digest(path),before)
                view.preview_info={'original_size':(1000,1200),'crop_box':(100,200,700,1000)}
                view.set_focus_region(path,(0,500,1000,600))
                rect=view.focus_rect();self.assertAlmostEqual(rect.top(),300)
                self.assertAlmostEqual(rect.height(),100)
                view.clear_image();self.assertIsNone(view.focus_rect())
            finally:
                view.pool.waitForDone();view.close();APP.processEvents()

    def test_date_button_ignores_wheel_and_typing_and_commits_calendar_choice(self):
        from receiving_qt import CalendarDateEdit
        from PySide6.QtCore import QDate, QPointF
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtTest import QTest, QSignalSpy
        from PySide6.QtWidgets import QLineEdit
        button=CalendarDateEdit();button.setDate(QDate(2026,11,6));button.show()
        spy=QSignalSpy(button.dateChanged)
        try:
            event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,1200),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
            APP.sendEvent(button,event)
            QTest.keyClicks(button,'2099')
            self.assertEqual(button.date(),QDate(2026,11,6));self.assertEqual(spy.count(),0)
            self.assertFalse(hasattr(button,'lineEdit'))
            QTest.mouseClick(button,Qt.LeftButton);APP.processEvents()
            self.assertTrue(button.popup.isVisible())
            button.choose_date(QDate(2026,11,7))
            self.assertFalse(button.popup.isVisible())
            self.assertEqual(button.date(),QDate(2026,11,7));self.assertEqual(spy.count(),1)
        finally:
            button.popup.close();button.close()

    def test_numeric_review_preserves_zero_and_distinguishes_arithmetic_from_ocr_proof(self):
        rows=[(2,{'Số lượng':2,'Thực nhận':0,'Đơn giá':10,'Thành tiền':0,'STT trên phiếu':'1','Ảnh nguồn':'one.jpg'}),
              (3,{'Số lượng':3,'Thực nhận':3,'Đơn giá':10,'Thành tiền':30,'STT trên phiếu':'3','Ảnh nguồn':'one.jpg','Thành tiền gốc (trước công thức)':35}),
              (4,{'Số lượng':1,'Thực nhận':None,'Đơn giá':None})]
        import copy
        before=copy.deepcopy(rows); flags=numeric_issues(rows)
        self.assertEqual(rows,before)
        self.assertTrue(any('SL nhận khác' in x for x in flags[2]))
        self.assertFalse(any('chưa rõ' in x for x in flags[2]))
        self.assertTrue(any('STT' in x for x in flags[3])); self.assertTrue(any('Tiền ghi' in x for x in flags[3]))
        self.assertEqual(len(flags[4]),2)
        good=[(2,{'Số lượng':2,'Thực nhận':2,'Đơn giá':10,'Thành tiền':20,'Tổng tiền trên phiếu (Số lượng × Đơn giá)':'=IF(COUNT(...))'})]
        self.assertEqual(numeric_issues(good)[2],[])

    def test_region_requires_unique_text_and_keeps_source_unchanged(self):
        words=[{'text':'Chanh vàng','confidence':.98,'box':[50,300,220,330]}]
        match=choose_region(words,'Yellow lemon/Chanh vàng',(500,800),True)
        self.assertEqual(match['text'],'Chanh vàng')
        duplicate=words+[{'text':'Chanh vàng','confidence':.98,'box':[50,500,220,530]}]
        self.assertIsNone(choose_region(duplicate,'Chanh vàng',(500,800)))
        self.assertIsNone(choose_region(words,'Cá thu',(500,800)))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'p.png'; Image.new('RGB',(500,800),'white').save(path); before=path.read_bytes()
            result=crop_region(path,match['box'],match['anchor'])
            self.assertEqual(path.read_bytes(),before); self.assertLess(result.height,800)

    def test_unmapped_standard_name_is_blank_and_ranked_catalog_never_applies_code(self):
        model=ReceiptTableModel(); values={'Tên hàng trên phiếu (Ảnh)':'Chanh vàng','Mã vật tư':'CHUA CO MA','Tên chuẩn hệ thống':'Không xác định được mã phù hợp'}
        model.set_rows([(2,values)],True)
        index=model.index(0,model.visible.index('Tên chuẩn hệ thống'))
        self.assertEqual(model.data(index),''); self.assertEqual(model.row_values(0)['Tên hàng trên phiếu (Ảnh)'],'Chanh vàng')
        entries=[('001','Cá thu','kg'),('002','Chanh vàng Đà Lạt','kg')]
        self.assertEqual(ranked_codes('chanh vang',entries)[0],1)
        self.assertEqual(values['Mã vật tư'],'CHUA CO MA')

    def test_progress_split_output_distinguishes_read_from_saved(self):
        progress = ReadingProgress(); progress.start(3)
        progress.consume('16:00:00 Đã tải danh mục. Tìm thấy 3 ảnh; đang kiểm tra\n16:00:01 Đã đ')
        self.assertEqual(len(progress.read), 0)
        progress.consume('ọc one.JPG: 4 dòng; đang kiểm tra ghép trang.\n')
        self.assertEqual(len(progress.read), 1); self.assertEqual(progress.invoices, 0)
        self.assertEqual(progress.bar.value(), 0)
        progress.consume('ĐÃ LƯU one.JPG, two.JPG: 8 dòng, ngày nhận 06/11/2026\nBỏ qua ảnh đã lưu: old.JPG (giữ nguyên dữ liệu đã sửa).\n')
        self.assertEqual(progress.invoices, 1); self.assertEqual(len(progress.saved), 2)
        self.assertEqual(progress.bar.value(), 3)
        progress.finish(0); self.assertFalse(progress.timer.isActive()); progress.close()

    def test_progress_error_stays_visible_and_partial_line_is_flushed(self):
        progress = ReadingProgress(); progress.start(15)
        progress.consume('Đã đọc one.JPG: 4 dòng; đang kiểm tra\nChưa đọc xong: timeout')
        progress.finish(1)
        self.assertEqual(len(progress.errors), 1)
        self.assertIn('timeout', progress.alert.text())
        self.assertFalse(progress.alert.isHidden()); self.assertEqual(progress.bar.value(), 0)
        self.assertFalse(progress.timer.isActive()); progress.close()

    def test_catalog_filters_whole_words_and_keeps_original_code(self):
        model = CatalogModel({'001': ('Cá thu tươi', 'kg'), '002': ('Cá hồi', 'kg')})
        model.filter('thu cá')
        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.data(model.index(0, 0)), '001')
        model.filter('missing'); self.assertEqual(model.rowCount(), 0)
        model.filter(''); self.assertEqual(model.rowCount(), 2)

    def test_brighten_dark_page_keeps_ink_and_leaves_bright_page(self):
        image = Image.new("RGB", (300, 400), (145, 145, 145)); ImageDraw.Draw(image).rectangle((20, 30, 240, 40), fill="black")
        fixed, changed = brighten(image)
        self.assertTrue(changed); self.assertGreater(fixed.getpixel((50, 50))[0], 145)
        self.assertEqual(fixed.getpixel((50, 35)), (0, 0, 0))
        white = Image.new("RGB", (100, 100), "white")
        fixed, changed = brighten(white); self.assertFalse(changed); self.assertEqual(fixed.tobytes(), white.tobytes())

    def test_crop_retains_page_and_safety_margin(self):
        image = Image.new("RGB", (900, 1200), (45, 45, 45)); draw = ImageDraw.Draw(image)
        draw.rectangle((90, 95, 810, 1110), fill=(225, 225, 225)); draw.text((105, 110), "DOCUMENT", fill="black")
        cropped, box = document_crop(image)
        self.assertIsNotNone(box)
        self.assertLess(box[0], 90); self.assertLess(box[1], 95)
        self.assertGreater(box[2], 810); self.assertGreater(box[3], 1110)
        self.assertLess(cropped.width, image.width)

    def test_inner_table_is_not_mistaken_for_page_boundary(self):
        image = Image.new("RGB", (900, 1200), "white"); draw = ImageDraw.Draw(image)
        draw.rectangle((100, 100, 800, 1100), outline="black", width=4)
        _, box = document_crop(image); self.assertIsNone(box)

    def test_prepare_preserves_source_and_original_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.png"; Image.new("RGB", (500, 650), (125, 125, 125)).save(path)
            before = path.read_bytes(); original, info = prepare_preview(path, False, False)
            self.assertFalse(info["brightened"]); self.assertIsNone(info["crop_box"])
            self.assertEqual(original.getpixel((0, 0)), (125, 125, 125))
            preview, info = prepare_preview(path); self.assertTrue(info["brightened"])
            self.assertEqual(path.read_bytes(), before)

    def test_view_discards_stale_result_and_zoom_keeps_cursor_anchor(self):
        view = PreviewView(); view.resize(620, 700); view.show(); APP.processEvents()
        with tempfile.TemporaryDirectory() as temp:
            one, two = Path(temp)/"one.png", Path(temp)/"two.png"
            Image.new("RGB", (500, 600), "red").save(one); Image.new("RGB", (650, 800), "blue").save(two)
            view.set_image(one); view.set_image(two)
            pump_until(lambda: view.item is not None and not view.workers)
            self.assertEqual(view.source_path, two)
            self.assertEqual(view.original.getpixel((0, 0)), (0, 0, 255))
            anchor = QPoint(230, 300); before = view.mapToScene(anchor)
            view.zoom_at(1.5, anchor); after = view.mapToScene(anchor)
            self.assertLess(abs(after.x()-before.x()), 2); self.assertLess(abs(after.y()-before.y()), 2)
            view.set_options(False, False); pump_until(lambda: not view.workers)
            self.assertFalse(view.light); self.assertFalse(view.crop)
        view.close()


class DesktopTests(unittest.TestCase):
    def test_catalog_suggestion_applies_selected_code_without_changing_source_name_or_numbers(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QTableView, QPushButton
        w=self.window; w.catalog={'001':('A','kg'),'002':('B chuẩn','hộp')}
        w.table.selectRow(0)
        def choose():
            dialog=APP.activeModalWidget()
            QTimer.singleShot(500,dialog.reject)
            table=dialog.findChild(QTableView); table.model().filter('002'); table.selectRow(0)
            button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Dùng mã cho dòng đang chọn')
            button.click()
        QTimer.singleShot(30,choose)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes): w.lookup_code()
        pump_until(lambda: not w.busy)
        book=load_workbook(self.report); sheet=book['FIRST']
        self.assertEqual(sheet['A2'].value,'A'); self.assertEqual(sheet['B2'].value,'002')
        self.assertEqual(sheet['C2'].value,'B chuẩn'); self.assertEqual(sheet['D2'].value,'hộp')
        self.assertEqual(sheet['E2'].value,2); self.assertEqual(sheet['F2'].value,0); book.close()

    def test_local_locator_subprocess_uses_image_hash_cache_and_updates_selected_row(self):
        w=self.window
        path=next(p for p in w.images if p.name=='one.png')
        cache=w.folder/'row-locations'; cache.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(b'local-locator-v1'+path.read_bytes()).hexdigest()
        data={'version':1,'size':[100,140],'words':[{'text':'A','confidence':.99,'box':[10,60,30,70]}]}
        (cache/(key+'.json')).write_text(json.dumps(data),encoding='utf-8')
        before=digest(self.report); image_before=path.read_bytes()
        w.local_review_enabled=True; w.table.selectRow(0)
        pump_until(lambda: w.location_process is None and bool(w.region_scene.items()) and 'Vùng gợi ý' in w.region_title.text())
        self.assertIn('Vùng gợi ý',w.region_title.text())
        self.assertEqual(path.read_bytes(),image_before); self.assertEqual(digest(self.report),before)

    def test_numeric_filter_hides_only_safe_rows_and_next_selects_warning(self):
        w=self.window
        w.data_by_sheet[w.current_sheet]=[(2,{'Tên hàng trên phiếu (Ảnh)':'A','Số lượng':1,'Thực nhận':1,'Đơn giá':10,'Thành tiền':10}),
                                        (3,{'Tên hàng trên phiếu (Ảnh)':'B','Số lượng':2,'Thực nhận':0,'Đơn giá':10,'Thành tiền':0})]
        w.refresh_table(); w.only_numbers.setChecked(True)
        self.assertTrue(w.table.isRowHidden(0)); self.assertFalse(w.table.isRowHidden(1))
        w.next_numeric_row(); self.assertEqual(w.table.model().source_row(w.table.currentIndex().row()),3)
        w.only_numbers.setChecked(False); self.assertFalse(w.table.isRowHidden(0))

    def test_bulk_warehouse_one_transaction_and_stale_source_is_refused(self):
        from receiving_service import mutate_invoice
        book=load_workbook(self.report); sheet=book['FIRST']
        for col,header in enumerate(['Mã kho','Tên kho','Bộ phận'],13): sheet.cell(1,col,header)
        book.save(self.report); book.close()
        before=digest(self.report); directory={'2000':('Kho lễ tân','FO')}
        mutate_invoice(self.report,before,'FIRST','warehouse',[2,3],'2000',directory)
        book=load_workbook(self.report)
        for row in [2,3]: self.assertEqual([book['FIRST'].cell(row,col).value for col in [13,14,15]],['2000','Kho lễ tân','FO'])
        self.assertEqual(book['FIRST']['F2'].value,0); self.assertEqual(book['SECOND']['A2'].value,'C'); book.close()
        current=digest(self.report)
        with self.assertRaises(ValueError): mutate_invoice(self.report,before,'FIRST','warehouse',[2,3],'2000',directory)
        self.assertEqual(digest(self.report),current)

    def test_delete_first_row_retains_formulas_and_rebuilds_totals(self):
        from receiving_service import mutate_invoice, snapshot
        book=load_workbook(self.report); sheet=book['FIRST']
        sheet.cell(1,13,'Thành tiền trên phiếu'); sheet.cell(1,14,'Tổng tiền trên phiếu (Số lượng × Đơn giá)')
        sheet.cell(1,15,'Tổng tiền phiếu (cộng Thành tiền)')
        sheet.cell(2,13,'=E2*G2'); sheet.cell(3,13,'=E3*G3')
        sheet.cell(2,14,75000); book.save(self.report); book.close()
        mutate_invoice(self.report,digest(self.report),'FIRST','delete',[2])
        book=load_workbook(self.report); sheet=book['FIRST']
        self.assertIsNone(sheet['A2'].value); self.assertEqual(sheet['A3'].value,'B')
        self.assertEqual(sheet['H3'].value,'=F3*G3'); self.assertEqual(sheet['M3'].value,'=E3*G3')
        self.assertIn('SUM(M2:M3)',sheet['N3'].value); self.assertIn('SUM(H2:H3)',sheet['O3'].value)
        self.assertEqual(book['SECOND']['A2'].value,'C'); book.close()
        self.assertEqual(len(dict(snapshot(self.report)[1])['FIRST']),1)
        before=digest(self.report)
        with self.assertRaises(ValueError): mutate_invoice(self.report,before,'FIRST','delete',[3])
        self.assertEqual(digest(self.report),before)
        self.assertTrue(list((self.directory/'.autowatcher-backups').rglob('*.xlsx')))

    def test_background_save_keeps_event_loop_responsive_and_scroll(self):
        from PySide6.QtCore import QTimer
        w=self.window; w.show(); APP.processEvents()
        w.table.horizontalScrollBar().setValue(100); initial=w.table.horizontalScrollBar().value()
        ticks=[]; timer=QTimer(); timer.setInterval(10); timer.timeout.connect(lambda: ticks.append(1)); timer.start()
        w.write_in_background(lambda: time.sleep(.15))
        pump_until(lambda: not w.busy)
        timer.stop()
        self.assertGreater(len(ticks),3)
        self.assertEqual(w.table.horizontalScrollBar().value(),initial)

    def test_single_click_department_opens_choices_without_changing_report(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QComboBox
        w = self.window
        w.get_warehouses = lambda: {'1103': ('Kho bếp Caya', 'KC')}
        w.data_by_sheet[w.current_sheet][0][1]['Bộ phận'] = 'KC'
        w.refresh_table(); w.show(); APP.processEvents()
        model = w.table.model(); index = model.index(0, model.visible.index('Bộ phận'))
        w.table.scrollTo(index); APP.processEvents()
        before = digest(self.report)
        QTest.mouseClick(w.table.viewport(), Qt.LeftButton, pos=w.table.visualRect(index).center())
        pump_until(lambda: bool(w.table.findChildren(QComboBox)))
        editor = w.table.findChildren(QComboBox)[0]
        pump_until(lambda: editor.view().isVisible())
        self.assertEqual(editor.itemData(1), '1103')
        editor.hidePopup(); QTest.keyClick(editor, Qt.Key_Escape); APP.processEvents()
        self.assertEqual(digest(self.report), before)

    def test_totals_below_table_keep_paper_total_separate_and_do_not_sum_repeats(self):
        w = self.window
        rows = [(2, {'Tên hàng trên phiếu (Ảnh)': 'A', 'Thành tiền': 20,
                     'Tổng tiền trên phiếu (Số lượng × Đơn giá)': 90}),
                (3, {'Tên hàng trên phiếu (Ảnh)': 'B', 'Thành tiền': 40,
                     'Tổng tiền trên phiếu (Số lượng × Đơn giá)': 90})]
        w.data_by_sheet[w.current_sheet] = rows; w.refresh_table()
        self.assertEqual(w.total_label.text(), 'Tổng tiền: 60 đ')
        self.assertEqual(w.paper_total_label.text(), 'Tổng trên phiếu: 90 đ')
        self.assertNotIn('Tổng tiền trên phiếu (Số lượng × Đơn giá)', w.table.model().visible)
        rows[1][1]['Tổng tiền trên phiếu (Số lượng × Đơn giá)'] = 100
        w.refresh_table()
        self.assertIn('chưa đủ dữ liệu', w.paper_total_label.text())

    def test_warehouse_choice_updates_three_fields_and_rejects_unknown_code(self):
        from receiving_service import edit_row
        book = load_workbook(self.report); sheet = book['FIRST']
        for col, header in enumerate(['Mã kho', 'Tên kho', 'Bộ phận'], 13): sheet.cell(1,col,header)
        book.save(self.report); book.close()
        directory = {'1101': ('Kho bếp Starfish', 'KC'), '1103': ('Kho bếp Caya', 'KC')}
        before = digest(self.report)
        with self.assertRaises(ValueError):
            edit_row(self.report, before, 'FIRST', 2, {'Mã kho':'bad'}, {}, directory)
        self.assertEqual(digest(self.report), before)
        edit_row(self.report, before, 'FIRST', 2, {'Mã kho':'1103'}, {'001':('A','kg')}, directory)
        book = load_workbook(self.report); sheet = book['FIRST']
        self.assertEqual([sheet.cell(2,c).value for c in [13,14,15]], ['1103','Kho bếp Caya','KC'])
        self.assertEqual(sheet['H2'].value, '=F2*G2'); self.assertEqual(sheet['F2'].value, 0)
        book.close()
        w = self.window
        w._day_loaded(w._load_day(self.day,self.destination,self.root))
        w.get_warehouses = lambda: directory
        model = w.table.model(); model.editRequested.disconnect(w.save_row_changes)
        changes = []; model.editRequested.connect(changes.append)
        index = model.index(0, model.visible.index('Bộ phận'))
        delegate = w.table.itemDelegate(); editor = delegate.createEditor(w.table, None, index)
        delegate.setEditorData(editor,index)
        self.assertEqual(editor.currentData(), '1103')
        editor.setCurrentIndex(editor.findData('1101')); delegate.setModelData(editor,model,index)
        self.assertEqual(changes, [(2, {'Mã kho':'1101'})])
        editor.deleteLater()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.destination = self.root / "accounting"
        self.day = date(2026, 11, 5); self.directory = self.destination / "Thang 11" / "Ngay 05"
        self.directory.mkdir(parents=True)
        (self.root / ".receiving").mkdir()
        (self.root/".receiving"/"settings.json").write_text(json.dumps({"destination": str(self.destination)}), encoding="utf-8")
        headers = ["Tên hàng trên phiếu (Ảnh)", "Mã vật tư", "Tên chuẩn hệ thống", "Đơn vị tính", "Số lượng", "Thực nhận", "Đơn giá", "Thành tiền", "Nhà cung cấp", "Ảnh nguồn", "Các ảnh cùng phiếu", "Ghi chú"]
        book = Workbook(); first = book.active; first.title = "FIRST"
        first.append(headers); first.append(["A", "001", "A", "kg", 2, 0, 15000, "=F2*G2", "Cùng NCC", "one.png", "one.png;two.png", ""])
        first.append(["B", "002", "B", "kg", 3, 1, 15000, "=F3*G3", "Cùng NCC", "two.png", "", ""])
        second = book.create_sheet("SECOND"); second.append(headers)
        second.append(["C", "", "", "kg", 1, None, None, None, "Cùng NCC", "three.png", "", ""])
        self.report = self.directory/"TongHopPhieuNgay_05-11-2026.xlsx"; book.save(self.report); book.close()
        for name in ["one.png", "two.png", "three.png", "unlinked.png"]:
            Image.new("RGB", (100, 140), "white").save(self.directory/name)
        self.window = ReceivingWindow(self.root, self.day, auto_load=False)
        self.window.local_review_enabled = False
        self.window._day_loaded(self.window._load_day(self.day, self.destination, self.root))
        self.addCleanup(self.close_window)

    def close_window(self):
        pump_until(lambda: not self.window.busy and not self.window.preview.workers)
        self.window.close();self.window.deleteLater();APP.processEvents()

    def test_navigation_syncs_same_supplier_and_each_page(self):
        w = self.window
        self.assertEqual(w.current_sheet, "FIRST"); self.assertEqual(w.current_image.name, "one.png")
        w.move_receipt(1); self.assertEqual(w.current_sheet, "SECOND"); self.assertEqual(w.current_image.name, "three.png")
        w.select_image(next(i for i,p in enumerate(w.images) if p.name == "two.png"))
        self.assertEqual(w.current_sheet, "FIRST"); self.assertEqual(w.current_image.name, "two.png")
        w.table.selectRow(0); self.assertEqual(w.current_image.name, "one.png")
        with patch.object(w, 'choose_receipt_references') as choose:
            w.select_image(next(i for i,p in enumerate(w.images) if p.name == "unlinked.png"))
            choose.assert_called_once()
        self.assertEqual(w.current_sheet, "FIRST"); self.assertEqual(w.table.model().rowCount(), 2)
        self.assertEqual(w.current_image.name, "one.png")

    def test_reference_toggle_preserves_receipt_rows_and_report(self):
        w = self.window; before = digest(self.report)
        w.save_receipt_references([next(p for p in w.images if p.name == 'unlinked.png')])
        w.toggle_reference_images()
        self.assertTrue(w.reference_mode)
        self.assertEqual(w.current_image.name, 'unlinked.png')
        self.assertEqual(w.current_sheet, 'FIRST')
        w.table.selectRow(1)
        self.assertEqual(w.current_image.name, 'unlinked.png')
        w.toggle_reference_images()
        self.assertFalse(w.reference_mode)
        self.assertIn(w.current_image.name, ['one.png', 'two.png'])
        self.assertEqual(w.page_combo.count(), 2)
        w.toggle_reference_images(); w.move_receipt(1)
        self.assertFalse(w.reference_mode)
        self.assertEqual(w.current_image.name, 'three.png')
        self.assertEqual(digest(self.report), before)

    def test_manual_pr_links_persist_and_do_not_leak_to_other_receipts(self):
        w = self.window
        pr = next(p for p in w.images if p.name == 'unlinked.png')
        w.save_receipt_references([pr])
        w._day_loaded(w._load_day(self.day, self.destination, self.root))
        self.assertEqual(w.receipt_references(), [pr])
        w.move_receipt(1)
        self.assertEqual(w.receipt_references(), [])
        w.move_receipt(-1)
        pr.write_bytes(b'changed image')
        self.assertEqual(w.receipt_references(), [])
        w.save_receipt_references([])
        self.assertEqual(w.receipt_references(), [])

    def test_approval_can_be_revoked_and_survives_reload(self):
        w = self.window; before = digest(self.report)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            w.approve()
            self.assertTrue(w.approved('FIRST'))
            self.assertEqual(w.approve_button.text(), 'Bỏ xác nhận')
            w.approve()
        self.assertFalse(w.approved('FIRST'))
        w._day_loaded(w._load_day(self.day, self.destination, self.root))
        self.assertFalse(w.approved('FIRST'))
        self.assertEqual(w.approve_button.text(), 'Xác nhận')
        self.assertEqual(digest(self.report), before)
        self.assertTrue(w.table.horizontalScrollBar().hasTracking())

    def test_pr_comparison_saves_separately_without_mutating_receipt(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog
        w=self.window;before=digest(self.report)
        image=next(p for p in w.images if p.name=='unlinked.png')
        w.save_receipt_references([image])
        w.show_pr_comparison([{'item_name':'A','catalog_code':'001','unit':'kg','quantity':'5','unit_price':'15000'}],w.data_by_sheet['FIRST'],[image])
        self.assertTrue(w.pr_save())
        saved=json.loads(w.reference_link_path().with_suffix('.comparison.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['results'][0]['remaining'],'5')
        self.assertEqual(digest(self.report),before)
        with patch.object(w,'show_pr_comparison') as show,patch.object(QMessageBox,'question') as question:
            w.compare_current_pr();show.assert_called_once();question.assert_not_called()

    def test_local_ledger_records_once_and_detects_source_edits(self):
        from PySide6.QtWidgets import QInputDialog
        import receiving_ledger as ledger
        w=self.window;before=digest(self.report)
        image=next(p for p in w.images if p.name=='unlinked.png');w.save_receipt_references([image])
        items=[{'item_name':'A','catalog_code':'001','unit':'kg','quantity':'5','unit_price':'15000'}]
        with patch.object(w,'confirm_ledger_receipt',return_value=True), patch.object(QMessageBox,'question',return_value=QMessageBox.Yes), patch.object(QMessageBox,'information'), patch.object(QMessageBox,'warning') as warning, patch.object(QInputDialog,'getItem',side_effect=lambda *args,**kw:(args[3][0],True)):
            w.approve()
            w.record_ledger(items,w.data_by_sheet['FIRST'],[image],{0:2})
            w.record_ledger(items,w.data_by_sheet['FIRST'],[image],{0:2})
            self.assertFalse(warning.called,warning.call_args)
        result,history=ledger.summary(w.ledger_path(),lambda p:w._ledger_valid(p,{}))
        self.assertEqual(len(history),1);self.assertTrue(history[0]['valid']);self.assertEqual(result[0]['remaining'],'5')
        self.assertEqual(digest(self.report),before)
        book=load_workbook(self.report);book['FIRST']['F2']=2;book.save(self.report);book.close()
        result,_=ledger.summary(w.ledger_path(),lambda p:w._ledger_valid(p,{}))
        self.assertIsNone(result[0]['remaining'])

    def test_conversion_dialog_persists_factor_without_editing_workbook(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QTableWidget,QPushButton,QLineEdit,QDialogButtonBox
        w=self.window;before=digest(self.report)
        image=next(p for p in w.images if p.name=='unlinked.png');w.save_receipt_references([image])
        items=[{'item_name':'A','catalog_code':'001','unit':'g','quantity':'2000','unit_price':'15'}]
        w.show_pr_comparison(items,w.data_by_sheet['FIRST'],[image])
        table=w.pr_compare_table;table.selectRow(0);APP.processEvents()
        def fill():
            edit=APP.activeModalWidget()
            self.assertIsNotNone(edit)
            edit.findChild(QLineEdit,'conversionSourceCount').setText('1')
            edit.findChild(QLineEdit,'conversionTargetCount').setText('1000')
            edit.findChild(QLineEdit,'conversionReason').setText('Xác nhận cho dữ liệu test')
            edit.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        QTimer.singleShot(50,fill)
        next(button for button in w.pr_panel.findChildren(QPushButton) if button.text()=='Quy đổi đơn vị').click()
        self.assertTrue(w.pr_save())
        saved=json.loads(w.reference_link_path().with_suffix('.comparison.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['conversions']['0']['factor'],'1000')
        self.assertEqual(saved['results'][0]['delivery_price'],'15')
        self.assertEqual(digest(self.report),before)

    def test_pr_picker_uses_checkboxes_and_reports_existing_links(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QListWidget
        w=self.window;before=digest(self.report)
        def choose():
            dialog=APP.activeModalWidget()
            QTimer.singleShot(500,dialog.reject)
            listing=dialog.findChild(QListWidget)
            item=listing.item(0)
            self.assertTrue(bool(item.flags() & Qt.ItemIsUserCheckable))
            self.assertEqual(item.checkState(),Qt.Unchecked)
            item.setCheckState(Qt.Checked)
            dialog.accept()
        QTimer.singleShot(50,choose)
        w.choose_receipt_references()
        self.assertEqual([p.name for p in w.receipt_references()],['unlinked.png'])
        self.assertEqual(digest(self.report),before)
        self.assertEqual(w.pr_image_owners(),{'unlinked.png':['FIRST']})
        w.move_receipt(1)
        self.assertEqual(w.pr_image_owners(),{'unlinked.png':['FIRST']})
        def reopen():
            dialog=APP.activeModalWidget();QTimer.singleShot(500,dialog.reject)
            item=dialog.findChild(QListWidget).item(0)
            self.assertIn('Đã ghép: FIRST',item.text())
            self.assertEqual(item.checkState(),Qt.Unchecked)
            dialog.reject()
        QTimer.singleShot(50,reopen);w.choose_receipt_references()

    def test_filters_and_all_columns_do_not_change_source(self):
        w = self.window; before = digest(self.report)
        w.filter_box.setCurrentText("Thiếu mã"); self.assertEqual(w.receipt_list.count(), 1); self.assertEqual(w.current_sheet, "SECOND")
        w.filter_box.setCurrentText("Đã kiểm tra"); self.assertEqual(w.receipt_list.count(), 0); self.assertEqual(w.table.model().rowCount(), 0)
        w.filter_box.setCurrentText("Tất cả phiếu"); w.show_all.setChecked(True)
        self.assertEqual(w.table.model().columnCount(), 9)
        self.assertEqual(digest(self.report), before)

    def test_edit_role_uses_unformatted_values_and_preserves_zero(self):
        model = self.window.table.model(); price_col = model.visible.index("Đơn giá"); received_col = model.visible.index("Thực nhận")
        self.assertEqual(model.data(model.index(0, price_col), Qt.EditRole), "15000")
        self.assertEqual(model.data(model.index(0, received_col), Qt.EditRole), "0")
        self.assertEqual(model.row_values(0)["Thành tiền"], "=F2*G2")

    def test_inline_edit_saves_and_only_invalidates_changed_receipt(self):
        w = self.window; w.reviews = dict(w.signatures)
        from receiving_service import atomic_json
        atomic_json(w.folder/"reviewed.json", w.reviews)
        w.catalog = {"001": ("A", "kg"), "002": ("B", "kg")}
        w.save_row_changes((2, {"Thực nhận": "1"}))
        pump_until(lambda: not w.busy)
        self.assertFalse(w.approved("FIRST")); self.assertTrue(w.approved("SECOND"))
        book = load_workbook(self.report); self.assertEqual(book["FIRST"]["F2"].value, 1); self.assertEqual(book["FIRST"]["H2"].value, "=F2*G2"); book.close()

    def test_load_error_clears_stale_rows_and_source(self):
        w = self.window; w._load_failed("fixture failure")
        self.assertIsNone(w.report); self.assertIsNone(w.source_hash); self.assertEqual(w.table.model().rowCount(), 0)


if __name__ == "__main__": unittest.main()
