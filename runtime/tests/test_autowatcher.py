import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook
from PIL import Image
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import AutoWatcher as aw
import supplier_rules as sr
from delivery_export import HEADERS as DELIVERY_HEADERS

SOURCE = PROJECT_ROOT / "DanhMuc.xlsm"


def payload(name="Chuối cau", code="001", review=False, confidence=91):
    return {"items": [{"invoice_name": name, "catalog_code": code,
                       "needs_review": review, "confidence": confidence, "note": ""}]}


def pair_payload(pr_reference="PR-17", delivery_reference="PR-17", row_status="match", pr_count=1):
    pr_items = [{"item_name": "Chuối cau", "catalog_code": "001", "quantity": "5",
                 "unit": "kg", "specification": "", "group_id": ""}]
    if pr_count == 2:
        pr_items.append({"item_name": "Bơ sáp", "catalog_code": "002", "quantity": "2",
                         "unit": "kg", "specification": "", "group_id": ""})
    rows = [{"pr_line": 1, "delivery_line": 1, "status": row_status,
             "note": "Số lượng và quy cách khớp."}]
    if pr_count == 2:
        rows.append({"pr_line": 2, "delivery_line": 0, "status": "only_pr",
                     "note": "Không thấy Bơ sáp trên phiếu giao."})
    return {"documents": [
        {"source_image": 1, "document_type": "pr", "reference_id": pr_reference,
         "supplier_name": "Nhà cung cấp", "items": pr_items},
        {"source_image": 2, "document_type": "delivery", "reference_id": delivery_reference,
         "supplier_name": "Nhà cung cấp", "items": [{
             "item_name": "Chuối cau", "catalog_code": "", "quantity": "5",
             "unit": "kg", "specification": "", "group_id": ""}]},
    ], "comparison": {"status": "match", "summary": "Tên, số lượng và quy cách khớp.", "rows": rows}}


