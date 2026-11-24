import unittest

from receiving_po_catalog import audit


class PurchaseOrderCatalogTests(unittest.TestCase):
    def test_known_code_uses_catalog_name_and_reports_differences(self):
        result = audit(
            dict(supplier='001234 - Tên trên PO', items=[
                dict(catalog_code='A01', item_name='Tên khác'),
                dict(catalog_code='A02', item_name='Hàng chưa có mã'),
            ]),
            {'A01': ('Tên chuẩn', 'Kg')},
            {'001234': 'Nhà cung cấp chuẩn'},
        )
        self.assertEqual(result['supplier'], 'Nhà cung cấp chuẩn')
        self.assertEqual(result['supplier_code'], '001234')
        self.assertEqual(result['supplier_on_po'], '001234 - Tên trên PO')
        self.assertEqual(len(result['warnings']), 3)
        self.assertIn('Tên chuẩn', result['warnings'][1])
        self.assertIn('A02 chưa có', result['warnings'][2])

    def test_unknown_branch_does_not_use_parent_supplier(self):
        result = audit(
            dict(supplier='1100790177 - 008 - Nhà cung cấp chi nhánh'),
            {},
            {'1100790177': 'Nhà cung cấp chính'},
        )
        self.assertEqual(result['supplier_code'], '1100790177-008')
        self.assertIn('chưa có trong DanhMucNCC', result['warnings'][0])
