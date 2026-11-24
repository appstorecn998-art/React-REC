from datetime import date
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import server
import multi_delivery as md
from ocr_events import listener
from receiving_service import snapshot


class WebReceiptTests(unittest.TestCase):
    def test_hold_partial_then_save_full_invoice_then_hold_rephoto(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inbox = root / 'input'
            inbox.mkdir()
            report = root / 'TongHopPhieuNgay_21-11-2026.xlsx'
            documents = {}
            events = []
            token = listener.set(lambda stage, message, details: events.append((stage, details)))
            self.addCleanup(listener.reset, token)

            def photo(name, page):
                path = inbox / name
                path.write_bytes(name.encode())
                documents[hashlib.sha256(path.read_bytes()).hexdigest()] = {
                    'document_type': 'delivery', 'supplier_name': 'NCC A',
                    'document_date': '21/11/2026', 'reference_id': 'A-42',
                    'page_number': f'{page}/2', 'has_total': page == 2,
                    'printed_total': '330', 'printed_subtotal': '290',
                    'items': [{'source_stt': str(page), 'unit': 'kg', 'quantity': '2',
                               'unit_price': '75', 'line_amount': '145'}],
                }
                return path

            def rows_for(entries, *_):
                items = [dict(entry['document']['items'][0], source_image=Path(entry['path']).name)
                         for entry in entries]
                rows = []
                for item in items:
                    row = [''] * (len(md.aw.HEADERS) + len(md.aw.PR_HEADERS))
                    row[0] = 'Hàng A'
                    row[5] = 'CÓ TRONG DANH MỤC'
                    row[12:16] = [2, 1, 75, 145]
                    rows.append(row)
                return rows, items

            args = SimpleNamespace(input=inbox, output=root, excel=None, rules=None, timeout=10,
                                   receipt_date=date(2026, 11, 21), web_receipts=True,
                                   held_image_names=[], preclassified_documents=documents)
            last = photo('02.jpg', 2)
            with (patch.object(md, 'report_path', return_value=report),
                  patch.object(md.aw, 'load_catalog_data', return_value=({}, {})),
                  patch.object(md.aw, 'read_rules', return_value={}),
                  patch.object(md.aw, 'validate_batch_document'),
                  patch.object(md.aw, 'wait_ready'),
                  patch.object(md, 'load_warehouse_directory', return_value={}),
                  patch.object(md, 'enrich_rows'),
                  patch.object(md, 'read_invoice', side_effect=rows_for) as match):
                md.run(args, 'dummy')
                self.assertFalse(report.exists())
                self.assertEqual(events[-1][0], 'needs_pages')
                match.assert_not_called()

                args.held_image_names.clear()
                first = photo('01.jpg', 1)
                self.assertEqual(md.run(args, 'dummy'), 0)
                _, sheets = snapshot(report)
                self.assertEqual(len(sheets), 1)
                self.assertEqual(len(sheets[0][1]), 2)
                row = server.receipt_row(*sheets[0][1][0])
                self.assertEqual(row['Chênh lệch thực nhận'], -1)
                self.assertEqual(row['Thành tiền in trên phiếu'], 145)
                self.assertEqual(row['Tổng tiền in trên phiếu'], 330)
                self.assertEqual(row['Tiền hàng tính lại từ lượng giao'], 300)
                self.assertIn('Thành tiền in lệch', row['Ghi chú'])
                self.assertIn('tính lại lệch', row['Ghi chú'])

                args.held_image_names.clear()
                first.unlink()
                last.unlink()
                photo('03.jpg', 1)
                photo('04.jpg', 2)
                md.run(args, 'dummy')
                self.assertEqual(len(snapshot(report)[1]), 1)
                self.assertEqual(events[-1][0], 'suspected_duplicate')
                match.assert_called_once()


if __name__ == '__main__':
    unittest.main()
