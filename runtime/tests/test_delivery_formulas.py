import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import AutoWatcher as aw
from delivery_export import HEADERS as DELIVERY_HEADERS


def make_delivery(path):
    wb = Workbook()
    for index in range(2):
        sheet = wb.active if index == 0 else wb.create_sheet()
        sheet.title = str(index + 1)
        sheet.append(["Mã hàng", "Tên mặt hàng", "Đvt", "Mã kho", "Số lượng", "Thực nhận", "Giá", "Tiền hàng"])
        sheet.append(["", "Hàng chưa mã", "kg", None, 5, 4.2, 25000, 125000])
        sheet.append(["", "Không nhận", "kg", None, 5, 0, 25000, 125000])
        sheet["H8"] = "Không phải dòng hàng"
        sheet["F2"].font = Font(bold=True)
        sheet.freeze_panes = "C2"
    wb.save(path)
    wb.close()


class DeliveryFormulaTests(unittest.TestCase):
    def test_upgrade_preserves_user_values_styles_and_only_changes_item_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Delivery.xlsx"
            make_delivery(path)
            self.assertTrue(aw.upgrade_delivery_workbook(path))
            wb = load_workbook(path)
            for sheet in wb:
                self.assertEqual(sheet["H2"].value, "=F2*G2")
                self.assertEqual(sheet["H3"].value, "=F3*G3")
                self.assertEqual(sheet["F2"].value, 4.2)
                self.assertEqual(sheet["G2"].value, 25000)
                self.assertEqual(sheet["F3"].value, 0)
                self.assertTrue(sheet["F2"].font.bold)
                self.assertEqual((sheet["F2"].font.name, sheet["F2"].font.sz), ("Calibri", 11))
                self.assertEqual(sheet.freeze_panes, "C2")
                self.assertEqual(sheet["H8"].value, "Không phải dòng hàng")
            self.assertEqual(wb.calculation.calcMode, "auto")
            wb.close()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertFalse(aw.upgrade_delivery_workbook(path))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_reusing_old_export_upgrades_same_file_and_its_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "TongHop.xlsx"
            wb = Workbook()
            wb.save(report)
            wb.close()
            path = root / "Phieu giao hang ngay 01.xlsx"
            make_delivery(path)
            aw.backup_delivery_workbook(path, report)
            existing = aw.restore_delivery_backup(root, report)
            self.assertEqual(existing, path)
            self.assertFalse((root / "Phieu giao hang ngay 02.xlsx").exists())
            backup = aw.delivery_backup_directory(root) / path.name
            self.assertEqual(path.read_bytes(), backup.read_bytes())
            wb = load_workbook(backup)
            self.assertEqual(wb["1"]["H2"].value, "=F2*G2")
            wb.close()
            path.unlink()
            restored = aw.restore_delivery_backup(root, report)
            self.assertEqual(restored.read_bytes(), backup.read_bytes())

    def test_locked_old_export_is_preserved_during_formula_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Delivery.xlsx"
            make_delivery(path)
            before = path.read_bytes()
            with patch.object(aw.os, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    aw.upgrade_delivery_workbook(path)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_master_template_does_not_silently_use_old_monthly_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "Thang 10" / "Ngay 31" / "Phieu giao hang ngay 31.xlsx"
            old.parent.mkdir(parents=True)
            make_delivery(old)
            with self.assertRaisesRegex(FileNotFoundError, "Phieu giao hang ngay X.xlsx"):
                aw.delivery_template_path(root / "Thang 11" / "Ngay 02")

    def test_fixed_template_font_override_preserves_header_emphasis_layout_and_formulas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "Phieu giao hang ngay X.xlsx"
            wb = Workbook()
            wb.active.append(DELIVERY_HEADERS)
            wb.save(template)
            wb.close()
            wb = load_workbook(template)
            for sheet in wb:
                sheet["F1"].font = Font(name="Arial", size=18, bold=True, color="123456")
                sheet["F2"].font = Font(name="Verdana", size=8, italic=True)
                sheet.column_dimensions["F"].width = 65
                sheet["J2"].number_format = "#,##0"
            wb.save(template)
            wb.close()
            template_digest = hashlib.sha256(template.read_bytes()).hexdigest()
            report = root / "TongHop.xlsx"
            wb = Workbook()
            wb.active.append(aw.HEADERS)
            wb.active.append(["Tên trên phiếu", "CHUA CO MA", "Không xác định", "kg", .95,
                              "CẦN KIỂM TRA", "", "NCC", "", "", "", "", 5, 4.2, 25000, 125000])
            wb.save(report)
            wb.close()
            final = aw.create_delivery_workbook(report, {}, output_dir=root / "Thang 11" / "Ngay 02")
            wb = load_workbook(final)
            sheet = wb.worksheets[0]
            for row in sheet:
                for cell in row:
                    self.assertEqual((cell.font.name, cell.font.sz), ("Calibri", 11))
            self.assertTrue(sheet["F1"].font.bold)
            self.assertEqual(sheet["F1"].font.color.rgb, "00123456")
            self.assertTrue(sheet["F2"].font.italic)
            self.assertEqual(sheet.column_dimensions["F"].width, 65)
            self.assertEqual(sheet["J2"].number_format, "#,##0")
            self.assertEqual(sheet["K2"].value, "=I2*J2")
            self.assertEqual(len(wb.sheetnames), 1)
            wb.close()
            self.assertEqual(hashlib.sha256(template.read_bytes()).hexdigest(), template_digest)
