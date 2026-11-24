import unittest
from datetime import date
from pathlib import Path
import sys
from openpyxl import Workbook, load_workbook
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_export import HEADERS, VIETNAMESE_DATE_FORMAT, fill_flat_delivery

class VietnameseDateFormatTests(unittest.TestCase):
    def test_date_is_typed_and_forced_to_vietnamese_day_month_year_display(self):
        wb = Workbook(); wb.active.append(HEADERS)
        sheet = fill_flat_delivery(wb,[dict(invoice_key='x', supplier_code='', supplier_name='NCC',
            delivery_date=date(2026,11,2), code='', name='Hàng', unit='cái', received=1, unit_price=2)])
        self.assertEqual(sheet['D2'].value, date(2026,11,2))
        self.assertEqual(sheet['D2'].number_format, VIETNAMESE_DATE_FORMAT)
        self.assertIn('dd/mm/yyyy', sheet['D2'].number_format)
        wb.close()
