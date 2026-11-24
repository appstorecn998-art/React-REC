import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

import server
from rec_supplier_reconciliation import SupplierResolver, reconciliation


class SupplierReconciliationTest(unittest.TestCase):
    def test_alias_preview_and_receipt_confirmation_preserve_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = Workbook()
            directory.active.title = 'DanhMucNCC'
            directory.active.append(['Mã nhà cung cấp', 'Tên nhà cung cấp', 'Mã số thuế'])
            directory.active.append(['A', 'Công ty Rau Xanh', '0123456789'])
            directory.active.append(['B', 'Công ty Trái Cây', '9876543210'])
            directory.save(root/'DanhMuc.xlsm')
            rule_file = root/'NhaCungCap.json'
            rule_file.write_text('{"supplier_aliases":[]}', encoding='utf-8')
            report = root/'report.xlsx'
            book = Workbook()
            book.remove(book.active)
            for name, vendor, tax in (
                ('known', 'Công ty Rau Xanh', ''),
                ('typo', 'Công ty Rau Xah', ''),
                ('other typo', 'Công ty Rau Xah', ''),
                ('tax', 'Rau xanh viết sai', '0123456789'),
                ('conflict', 'Công ty Trái Cây', '0123456789'),
            ):
                sheet = book.create_sheet(name)
                sheet.append(['Tên hàng trên phiếu (Ảnh)', 'Nhà cung cấp', 'Mã số thuế bên bán', 'Thực nhận', 'Đơn giá'])
                sheet.append(['Hàng', vendor, tax, 2, 1500])
            book.save(report)
            original = report.read_bytes()
            reports = {'2026-11-20': report}
            resolver = SupplierResolver(root, root)
            rows = {row['sheet']: row for row in resolver.receipts(reports)}
            self.assertEqual(rows['known']['supplier']['code'], 'A')
            self.assertEqual(rows['tax']['supplier']['code'], 'A')
            self.assertIsNone(rows['conflict']['supplier']['code'])
            self.assertIsNone(rows['typo']['supplier']['code'])
            self.assertEqual(rows['typo']['supplier']['candidates'][0]['code'], 'A')
            row = rows['typo']
            action = dict(id=row['id'], version=row['version'], code='A',
                          reason='Checked photocopy', alias=row['rawNames'][0])
            result = resolver.confirm(reports, action)
            self.assertFalse(result['saved'])
            self.assertEqual(len(result['affected']), 2)
            self.assertFalse(json.loads(rule_file.read_text())['supplier_aliases'])
            resolver = SupplierResolver(root, root)
            self.assertTrue(resolver.confirm(reports, dict(action, previewToken=result['previewToken']))['saved'])
            row = rows['conflict']
            resolver.confirm(reports, dict(id=row['id'], version=row['version'], code='B',
                                           reason='Checked original receipt'))
            data = reconciliation(root, root, reports, '2026-11')
            groups = {group['code']: group for group in data['suppliers']}
            self.assertEqual(groups['A']['provisional'], '12000')
            self.assertEqual(groups['B']['provisional'], '3000')
            self.assertEqual(report.read_bytes(), original)
