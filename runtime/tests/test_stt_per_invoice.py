import unittest
from pathlib import Path
import sys
from openpyxl import Workbook, load_workbook
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_export import HEADERS, fill_flat_delivery

class SttPerInvoiceTests(unittest.TestCase):
    def test_all_rows_of_each_invoice_share_one_stt(self):
        wb = Workbook(); wb.active.append(HEADERS)
        rows = [
            dict(invoice_key='America', supplier_code='A', supplier_name='CÔNG TY AMERICA', delivery_date=None, code='', name='A1', unit='cái', received=1, unit_price=10),
            dict(invoice_key='America', supplier_code='A', supplier_name='CÔNG TY AMERICA', delivery_date=None, code='', name='A2', unit='cái', received=2, unit_price=20),
            dict(invoice_key='Sky', supplier_code='B', supplier_name='CÔNG TY SKY', delivery_date=None, code='', name='B1', unit='cái', received=3, unit_price=30),
            dict(invoice_key='Sky', supplier_code='B', supplier_name='CÔNG TY SKY', delivery_date=None, code='', name='B2', unit='cái', received=4, unit_price=40),
        ]
        sheet = fill_flat_delivery(wb, rows)
        self.assertEqual([sheet.cell(r,1).value for r in range(2,6)], [1,1,2,2])
        self.assertEqual([sheet.cell(r,6).value for r in range(2,6)], ['A1','A2','B1','B2'])
        wb.close()

    def test_same_supplier_different_invoice_keys_get_different_stt(self):
        wb = Workbook(); wb.active.append(HEADERS)
        rows = [dict(invoice_key='sheet-1', supplier_code='A', supplier_name='NCC', delivery_date=None, code='', name='A', unit='cái', received=1, unit_price=1),
                dict(invoice_key='sheet-2', supplier_code='A', supplier_name='NCC', delivery_date=None, code='', name='B', unit='cái', received=1, unit_price=1)]
        sheet = fill_flat_delivery(wb, rows)
        self.assertEqual([sheet.cell(r,1).value for r in (2,3)], [1,2])
        wb.close()