def batch_items():
    pr = [
        {"line_id": "PR1:1", "item_name": "Chuối cau", "catalog_code": "001", "quantity": "10",
         "received_quantity": "", "unit": "kg", "specification": "", "group_id": ""},
        {"line_id": "PR1:2", "item_name": "Bơ sáp", "catalog_code": "002", "quantity": "2",
         "received_quantity": "", "unit": "kg", "specification": "", "group_id": ""},
    ]
    delivery = [
        {"line_id": "DE1:1", "item_name": "Chuối cau", "catalog_code": "001", "quantity": "6",
         "received_quantity": "6", "unit": "kg", "specification": "", "group_id": ""},
        {"line_id": "DE2:1", "item_name": "Chuối cau", "catalog_code": "001", "quantity": "4",
         "received_quantity": "4", "unit": "kg", "specification": "", "group_id": ""},
        {"line_id": "DE2:2", "item_name": "Bơ sáp", "catalog_code": "002", "quantity": "2",
         "received_quantity": "2", "unit": "kg", "specification": "", "group_id": ""},
    ]
    return pr, delivery


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"001": ("Fruit Finger Banana/Chuoi Cau Chin/Kg", "kg")}

    def test_original_catalog_keeps_first_five_and_all_2478_items(self):
        before = hashlib.sha256(SOURCE.read_bytes()).digest()
        catalog = aw.load_catalog(SOURCE)
        self.assertEqual(len(catalog), 2478)
        self.assertEqual(list(catalog)[:5], ["11110001", "11110002", "11110003", "11110004", "11110005"])
        self.assertIn("11410050", catalog)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).digest(), before)

    def test_code_and_authoritative_name_unit_are_from_catalog(self):
        rows = aw.validate_rows(payload(), self.catalog)
        self.assertEqual(rows[0][1:4], ["001", self.catalog["001"][0], "kg"])
        self.assertEqual(rows[0][4], .91)

    def test_review_report_includes_order_received_price_and_amount(self):
        data = payload(confidence=90)
        data["items"][0].update({"quantity": "5", "received_quantity": "4.2",
                                 "unit_price": "25,000", "line_amount": "125,000"})
        row = aw.validate_rows(data, self.catalog)[0]
        self.assertEqual(row[12:16], [5, 4.2, 25000, 125000])
        self.assertEqual(aw.parse_invoice_amount("80,000 VND"), 80000)
        self.assertIsNone(aw.parse_invoice_amount("chưa rõ"))

    def test_report_amount_uses_printed_total_or_ordered_quantity_not_received(self):
        data = payload(confidence=90)
        data["items"][0].update({"quantity": "5", "received_quantity": "4.2",
                                 "unit_price": "25,000"})
        row = aw.validate_rows(data, self.catalog)[0]
        self.assertEqual(row[15], 125000)
        data["items"][0]["line_amount"] = "120,000"
        row = aw.validate_rows(data, self.catalog)[0]
        self.assertEqual(row[15], 120000)

    def test_quantity_and_amount_parsers_accept_common_vietnamese_number_formats(self):
        self.assertEqual(aw.parse_simple_quantity("100,00"), 100)
        self.assertEqual(aw.parse_simple_quantity("1,5"), 1.5)
        self.assertEqual(aw.parse_simple_quantity("1.000"), 1000)
        self.assertEqual(aw.parse_invoice_amount("25,000 VND"), 25000)
        self.assertEqual(aw.parse_invoice_amount("5.000"), 5000)

    def test_cached_resolved_rows_restore_original_delivery_values(self):
        stale = {"items": [{"line_id": "DE1:1", "invoice_name": "Thanh long ĐP",
                            "catalog_code": "11410050", "quantity": None,
                            "received_quantity": None, "unit_price": None}]}
        source = [{"line_id": "DE1:1", "quantity": "10", "received_quantity": "",
                   "unit_price": "", "line_amount": "250,000", "unit": "Kg",
                   "english_name": "White dragon fruit", "vietnamese_name": "Thanh long ĐP"}]
        restored = aw.restore_delivery_source_fields(stale, source)
        self.assertEqual(restored["items"][0]["quantity"], "10")
        self.assertEqual(restored["items"][0]["received_quantity"], "")
        self.assertEqual(restored["items"][0]["line_amount"], "250,000")
        self.assertEqual(restored["items"][0]["invoice_unit"], "Kg")

    def test_number_parsers_preserve_excel_numbers_and_mixed_locale_separators(self):
        self.assertEqual(aw.parse_simple_quantity(1.234), aw.Decimal("1.234"))
        self.assertEqual(aw.parse_simple_quantity("0.005"), aw.Decimal("0.005"))
        self.assertEqual(aw.parse_simple_quantity("1.234,50"), aw.Decimal("1234.5"))
        self.assertEqual(aw.parse_invoice_amount("1,234.50 VND"), 1234.5)
        self.assertEqual(aw.parse_invoice_amount("1.234,50 VNĐ"), 1234.5)
        self.assertIsNone(aw.parse_simple_quantity("1,000"))
        for value in ("1.23.456", "1,23.45", float("nan"), float("inf"), -1):
            with self.subTest(value=value):
                self.assertIsNone(aw.parse_simple_quantity(value))
                self.assertIsNone(aw.parse_invoice_amount(value))

    def test_source_restore_rejects_missing_or_duplicate_line_ids(self):
        source = [{"line_id": "DE1:1"}, {"line_id": "DE1:2"}]
        for ids in (["DE1:1", "DE1:1"], ["DE1:1", "DE1:3"], ["DE1:1"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                aw.restore_delivery_source_fields({"items": [{"line_id": x} for x in ids]}, source)

    def test_cached_batch_restores_figures_before_writing_report_without_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_path = root / "analysis.json"
            resolved = payload(confidence=90)
            resolved["items"][0]["line_id"] = "DE1:1"
            resolved["extracted"] = {"supplier_name": "NCC", "items": [
                {"invoice_name": "Chuối cau", "group_id": ""}]}
            cache_path.write_text(json.dumps({"resolved": resolved, "comparison": None}), encoding="utf-8")
            entry = {"path": "delivery.jpg", "document": {"document_type": "delivery",
                     "reference_id": "", "supplier_name": "NCC", "items": [{
                         "item_name": "Chuối cau", "quantity": "5", "received_quantity": "4.2",
                         "unit_price": "25.000", "line_amount": "125.000", "unit": "kg"}]}}
            args = argparse.Namespace(timeout=5, output=root, review_only=True)
            with (patch.object(aw, "read_batch_documents", return_value=[entry]),
                  patch.object(aw, "batch_analysis_cache_path", return_value=cache_path),
                  patch.object(aw, "resolve_batch_items") as resolve,
                  patch.object(aw, "request_batch_comparison") as compare):
                report = aw.process_batch(root, args, "unused", self.catalog, {}, {"suppliers": []},
                                          image_paths=[Path("delivery.jpg")])
            resolve.assert_not_called()
            compare.assert_not_called()
            wb = load_workbook(report, read_only=True, data_only=True)
            try:
                row = next(wb.active.iter_rows(min_row=2, max_row=2, values_only=True))
                self.assertEqual(row[12:16], (5, 4.2, 25000, 125000))
            finally:
                wb.close()

    def test_review_report_keeps_bilingual_names_and_invoice_unit_for_all_unmapped_items(self):
        data = {"items": [{"invoice_name": "Đu đủ xanh", "catalog_code": "", "confidence": 0,
                           "needs_review": True, "note": "Không có mã đủ tin cậy.",
                           "english_name": "Green papaya", "vietnamese_name": "Đu đủ xanh",
                           "invoice_unit": "kg", "quantity": "3", "received_quantity": "3",
                           "unit_price": "15000", "line_amount": "45000"}]}
        for confidence in (0, 49, 50, 90, 100):
            with self.subTest(confidence=confidence):
                data["items"][0]["confidence"] = confidence
                row = aw.validate_rows(data, self.catalog)[0]
                self.assertEqual(row[1], "CHUA CO MA")
                self.assertEqual(row[0], "Đu đủ xanh")
                self.assertEqual(row[3], "kg")

    def test_batch_document_captures_english_vietnamese_and_invoice_unit(self):
        document = {"document_type": "delivery", "reference_id": "", "supplier_name": "NCC",
                    "items": [{"item_name": "Đu đủ xanh", "english_name": "Green papaya",
                               "vietnamese_name": "Đu đủ xanh", "catalog_code": "", "quantity": "3",
                               "received_quantity": "3", "unit_price": "15000", "unit": "kg",
                               "line_amount": "45000",
                               "specification": "", "group_id": "1410"}]}
        validated = aw.validate_batch_document(document)
        self.assertEqual(validated["items"][0]["english_name"], "Green papaya")
        self.assertEqual(validated["items"][0]["vietnamese_name"], "Đu đủ xanh")
        self.assertEqual(validated["items"][0]["line_amount"], "45000")

    def test_old_batch_document_cache_defaults_missing_line_amount(self):
        document = {"document_type": "delivery", "reference_id": "", "supplier_name": "NCC",
                    "items": [{"item_name": "Đu đủ xanh", "english_name": "Green papaya",
                               "vietnamese_name": "Đu đủ xanh", "catalog_code": "", "quantity": "3",
                               "received_quantity": "3", "unit_price": "15000", "unit": "kg",
                               "specification": "", "group_id": "1410"}]}
        self.assertEqual(aw.validate_batch_document(document)["items"][0]["line_amount"], "")

    def test_delivery_export_preserves_unmapped_name_and_amount(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "TongHop.xlsx"
            wb = Workbook()
            sheet = wb.active
            sheet.append(aw.HEADERS)
            sheet.append(["Green papaya/Đu đủ xanh", "CHUA CO MA", "Không xác định được mã phù hợp", "kg", .49,
                          "CẦN KIỂM TRA", "Không có mã trên 50%.", "NCC", "1410", "Chờ kiểm tra",
                          "", "", 3, 2.8, 15000, 42000])
            wb.save(report_path)
            wb.close()
            rows = aw.reviewed_delivery_rows(report_path, self.catalog)
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(rows[0]), 1)
            self.assertEqual(rows[0][0]["code"], "")
            self.assertEqual(rows[0][0]["name"], "Green papaya/Đu đủ xanh")
            self.assertEqual(rows[0][0]["unit"], "kg")
            self.assertEqual(rows[0][0]["amount"], 42000)

    def test_delivery_export_accepts_missing_and_unknown_codes_at_any_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "TongHop.xlsx"
            for code in ("", "CHUA CO MA", "unknown-code"):
                for confidence in (None, 0, .49, .50, .9, 1):
                    with self.subTest(code=code, confidence=confidence):
                        wb = Workbook()
                        wb.active.append(aw.HEADERS)
                        wb.active.append(["Green papaya/Đu đủ xanh", code, "Không xác định", "kg", confidence,
                                          "CẦN KIỂM TRA", "Cần rà.", "NCC", "1410", "Chờ kiểm tra",
                                          "", "", 3, 0, 15000, 45000])
                        wb.save(report_path)
                        wb.close()
                        row = aw.reviewed_delivery_rows(report_path, self.catalog)[0][0]
                        self.assertEqual(row["code"], "")
                        self.assertEqual(row["name"], "Green papaya/Đu đủ xanh")
                        self.assertEqual(row["unit"], "kg")
                        self.assertEqual(row["received"], 0)
                        self.assertEqual(row["amount"], 45000)

    def test_delivery_export_derives_unit_price_from_printed_amount_and_order_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "TongHop.xlsx"
            wb = Workbook()
            sheet = wb.active
            sheet.append(aw.HEADERS)
            sheet.append(["Chuối cau", "001", self.catalog["001"][0], "kg", .95,
                          "CÓ TRONG DANH MỤC", "", "NCC", "1410", "AI", "", "",
                          5, 4.2, None, 125000])
            wb.save(report_path)
            wb.close()
            rows = aw.reviewed_delivery_rows(report_path, self.catalog)
            self.assertEqual(rows[0][0]["unit_price"], 25000)
            self.assertEqual(rows[0][0]["amount"], 125000)

    def test_delivery_export_still_blocks_missing_price_or_inexact_price_derivation(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "TongHop.xlsx"
            for amount in (None, 2):
                with self.subTest(amount=amount):
                    wb = Workbook()
                    wb.active.append(aw.HEADERS)
                    wb.active.append(["Chuối cau", "001", self.catalog["001"][0], "kg", .95,
                                      "CÓ TRONG DANH MỤC", "", "NCC", "1410", "AI", "", "",
                                      3, 2, None, amount])
                    wb.save(report_path)
                    wb.close()
                    with self.assertRaisesRegex(ValueError, "thiếu số lượng hoặc đơn giá"):
                        aw.reviewed_delivery_rows(report_path, self.catalog)

    def test_delivery_export_writes_bilingual_name_without_code_at_high_confidence(self):
        catalog = aw.load_catalog(SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "Ngay 02"
            output_dir.mkdir()
            template = Workbook()
            sheet = template.active
            sheet.append(DELIVERY_HEADERS)
            sheet["H2"] = "=F2*G2"
            template_path = root / "Phieu giao hang ngay 01.xlsx"
            template.save(template_path)
            template.close()
            report_path = root / "TongHop.xlsx"
            report = Workbook()
            sheet = report.active
            sheet.append(aw.HEADERS + ["Tên tiếng Anh trên phiếu", "Tên tiếng Việt trên phiếu",
                                       "Đơn vị trên phiếu"])
            sheet.append(["Đu đủ xanh", "CHUA CO MA", "Không xác định", "", .95,
                          "CẦN KIỂM TRA", "", "NCC", "1410", "AI", "", "", 3, 3,
                          15000, 45000, None, '', '', '', "Green papaya", "Đu đủ xanh", "kg"])
            report.save(report_path)
            report.close()
            final_path = aw.create_delivery_workbook(report_path, catalog, template_path, output_dir)
            result = load_workbook(final_path, read_only=False, data_only=False)
            try:
                self.assertIsNone(result["1"]["E2"].value)
                self.assertEqual(result["1"]["F2"].value, "Green papaya/Du du xanh")
                self.assertEqual(result["1"]["G2"].value, "Kg")
                self.assertEqual(result["1"]["K2"].value, "=I2*J2")
            finally:
                result.close()

    def test_delivery_export_combines_all_tonghop_sheets(self):
        catalog = aw.load_catalog(SOURCE)
        codes = list(catalog)[:2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "Thang 11"
            output_dir.mkdir()
            template_path = output_dir / "Phieu giao hang ngay 01.xlsx"
            template = Workbook()
            sample = template.active
            sample.title = "1"
            sample.append(DELIVERY_HEADERS)
            sample["B2"] = "Old sample data"
            sample["H2"] = "=F2*G2"
            sample.column_dimensions["B"].width = 65
            template.create_sheet("2")["B2"] = "Old second sheet"
            template.save(template_path)
            template.close()

            report_path = root / "TongHop.xlsx"
            report = Workbook()
            report.remove(report.active)
            for index, code in enumerate(codes, 1):
                sheet = report.create_sheet(f"Batch_{index}")
                sheet.append(aw.HEADERS)
                sheet.append(["Tên OCR", code, f"Approved item {index}", f"Unit {index}", .95,
                              "CÓ TRONG DANH MỤC", "", "NCC", "Nhóm", "AI", "KHỚP", "",
                              5, 4.2, 25000, 105000])
            report.save(report_path)
            report.close()

            final_path = aw.create_delivery_workbook(
                report_path, catalog, template_path=template_path, output_dir=output_dir,
                now=datetime(2026, 11, 2))
            final = load_workbook(final_path, read_only=False, data_only=False)
            try:
                self.assertEqual(final_path.name, "Phieu giao hang ngay 02.xlsx")
                self.assertEqual(final.sheetnames, ["1"])
                for index, code in enumerate(codes, 1):
                    sheet = final["1"]
                    row = index + 1
                    self.assertEqual(sheet.max_column, 19)
                    self.assertEqual(sheet.cell(row, 5).value, code)
                    self.assertEqual(sheet.cell(row, 6).value, f"Approved item {index}")
                    self.assertEqual(sheet.cell(row, 7).value, f"Unit {index}")
                    self.assertEqual([sheet.cell(row, column).value for column in (9, 10)],
                                     [4.2, 25000])
                    self.assertEqual(sheet.cell(row, 11).value, f"=I{row}*J{row}")
                    self.assertNotIn("Old", str(sheet["B2"].value))
                self.assertEqual(final["1"].column_dimensions["B"].width, 65)
            finally:
                final.close()

    def test_delivery_export_restores_same_file_from_backup_after_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            month_dir = root / "Thang 11"
            output_dir = month_dir / "Ngay 02"
            output_dir.mkdir(parents=True)
            template_path = month_dir / "Phieu giao hang ngay 01.xlsx"
            template = Workbook()
            template.active.append(DELIVERY_HEADERS)
            template.save(template_path)
            template.close()
            report_path = root / "TongHop_2026-11-02.xlsx"
            report = Workbook()
            sheet = report.active
            sheet.append(aw.HEADERS)
            sheet.append(["Tên", "001", self.catalog["001"][0], "kg", .95, "CÓ TRONG DANH MỤC",
                          "", "NCC", "Nhóm", "AI", "", "", 1, 1, 100, 100])
            report.save(report_path)
            report.close()

            first = aw.create_delivery_workbook(report_path, self.catalog, template_path, output_dir,
                                                now=datetime(2026, 11, 2))
            backup = aw.delivery_backup_directory(output_dir) / first.name
            self.assertTrue(backup.is_file())
            first.unlink()
            restored = aw.create_delivery_workbook(report_path, self.catalog,
                                                   template_path=template_path,
                                                   output_dir=output_dir, now=datetime(2026, 11, 2))
            self.assertEqual(restored, first)
            self.assertTrue(restored.is_file())
            self.assertFalse((output_dir / "Phieu giao hang ngay 02 (ban 2).xlsx").exists())

    def test_delivery_template_uses_fixed_root_file_over_prior_month_deliveries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "Thang 11" / "Ngay 02"
            previous_template = root / "Thang 10" / "Ngay 31" / "Phieu giao hang ngay 31.xlsx"
            previous_template.parent.mkdir(parents=True)
            workbook = Workbook()
            workbook.active["A1"] = "Mã hàng"
            workbook.save(previous_template)
            workbook.close()
            fixed_template = root / "Phieu giao hang ngay X.xlsx"
            workbook = Workbook()
            workbook.save(fixed_template)
            workbook.close()
            self.assertEqual(aw.delivery_template_path(output_dir), fixed_template)

    def test_delivery_export_keeps_unmapped_row_with_uncertain_pr_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "TongHop.xlsx"
            report = Workbook()
            sheet = report.active
            sheet.append(aw.HEADERS)
            sheet.append(["Item", "CHUA CO MA", "", "", .50, "CẦN KIỂM TRA", "", "", "", "",
                          "CHƯA RÕ", "", 1, 1, 100, 100])
            report.save(report_path)
            report.close()
            row = aw.reviewed_delivery_rows(report_path, self.catalog)[0][0]
            self.assertEqual(row["code"], "")
            self.assertEqual(row["name"], "Item")
            self.assertEqual(row["quantity"], 1)

    def test_delivery_output_directory_and_filename_follow_selected_calendar_day(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_auto = Path(directory) / "Auto"
            fake_auto.mkdir()
            with patch.object(aw, "BASE_DIR", fake_auto):
                first_day = aw.delivery_output_directory(datetime(2026, 11, 2))
                second_day = aw.delivery_output_directory(datetime(2026, 11, 3))
                self.assertEqual(first_day.name, "Ngay 02")
                self.assertEqual(second_day.name, "Ngay 03")
                self.assertEqual(first_day.parent, second_day.parent)
                self.assertEqual(aw.next_delivery_path(first_day, datetime(2026, 11, 2)).name,
                                 "Phieu giao hang ngay 02.xlsx")

    def test_export_reviewed_tonghop_uses_current_date_and_needs_no_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "TongHop_2026-11-02.xlsx"
            report.touch()
            args = argparse.Namespace(output=root, delivery_date="02/11/2026")
            expected = root / "Thang 11" / "Ngay 02" / "Phieu giao hang ngay 01.xlsx"
            with patch.object(aw, "create_delivery_workbook", return_value=expected) as create:
                result = aw.export_reviewed_tonghop(args, self.catalog, datetime(2026, 11, 2))
            self.assertEqual(result, expected)
            self.assertEqual(create.call_args.args[0], report)

    def test_export_reviewed_tonghop_reports_missing_same_day_report(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(output=Path(directory))
            with self.assertRaisesRegex(FileNotFoundError, "Không tìm thấy TongHop"):
                aw.export_reviewed_tonghop(args, self.catalog, datetime(2026, 11, 2))

    def test_export_reviewed_cli_does_not_require_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / "Phieu giao hang ngay 01.xlsx"
            with (patch.object(sys, "argv", ["AutoWatcher.py", "--export-reviewed", "--output", directory]),
                  patch.object(aw, "load_catalog_data", return_value=(self.catalog, {})),
                  patch.object(aw, "export_reviewed_tonghop", return_value=final_path) as export):
                self.assertEqual(aw.main(), 0)
            export.assert_called_once()

    def test_two_run_files_route_to_distinct_modes(self):
        review_run = (PROJECT_ROOT / "01_Doc_mot_don.bat").read_text(encoding="utf-8")
        delivery_run = (PROJECT_ROOT / "02_Xuat_phieu_mot_don.bat").read_text(encoding="utf-8")
        self.assertIn("--review-only", review_run)
        self.assertIn("--export-reviewed", delivery_run)

    def test_delivery_export_uses_first_template_sheet_and_removes_extra_sample_tabs(self):
        catalog = aw.load_catalog(SOURCE)
        codes = list(catalog)[:2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "Thang 11"
            output_dir.mkdir()
            template_path = output_dir / "Phieu giao hang ngay 01.xlsx"
            template = Workbook()
            first = template.active
            first.title = "1"
            first.append(DELIVERY_HEADERS)
            first["B2"] = "Old item to clear"
            first["H2"] = "=F2*G2"
            first.column_dimensions["B"].width = 65
            for index in range(2, 20):
                template.create_sheet(str(index))["B2"] = f"Old sheet {index}"
            template.save(template_path)
            template.close()

            report_path = root / "TongHop.xlsx"
            report = Workbook()
            report.remove(report.active)
            for index, code in enumerate(codes, 1):
                sheet = report.create_sheet(f"LocalSend_{index}")
                sheet.append(aw.HEADERS)
                sheet.append(["Tên ghi trên phiếu", code, f"Approved item {index}", f"Unit {index}", .95,
                              "CÓ TRONG DANH MỤC", "", "NCC", "Nhóm", "AI", "KHỚP", "",
                              5, 4.2, 25000, 105000])
            report.save(report_path)
            report.close()

            final_path = aw.create_delivery_workbook(report_path, catalog, template_path, output_dir,
                                                     now=datetime(2026, 11, 2))
            result = load_workbook(final_path, read_only=False, data_only=False)
            try:
                self.assertEqual(final_path.name, "Phieu giao hang ngay 02.xlsx")
                self.assertEqual(result.sheetnames, ["1"])
                for index, code in enumerate(codes, 1):
                    sheet = result["1"]
                    row = index + 1
                    self.assertEqual(sheet.max_column, 19)
                    self.assertEqual(sheet.cell(row, 5).value, code)
                    self.assertEqual(sheet.cell(row, 6).value, f"Approved item {index}")
                    self.assertEqual(sheet.cell(row, 7).value, f"Unit {index}")
                    self.assertEqual([sheet.cell(row, column).value for column in (9, 10)],
                                     [4.2, 25000])
                    self.assertEqual(sheet.cell(row, 11).value, f"=I{row}*J{row}")
                    self.assertNotEqual(sheet["B2"].value, "Old item to clear")
                self.assertEqual(result["1"].column_dimensions["B"].width, 65)
            finally:
                result.close()

    def test_delivery_export_keeps_unmapped_name_with_missing_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "TongHop.xlsx"
            wb = Workbook()
            sheet = wb.active
            sheet.append(aw.HEADERS)
            sheet.append(["Item", "CHUA CO MA", "", "", .50, "CẦN KIỂM TRA", "", "", "", "", "", "",
                          None, None, None, None])
            wb.save(report_path)
            wb.close()
            row = aw.reviewed_delivery_rows(report_path, self.catalog)[0][0]
            self.assertEqual(row["code"], "")
            self.assertEqual(row["name"], "Item")
            self.assertIsNone(row["quantity"])
            self.assertIsNone(row["unit_price"])

    def test_unknown_code_cannot_be_written_as_valid(self):
        rows = aw.validate_rows(payload(code="made-up-code"), self.catalog)
        self.assertEqual(rows[0][1], "CHUA CO MA")
        self.assertEqual(rows[0][3], "")
        self.assertEqual(rows[0][5], "CẦN KIỂM TRA")

    def test_absent_and_ambiguous_are_distinct(self):
        absent = aw.validate_rows(payload(code=""), self.catalog)[0]
        ambiguous = aw.validate_rows(payload(code="", review=True), self.catalog)[0]
        self.assertEqual(absent[5], "KHÔNG TÌM THẤY")
        self.assertEqual(ambiguous[5], "CẦN KIỂM TRA")

    def test_empty_partial_and_wrong_types_rejected(self):
        for value in [None, {}, {"items": []}, {"items": [{}]}, payload(confidence=101),
                      payload(confidence=True), payload(name=""), payload(review="false")]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    aw.validate_rows(value, self.catalog)

    def test_duplicate_invoice_lines_not_dropped(self):
        data = payload()
        data["items"] *= 2
        self.assertEqual(len(aw.validate_rows(data, self.catalog)), 2)

    def test_ambiguous_short_name_cannot_choose_a_variety(self):
        catalog = {"001": ("Fruit Avocado/Bo Sap", "kg"), "002": ("Fruit Avocado/Bo 034", "kg")}
        row = aw.validate_rows(payload(name="Bơ", confidence=85), catalog)[0]
        self.assertEqual(row[1], "CHUA CO MA")
        self.assertEqual(row[5], "CẦN KIỂM TRA")
        self.assertIn("001", row[6])
        self.assertIn("002", row[6])

    def test_confidence_over_85_keeps_ambiguity_flagged(self):
        catalog = {"001": ("Fruit Avocado/Bo Sap", "kg"), "002": ("Fruit Avocado/Bo 034", "kg")}
        row = aw.validate_rows(payload(name="Bơ", confidence=86), catalog)[0]
        self.assertEqual(row[1], "CHUA CO MA")
        self.assertEqual(row[5], "CẦN KIỂM TRA")
        self.assertIn("nhiều mã", row[6])

    def test_confidence_at_85_does_not_auto_accept_reviewed_code(self):
        row = aw.validate_rows(payload(review=True, confidence=85), self.catalog)[0]
        self.assertEqual(row[1], "CHUA CO MA")

    def test_reviewed_proposal_is_not_written_as_a_confirmed_code(self):
        row = aw.validate_rows(payload(review=True, confidence=85), self.catalog)[0]
        self.assertEqual(row[1], "CHUA CO MA")
        self.assertIn("001", row[6])

    def test_high_confidence_code_survives_pr_mismatch_but_stays_flagged(self):
        comparison = aw.validate_pair_analysis(pair_payload(row_status="mismatch"))[1]
        row = aw.validate_rows(payload(confidence=90), self.catalog, pair_analysis=comparison)[0]
        self.assertEqual(row[1], "001")
        self.assertEqual(row[5], "CẦN KIỂM TRA")
        self.assertEqual(row[10], "KHÔNG KHỚP")

    def test_root_batch_signature_includes_all_root_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("PR_01.jpg", "PR_02.jpg", "delivery.jpg"):
                Image.new("RGB", (16, 16)).save(root / name)
            (root / aw.BATCH_MARKER).write_text("", encoding="utf-8")
            signature = aw.batch_signature(root, root)
            self.assertEqual({entry[0] for entry in signature},
                             {"PR_01.jpg", "PR_02.jpg", "delivery.jpg", aw.BATCH_MARKER})

    def test_no_ambiguity_when_other_sku_lacks_a_required_word(self):
        catalog = {"001": ("Fruit Jujube/Tao Xanh VN", "kg"), "002": ("Fruit Pear/Le VN", "kg")}
        row = aw.validate_rows(payload(name="Táo VN"), catalog)[0]
        self.assertEqual(row[1], "001")

    def test_candidate_union_keeps_all_varieties_without_top_k_cutoff(self):
        catalog = {str(i): (f"Fruit Avocado/Bo variety {i}", "kg") for i in range(30)}
        catalog["other"] = ("Milk", "Box")
        groups = aw.candidate_groups(["Bơ"], catalog)
        self.assertEqual(len(groups[0]["candidates"]), 30)

    def test_unknown_names_keep_a_row_with_empty_candidates(self):
        groups = aw.candidate_groups(["Capri Tubetop"], self.catalog)
        self.assertEqual(groups, [{"invoice_name": "Capri Tubetop", "candidates": []}])

    def test_alignment_rejects_extra_rows_changed_order_and_unrelated_code(self):
        groups = aw.candidate_groups(["Chuối cau"], self.catalog)
        aw.validate_alignment(payload(), groups)
        for data in [{"items": payload()["items"] * 2}, payload(name="Different"), payload(code="999")]:
            with self.assertRaises(ValueError):
                aw.validate_alignment(data, groups)

    def test_pair_extraction_builds_delivery_input_and_validates_line_alignment(self):
        extracted, comparison = aw.validate_pair_analysis(pair_payload())
        self.assertEqual(extracted["items"][0]["invoice_name"], "Chuối cau")
        self.assertEqual(extracted["items"][0]["quantity"], "5")
        self.assertEqual(comparison["status"], "match")
        malformed = pair_payload()
        malformed["comparison"]["rows"][0]["delivery_line"] = 2
        with self.assertRaises(ValueError):
            aw.validate_pair_analysis(malformed)

    def test_pair_reference_mismatch_forces_review(self):
        _, comparison = aw.validate_pair_analysis(pair_payload("PR-17", "PR-18"))
        self.assertEqual(comparison["status"], "mismatch")
        self.assertTrue(comparison["reference_mismatch"])
        row = aw.validate_rows(payload(confidence=85), self.catalog, pair_analysis=comparison)[0]
        self.assertEqual(row[1], "CHUA CO MA")
        self.assertEqual(row[5], "CẦN KIỂM TRA")
        self.assertEqual(row[10], "KHÔNG KHỚP")

    def test_pair_item_mismatch_blocks_code_but_keeps_report_delivery_only(self):
        _, comparison = aw.validate_pair_analysis(pair_payload(row_status="mismatch", pr_count=2))
        rows = aw.validate_rows(payload(confidence=85), {"001": ("Chuối cau", "kg"), "002": ("Bơ sáp", "kg")},
                                pair_analysis=comparison)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "CHUA CO MA")
        self.assertEqual(rows[0][10], "KHÔNG KHỚP")

    def test_pair_rejects_wrong_document_types_and_missing_pr_rows(self):
        wrong_types = pair_payload()
        wrong_types["documents"][0]["document_type"] = "delivery"
        with self.assertRaises(aw.PairDocumentTypeError) as raised:
            aw.validate_pair_analysis(wrong_types)
        lines = aw.pair_document_type_error_lines(
            raised.exception, Path("IMG_3889.JPG"), Path("IMG_3896.JPG"), Path("PhieuGiao_Input"))
        message = "\n".join(lines)
        self.assertIn("cả hai ảnh là phiếu giao hàng", message)
        self.assertIn("IMG_3889.JPG: AI nhận diện là phiếu giao hàng", message)
        self.assertIn("IMG_3896.JPG: AI nhận diện là phiếu giao hàng", message)
        self.assertIn("chuyển ảnh bị ghép nhầm ra khỏi PhieuGiao_Input", message)
        self.assertNotIn("mạng/API", message)
        missing_pr_line = pair_payload(pr_count=2)
        missing_pr_line["comparison"]["rows"].pop()
        with self.assertRaises(ValueError):
            aw.validate_pair_analysis(missing_pr_line)

    def test_explicit_code_or_quantity_difference_overrides_ai_match(self):
        for field, value in [("catalog_code", "999"), ("quantity", "4")]:
            data = pair_payload()
            data["documents"][1]["items"][0][field] = value
            _, comparison = aw.validate_pair_analysis(data)
            self.assertEqual(comparison["status"], "mismatch")
            self.assertEqual(comparison["rows"][0]["status"], "mismatch")
        self.assertEqual(aw.parse_simple_quantity("5.0"), aw.parse_simple_quantity("5"))
        self.assertIsNone(aw.parse_simple_quantity("1,000"))

    def test_pending_pair_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "pr.jpg", root / "delivery.jpg"
            first.write_bytes(b"pr")
            second.write_bytes(b"delivery")
            state = root / ".autowatcher-pending-pair.json"
            aw.save_pending_pair(state, [first, second])
            self.assertEqual(aw.load_pending_pair(state), [first, second])
            aw.clear_pending_pair(state)
            self.assertEqual(aw.load_pending_pair(state), [])

    def test_pending_pair_keeps_surviving_image_after_other_is_moved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "delivery.jpg", root / "wrong_delivery.jpg"
            first.write_bytes(b"delivery")
            second.write_bytes(b"wrong")
            state = root / ".autowatcher-pending-pair.json"
            aw.save_pending_pair(state, [first, second])
            second.unlink()
            self.assertEqual(aw.load_pending_pair(state), [first])
            self.assertEqual(aw.load_pending_pair(state), [first])

    def test_pending_pair_deduplicates_same_path_left_by_old_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "delivery.jpg"
            first.write_bytes(b"delivery")
            state = root / ".autowatcher-pending-pair.json"
            state.write_text(json.dumps({"paths": [str(first), str(first)]}), encoding="utf-8")
            self.assertEqual(aw.load_pending_pair(state), [first])
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["paths"], [str(first.resolve())])

    def test_pair_wait_discards_duplicate_event_for_first_image(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "pr.jpg", Path(directory) / "delivery.jpg"
            first.write_bytes(b"pr")
            second.write_bytes(b"delivery")
            pending = queue.Queue()
            pending.put(first)
            pending.put(second)
            stat = first.stat()
            seen = {first: (stat.st_size, stat.st_mtime_ns)}
            self.assertEqual(aw.next_pair_file(pending, first, 1, True, seen), second)

    def test_resuming_saved_pair_waits_for_distinct_second_image(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "delivery.jpg", Path(directory) / "pr.jpg"
            first.write_bytes(b"delivery")
            second.write_bytes(b"pr")
            first_stat = first.stat()
            second_stat = second.stat()
            seen = {first: (first_stat.st_size, first_stat.st_mtime_ns)}
            pending = queue.Queue()
            pending.put(first)
            pending.put(second)
            companion = aw.resume_pending_pair(pending, first, first, 1, True, seen)
            self.assertEqual(companion, second)
            self.assertFalse(aw.same_path(first, companion))

    def test_resuming_saved_pair_without_second_image_keeps_wait_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "delivery.jpg"
            first.write_bytes(b"delivery")
            stat = first.stat()
            seen = {first: (stat.st_size, stat.st_mtime_ns)}
            pending = queue.Queue()
            pending.put(first)
            self.assertIsNone(aw.resume_pending_pair(pending, first, first, 1, True, seen))

    def test_missing_partner_saves_first_image_and_names_expected_document(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "request.jpg"
            Image.new("RGB", (16, 16)).save(image)
            root = Path(directory)
            state = root / ".autowatcher-pending-pair.json"
            args = argparse.Namespace(input=root, timeout=3)
            with patch.object(aw, "request_document_type", return_value={
                    "document_type": "pr", "reference_id": "PR-17"}):
                aw.report_missing_partner(image, args, "not-a-key", state)
            self.assertEqual(aw.load_pending_pair(state), [image])

    def test_pair_mismatch_asks_before_continue(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value="CO"):
            self.assertTrue(aw.confirm_pair_mismatch({"status": "mismatch", "summary": "Lệch số lượng.",
                                                       "rows": [{"status": "mismatch", "pr_index": 1,
                                                                 "delivery_index": 1, "note": "PR 5, giao 4."}]}))

    def test_batch_comparison_allows_one_pr_line_split_across_delivery_pages(self):
        pr, delivery = batch_items()
        comparison = {"status": "match", "summary": "Đủ số lượng.", "rows": [
            {"pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1", "DE2:1"],
             "status": "match", "note": "Giao hai lần, cộng đủ 10 kg."},
            {"pr_line_ids": ["PR1:2"], "delivery_line_ids": ["DE2:2"],
             "status": "match", "note": "Khớp."},
        ]}
        validated = aw.validate_batch_comparison(comparison, pr, delivery)
        self.assertEqual(len(validated["rows"]), 2)
        pair = aw.batch_pair_analysis(validated, pr, delivery)
        self.assertEqual(pair["status"], "match")
        self.assertEqual(sorted(row["delivery_index"] for row in pair["rows"]), [1, 2, 3])

    def test_batch_comparison_forces_mismatch_when_aggregate_quantity_differs(self):
        pr, delivery = batch_items()
        delivery[1]["quantity"] = "3"
        delivery[1]["received_quantity"] = "3"
        comparison = {"status": "match", "summary": "AI nghĩ là khớp.", "rows": [
            {"pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1", "DE2:1"],
             "status": "match", "note": ""},
            {"pr_line_ids": ["PR1:2"], "delivery_line_ids": ["DE2:2"],
             "status": "match", "note": ""},
        ]}
        validated = aw.validate_batch_comparison(comparison, pr, delivery)
        self.assertEqual(validated["status"], "mismatch")
        self.assertIn("10", validated["rows"][0]["note"])
        self.assertIn("9", validated["rows"][0]["note"])

    def test_batch_comparison_uses_actual_received_quantity_when_present(self):
        pr, delivery = batch_items()
        pr[0]["quantity"] = "5"
        delivery[0]["quantity"] = "5"
        delivery[0]["received_quantity"] = "4.2"
        comparison = {"status": "match", "summary": "Khớp.", "rows": [
            {"pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1"],
             "status": "match", "note": ""},
            {"pr_line_ids": ["PR1:2"], "delivery_line_ids": ["DE2:1", "DE2:2"],
             "status": "match", "note": ""},
        ]}
        validated = aw.validate_batch_comparison(comparison, pr, delivery)
        self.assertEqual(validated["status"], "mismatch")
        self.assertIn("PR 5, phiếu giao 4.2", validated["rows"][0]["note"])

    def test_batch_comparison_falls_back_to_ordered_quantity_when_received_blank(self):
        _, delivery = batch_items()
        delivery[0]["received_quantity"] = ""
        self.assertEqual(aw.delivery_quantity_for_compare(delivery[0]), 6)

    def test_delivery_only_batch_skips_pr_comparison_and_still_writes_review_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_path = root / "analysis.json"
            image = Path("delivery-only.jpg")
            entry = {"path": str(image), "document": {"document_type": "delivery",
                     "reference_id": "", "supplier_name": "NCC", "items": [{
                         "item_name": "Đu đủ xanh", "english_name": "Green papaya",
                         "vietnamese_name": "Đu đủ xanh", "catalog_code": "", "quantity": "3",
                         "received_quantity": "3", "unit_price": "15000", "unit": "kg",
                         "specification": "", "group_id": "1410"}]}}
            args = argparse.Namespace(timeout=5, output=root)
            with (patch.object(aw, "read_batch_documents", return_value=[entry]),
                  patch.object(aw, "batch_analysis_cache_path", return_value=cache_path),
                  patch.object(aw, "resolve_batch_items", return_value=({"items": [
                      {"line_id": "DE1:1", "invoice_name": "Đu đủ xanh"}]}, [])) as resolve,
                  patch.object(aw, "request_batch_comparison") as compare,
                  patch.object(aw, "validate_rows", return_value=[["row"]]),
                  patch.object(aw, "write_result") as write,
                  patch.object(aw, "report_batch_mismatch") as report,
                  patch.object(aw.sys.stdin, "isatty", return_value=False),
                  patch.object(aw, "create_delivery_workbook") as create_delivery):
                output = aw.process_batch(root, args, "key", self.catalog, {}, [],
                                          image_paths=[image], batch_label="Delivery without PR")
            self.assertEqual(output.name, "TongHop_" + aw.datetime.now().strftime("%Y-%m-%d") + ".xlsx")
            self.assertEqual(resolve.call_args.args[3], [])
            compare.assert_not_called()
            write.assert_called_once()
            report.assert_not_called()
            create_delivery.assert_not_called()

    def test_review_only_batch_skips_final_delivery_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_path = root / "analysis.json"
            image = Path("delivery-review-only.jpg")
            entry = {"path": str(image), "document": {"document_type": "delivery",
                     "reference_id": "", "supplier_name": "NCC", "items": [{
                         "item_name": "Banana", "english_name": "Banana", "vietnamese_name": "Chuối",
                         "catalog_code": "", "quantity": "2", "received_quantity": "2",
                         "unit_price": "1000", "unit": "kg", "specification": "", "group_id": ""}]}}
            args = argparse.Namespace(timeout=5, output=root, review_only=True)
            with (patch.object(aw, "read_batch_documents", return_value=[entry]),
                  patch.object(aw, "batch_analysis_cache_path", return_value=cache_path),
                  patch.object(aw, "resolve_batch_items", return_value=({"items": [
                      {"line_id": "DE1:1", "invoice_name": "Banana"}]}, [])),
                  patch.object(aw, "validate_rows", return_value=[["row"]]),
                  patch.object(aw, "write_result"),
                  patch.object(aw, "create_delivery_workbook") as create_delivery,
                  patch.object(aw.sys.stdin, "isatty", return_value=True),
                  patch("builtins.input") as input_prompt):
                aw.process_batch(root, args, "key", self.catalog, {}, [], image_paths=[image])
            create_delivery.assert_not_called()
            input_prompt.assert_not_called()

    def test_delivery_only_batch_refuses_to_combine_different_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = [
                {"path": "GH_01.jpg", "document": {"document_type": "delivery",
                 "reference_id": "PO-01", "supplier_name": "NCC", "items": []}},
                {"path": "GH_02.jpg", "document": {"document_type": "delivery",
                 "reference_id": "PO-02", "supplier_name": "NCC", "items": []}},
            ]
            args = argparse.Namespace(timeout=5, output=root)
            with patch.object(aw, "read_batch_documents", return_value=documents):
                with self.assertRaisesRegex(ValueError, "nhiều mã tham chiếu khác nhau"):
                    aw.process_batch(root, args, "key", self.catalog, {}, [],
                                     image_paths=[Path("GH_01.jpg"), Path("GH_02.jpg")],
                                     batch_label="Delivery only")

    def test_twenty_one_line_pr_split_across_two_images_is_collected(self):
        first = [{"item_name": f"PR item {index}", "catalog_code": "", "quantity": "1",
                  "received_quantity": "", "unit": "kg", "specification": "", "group_id": ""}
                 for index in range(1, 15)]
        second = [{"item_name": f"PR item {index}", "catalog_code": "", "quantity": "1",
                   "received_quantity": "", "unit": "kg", "specification": "", "group_id": ""}
                  for index in range(15, 22)]
        documents = [{"path": "IMG_3908.JPG", "document": {"document_type": "pr", "items": first}},
                     {"path": "IMG_3915.JPG", "document": {"document_type": "pr", "items": second}}]
        items = aw.flatten_batch_items(documents, "pr")
        self.assertEqual(len(items), 21)
        self.assertEqual(items[-1]["item_name"], "PR item 21")

    def test_root_done_marker_selects_batch_mode_and_watcher_queues_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("IMG_3908.JPG", "IMG_3915.JPG", "IMG_3905.JPG"):
                Image.new("RGB", (16, 16)).save(root / name)
            marker = root / aw.BATCH_MARKER
            self.assertFalse(aw.uses_batch_mode(root))
            marker.write_text("", encoding="utf-8")
            self.assertTrue(aw.uses_batch_mode(root))
            pending = queue.Queue()
            handler = aw.BatchDoneHandler(pending, root)
            handler.on_any_event(FileCreatedEvent(str(marker)))
            self.assertEqual(pending.get_nowait(), root)

    def test_flat_localsend_batch_skips_previously_processed_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, third = [root / name for name in
                                    ("IMG_3908.JPG", "IMG_3915.JPG", "IMG_3905.JPG")]
            first.write_bytes(b"pr page one")
            second.write_bytes(b"pr page two")
            third.write_bytes(b"delivery")
            with patch.object(aw, "wait_ready"):
                images, fingerprints = aw.pending_flat_images(root, {})
                self.assertEqual(len(images), 3)
                state = root / ".autowatcher-processed-images.json"
                aw.save_processed_images(state, fingerprints)
                self.assertEqual(aw.load_processed_images(state), fingerprints)
                self.assertEqual(aw.pending_flat_images(root, fingerprints)[0], [])
                first.write_bytes(b"updated delivery")
                pending, changed = aw.pending_flat_images(root, fingerprints)
            self.assertEqual(pending, [first])
            self.assertNotEqual(changed[first.name], fingerprints[first.name])

    def test_flat_localsend_reprocess_flag_queues_already_processed_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "delivery.jpg"
            image.write_bytes(b"same scan")
            processed = {image.name: aw.image_fingerprint(image)}
            with patch.object(aw, "wait_ready"):
                normal, _ = aw.pending_flat_images(root, processed)
                forced, fingerprints = aw.pending_flat_images(root, processed, reprocess=True)
            self.assertEqual(normal, [])
            self.assertEqual(forced, [image])
            self.assertEqual(fingerprints[image.name], processed[image.name])

    def test_flat_batch_key_is_stable_and_unique_per_send(self):
        first = aw.flat_batch_key({"PR.jpg": "aaa", "GH.jpg": "bbb"}, "PR 08")
        same = aw.flat_batch_key({"GH.jpg": "bbb", "PR.jpg": "aaa"}, "PR 08")
        changed = aw.flat_batch_key({"PR.jpg": "aaa", "GH.jpg": "ccc"}, "PR 08")
        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)
        self.assertTrue(first.stem.startswith("PR 08_"))

    def test_batch_reader_submits_and_reports_every_image(self):
        paths = [Path("PR_01.jpg"), Path("PR_02.jpg"), Path("GH_01.jpg")]
        def extract(path, *_):
            kind = "delivery" if path.name.startswith("GH") else "pr"
            return {"path": str(path), "document": {"document_type": kind}}
        with patch.object(aw, "extract_batch_document", side_effect=extract) as request:
            with self.assertLogs(level="INFO") as captured:
                documents = aw.read_batch_documents(paths, None, "key", {})
        self.assertEqual(request.call_count, 3)
        self.assertEqual(len(documents), 3)
        for path in paths:
            self.assertTrue(any(f"/3: {path.name}" in line for line in captured.output))
        self.assertEqual(sum("Đã đọc ảnh" in line for line in captured.output), 3)

    def test_batch_reader_attempts_remaining_images_after_one_ocr_failure(self):
        paths = [Path("PR_01.jpg"), Path("PR_02.jpg"), Path("GH_01.jpg")]
        def extract(path, *_):
            if path.name == "PR_02.jpg":
                raise ValueError("OCR failed")
            return {"path": str(path), "document": {"document_type": "delivery"}}
        with patch.object(aw, "extract_batch_document", side_effect=extract) as request:
            with self.assertRaisesRegex(ValueError, "PR_02.jpg"):
                aw.read_batch_documents(paths, None, "key", {})
        self.assertEqual(request.call_count, 3)

    def test_localsend_enter_processes_new_root_images_once_then_skips_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (("PR_01.jpg", b"pr1"), ("PR_02.jpg", b"pr2"), ("GH_01.jpg", b"delivery")):
                (root / name).write_bytes(data)
            args = argparse.Namespace(input=root, output=root, once=False)
            with (patch.object(sys.stdin, "isatty", return_value=True),
                  patch("builtins.input", side_effect=["PR 08", "", KeyboardInterrupt]),
                  patch.object(aw, "wait_ready"),
                  patch.object(aw, "process_batch", return_value=root / "TongHop.xlsx") as process):
                self.assertEqual(aw.run_flat_batch_mode(args, "key", {}, {}, []), 0)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(len(process.call_args.kwargs["image_paths"]), 3)
            self.assertEqual(process.call_args.kwargs["batch_label"], "PR 08")
            self.assertTrue(process.call_args.kwargs["image_key"].stem.startswith("LocalSend_"))
            state = aw.load_processed_images(root / ".autowatcher-processed-images.json")
            self.assertEqual(set(state), {"PR_01.jpg", "PR_02.jpg", "GH_01.jpg"})

    def test_batch_comparison_rejects_missing_or_duplicate_line_ids(self):
        pr, delivery = batch_items()
        comparison = {"status": "match", "summary": "", "rows": [
            {"pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1"],
             "status": "match", "note": ""},
            {"pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE2:1", "DE2:2"],
             "status": "match", "note": ""},
        ]}
        with self.assertRaises(ValueError):
            aw.validate_batch_comparison(comparison, pr, delivery)

    def test_batch_pair_analysis_marks_reference_mismatch(self):
        pr, delivery = batch_items()
        comparison = {"status": "match", "summary": "Khớp.", "rows": [
            {"pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1", "DE2:1"],
             "status": "match", "note": ""},
            {"pr_line_ids": ["PR1:2"], "delivery_line_ids": ["DE2:2"],
             "status": "match", "note": ""},
        ]}
        pair = aw.batch_pair_analysis(comparison, pr, delivery, refs_mismatch=True)
        self.assertEqual(pair["status"], "mismatch")
        self.assertTrue(pair["reference_mismatch"])

    def test_batch_document_requires_items_and_preserves_document_metadata(self):
        document = {"document_type": "delivery", "reference_id": "PR-001",
                    "supplier_name": "NCC", "items": [{"item_name": "Chuối cau",
                    "english_name": "Finger banana", "vietnamese_name": "Chuối cau",
                    "catalog_code": "", "quantity": "2", "unit_price": "25000", "unit": "kg",
                    "received_quantity": "1.5", "specification": "", "group_id": "1410"}]}
        self.assertEqual(aw.validate_batch_document(document)["reference_id"], "PR-001")
        invalid = dict(document, items=[])
        with self.assertRaises(ValueError):
            aw.validate_batch_document(invalid)

    def test_batch_signature_changes_when_new_page_is_added(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory) / "PR-001"
            batch.mkdir()
            Image.new("RGB", (16, 16)).save(batch / "page1.jpg")
            (batch / "_DONE").write_text("", encoding="utf-8")
            before = aw.batch_signature(batch)
            Image.new("RGB", (16, 16)).save(batch / "page2.jpg")
            after = aw.batch_signature(batch)
            self.assertNotEqual(before, after)

    def test_names_valid_and_collision_resistant(self):
        paths = [Path("a" * 50 + "1.jpg"), Path("a" * 50 + "2.jpg"),
                 Path("same.jpg"), Path("same.png"), Path("'name[1]'.jpg")]
        names = [aw.sheet_name(p) for p in paths]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(len(name) <= 31 for name in names))
        self.assertTrue(all(not any(c in name for c in "[]:*?/\\") for name in names))

    def test_export_preserves_other_sheets_text_and_percent(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "TongHop.xlsx"
            wb = Workbook()
            wb.active["A1"] = "User data to preserve"
            wb.save(output)
            wb.close()
            first = Path("image1.jpg")
            rows = aw.validate_rows(payload(name="=HYPERLINK(\"https://example.com\")"), self.catalog)
            aw.write_result(output, first, rows)
            aw.write_result(output, Path("image2.jpg"), rows)
            aw.write_result(output, first, rows)
            wb = load_workbook(output)
            try:
                self.assertEqual(wb["Sheet"]["A1"].value, "User data to preserve")
                self.assertEqual(len(wb.sheetnames), 3)
                sheet = wb[aw.sheet_name(first)]
                self.assertEqual(sheet["A2"].data_type, "s")
                self.assertEqual(sheet["B2"].value, "001")
                self.assertEqual(sheet["E2"].value, .91)
                self.assertEqual(sheet["E2"].number_format, "0%")
                self.assertEqual(sheet.max_row, 2)
            finally:
                wb.close()

    def test_tonghop_write_creates_recoverable_backup_and_restores_deleted_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TongHop_2026-11-02.xlsx"
            backup = aw.tonghop_backup_path(report)
            rows = aw.validate_rows(payload(), self.catalog)
            aw.write_result(report, Path("image1.jpg"), rows)
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_bytes(), report.read_bytes())
            report.unlink()
            self.assertTrue(aw.restore_tonghop_backup(report))
            self.assertTrue(report.is_file())
            restored = load_workbook(report, read_only=True, data_only=True)
            try:
                self.assertEqual(restored.worksheets[0]["B2"].value, "001")
            finally:
                restored.close()

    def test_restore_tonghop_backup_does_not_overwrite_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TongHop_2026-11-02.xlsx"
            aw.write_result(report, Path("image1.jpg"), aw.validate_rows(payload(), self.catalog))
            original = report.read_bytes()
            report.write_bytes(b"new user data")
            self.assertFalse(aw.restore_tonghop_backup(report))
            self.assertEqual(report.read_bytes(), b"new user data")
            self.assertNotEqual(report.read_bytes(), original)

    def test_failed_replace_does_not_damage_old_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "TongHop.xlsx"
            rows = aw.validate_rows(payload(), self.catalog)
            aw.write_result(output, Path("image1.jpg"), rows)
            before = output.read_bytes()
            with patch.object(aw.os, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    aw.write_result(output, Path("image2.jpg"), rows)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(list(Path(directory).glob("*.xlsx")), [output])

    def test_cache_allows_retry_after_output_is_locked_without_api_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "test.jpg"
            Image.new("RGB", (40, 50)).save(image)
            args = argparse.Namespace(excel=SOURCE, output=root, timeout=3)
            catalog = aw.load_catalog(SOURCE)
            code = next(iter(catalog))
            response = payload(code=code)
            response["extracted"] = {"supplier_name": "", "items": [{"invoice_name": "Chuối cau", "group_id": ""}]}
            with (patch.object(aw, "wait_ready"), patch.object(aw, "enrich_report_rows"),
                  patch.object(aw, "request_items", return_value=response) as api):
                with patch.object(aw, "write_result", side_effect=PermissionError("locked")):
                    with self.assertRaises(PermissionError):
                        aw.process_image(image, args, "not-a-key")
                output = aw.process_image(image, args, "not-a-key")
                self.assertTrue(output.exists())
                self.assertEqual(api.call_count, 1)

    def test_watch_events_handle_renames_but_ignore_non_images(self):
        pending = queue.Queue()
        handler = aw.PhieuGiaoHandler(pending)
        handler.on_any_event(FileCreatedEvent("file.txt"))
        handler.on_any_event(FileModifiedEvent("new.JPG"))
        handler.on_any_event(FileMovedEvent("upload.tmp", "complete.HEIC"))
        self.assertEqual([pending.get_nowait(), pending.get_nowait()], [Path("new.JPG"), Path("complete.HEIC")])
        self.assertTrue(pending.empty())

    def test_compressed_image_is_jpeg_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "test.png"
            Image.new("RGBA", (3000, 4000), (1, 2, 3, 0)).save(image)
            encoded = aw.prepare_image(image, image.read_bytes())
            with Image.open(io.BytesIO(encoded)) as converted:
                self.assertEqual(converted.format, "JPEG")
                self.assertLessEqual(max(converted.size), 2400)


class SupplierRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.groups = aw.load_catalog_data(SOURCE)
        cls.rules = sr.read_rules(PROJECT_ROOT / "NhaCungCap.json", cls.catalog, cls.groups)

    def extraction(self, name="Thanh long ĐP", supplier="TRÁI CÂY ĐỨC TÚ", group="1410"):
        return {"supplier_name": supplier, "items": [{"invoice_name": name, "group_id": group}]}

    def plans(self, **kwargs):
        return sr.build_plans(self.extraction(**kwargs), self.catalog, self.groups, self.rules)

    def test_match_supplier_accents_case_but_not_partial_or_recipient(self):
        self.assertEqual(sr.find_supplier("trai cay DUC TU", self.rules)["id"], "duc_tu")
        self.assertIsNone(sr.find_supplier("AMERYS", self.rules))
        self.assertIsNone(sr.find_supplier("Đức Tú và đối tác", self.rules))

    def test_catalog_first_search_includes_all_dragon_product_forms(self):
        plan = self.plans(name="Thanh long")[0]
        candidates = aw.candidate_groups(["Thanh long"], plan["catalog"])[0]["candidates"]
        self.assertTrue({"11410050", "11410051", "11420010", "11640056", "11920029"} <= {row[0] for row in candidates})

    def test_confirmed_alias_overrides_ai_and_ambiguity(self):
        plan = self.plans(name="THANH LONG dp")
        data = payload(name="THANH LONG dp", code="11410051", review=True)
        row = aw.validate_rows(data, self.catalog, plan, self.groups)[0]
        self.assertEqual(row[1], "11410050")
        self.assertIsNone(row[4])
        self.assertEqual(row[7], "Đức Tú")
        self.assertEqual(row[9], "Quy đổi đã xác nhận")

    def test_confirmed_alias_does_not_apply_to_other_suppliers_or_names(self):
        self.assertEqual(self.plans(supplier="Other supplier")[0]["approved_code"], "")
        self.assertEqual(self.plans(name="Thanh long đỏ")[0]["approved_code"], "")
        self.assertEqual(self.plans(name="Nước ép thanh long")[0]["approved_code"], "")

    def test_plain_dragon_remains_ambiguous_between_fresh_varieties(self):
        plans = self.plans(name="Thanh long")
        row = aw.validate_rows(payload(name="Thanh long", code="11410050", confidence=85),
                                self.catalog, plans, self.groups)[0]
        self.assertEqual(row[1], "CHUA CO MA")
        self.assertIn("11410050", row[6])
        self.assertIn("11410051", row[6])
        self.assertIn("11420010", row[6])

    def test_juice_category_conflict_cannot_be_forced_to_fresh(self):
        plans = self.plans(name="Nước ép thanh long", group="1920")
        self.assertFalse(plans[0]["conflict"])
        self.assertEqual(set(plans[0]["catalog"]), set(self.catalog))
        row = aw.validate_rows(payload(name="Nước ép thanh long", code="11410050"),
                               self.catalog, plans, self.groups)[0]
        self.assertEqual(row[1], "CHUA CO MA")
        self.assertEqual(row[5], "CẦN KIỂM TRA")

    def test_unknown_supplier_uses_category_and_never_gets_a_learned_alias(self):
        plans = self.plans(supplier="New supplier", name="Thanh long khô", group="1420")
        self.assertFalse(plans[0]["supplier_known"])
        self.assertEqual(plans[0]["approved_code"], "")
        self.assertIn("11420010", plans[0]["catalog"])
        self.assertIn("11410050", plans[0]["catalog"])

    def test_catalog_product_can_be_selected_outside_supplier_historical_group(self):
        plans = self.plans(name="Thanh long khô")
        row = aw.validate_rows(payload(name="Thanh long khô", code="11420010"),
                               self.catalog, plans, self.groups)[0]
        self.assertEqual(row[1], "11420010")
        self.assertEqual(row[8], self.groups['11420010'][1])

    def test_missing_group_does_not_limit_catalog_to_supplier_scope(self):
        plan = self.plans(name="Thanh long", group="")[0]
        self.assertEqual(plan["group_ids"], set())
        self.assertEqual(set(plan['catalog']), set(self.catalog))

    def test_unknown_group_id_is_rejected(self):
        with self.assertRaises(ValueError):
            self.plans(group="invented")

    def test_written_confirmed_row_has_supplier_group_and_source_without_fake_ai_score(self):
        plans = self.plans()
        rows = aw.validate_rows(payload(name="Thanh long ĐP", code="11410050"), self.catalog, plans, self.groups)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "TongHop.xlsx"
            aw.write_result(output, Path("duc_tu.jpg"), rows)
            wb = load_workbook(output, read_only=True, data_only=True)
            try:
                sheet = wb.worksheets[0]
                self.assertEqual(sheet.max_column, 20)
                self.assertEqual(sheet["B2"].value, "11410050")
                self.assertIsNone(sheet["E2"].value)
                self.assertEqual(sheet["H2"].value, "Đức Tú")
                self.assertEqual(sheet["I2"].value, "Trái Cây Tươi Sống")
                self.assertEqual(sheet["J2"].value, "Quy đổi đã xác nhận")
                self.assertEqual(sheet["K1"].value, "Đối chiếu PR")
                self.assertEqual(sheet["L1"].value, "Chi tiết đối chiếu PR")
                self.assertEqual([sheet.cell(1, column).value for column in range(13, 17)],
                                 ["Số lượng", "Thực nhận", "Đơn giá", "Thành tiền"])
                self.assertEqual(sheet["P1"].value, "Thành tiền")
            finally:
                wb.close()

    def test_modified_rules_invalidate_cache(self):
        import copy
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "test.jpg"
            Image.new("RGB", (40, 50)).save(image)
            rules_file = root / "NhaCungCap.json"
            rules_file.write_text(json.dumps(self.rules), encoding="utf-8")
            args = argparse.Namespace(excel=SOURCE, output=root, timeout=3, rules=rules_file)
            response = payload(name="Thanh long ĐP", code="11410051")
            response["extracted"] = self.extraction()
            with (patch.object(aw, "wait_ready"), patch.object(aw, "enrich_report_rows"),
                  patch.object(aw, "request_items", return_value=response) as api):
                aw.process_image(image, args, "not-a-key")
                aw.process_image(image, args, "not-a-key")
                self.assertEqual(api.call_count, 1)
                changed = copy.deepcopy(self.rules)
                changed["suppliers"][0]["confirmed_items"][0]["catalog_code"] = "11410051"
                rules_file.write_text(json.dumps(changed), encoding="utf-8")
                output = aw.process_image(image, args, "not-a-key")
                self.assertEqual(api.call_count, 2)
            wb = load_workbook(output, read_only=True, data_only=True)
            try:
                self.assertEqual(wb.worksheets[0]["B2"].value, "11410051")
            finally:
                wb.close()

    def test_invalid_confirmed_rules_stop_instead_of_guessing(self):
        import copy
        for mutation in ["missing_code", "duplicate_alias", "duplicate_item", "unknown_group"]:
            rules = copy.deepcopy(self.rules)
            supplier = rules["suppliers"][0]
            if mutation == "missing_code":
                supplier["confirmed_items"][0]["catalog_code"] = "not-in-catalog"
            elif mutation == "duplicate_alias":
                other = copy.deepcopy(supplier)
                other["id"] = "other"
                rules["suppliers"].append(other)
            elif mutation == "duplicate_item":
                supplier["confirmed_items"].append(supplier["confirmed_items"][0])
            else:
                supplier["allowed_group_ids"] = ["9999"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                sr.validate_rules(rules, self.catalog, self.groups)


if __name__ == "__main__":
    unittest.main(verbosity=2)

