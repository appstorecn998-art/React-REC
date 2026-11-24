import hashlib
import json
from datetime import date, datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import AutoWatcher as aw
from delivery_export import HEADERS, DELIVERY_DATE_PROMPT, fill_flat_delivery, parse_delivery_date
from supplier_directory import load_supplier_directory, supplier_aliases, resolve_supplier

SKY = 'CÔNG TY TNHH SẢN XUẤT TM THIẾT BỊ SKY'
CODE = '0312281677'


def inputs(root):
    template = root / 'template.xlsx'
    wb = Workbook()
    wb.active.append(HEADERS)
    wb.active.column_dimensions['C'].width = 65
    wb.active['F2'] = 'Dữ liệu mẫu cần xóa'
    wb.create_sheet('Mẫu phụ')
    wb.save(template)
    wb.close()
    directory = root / 'catalog.xlsx'
    wb = Workbook()
    wb.active.title = 'DanhMucNCC'
    wb.active.append(['Mã nhà cung cấp', 'Tên nhà cung cấp'])
    wb.active.append([CODE, SKY])
    wb.save(directory)
    wb.close()
    rules = root / 'rules.json'
    rules.write_text(json.dumps({'supplier_aliases': [{'invoice_name': 'Thiết bị sky',
                                                      'supplier_code': CODE}]}), encoding='utf-8')
    report = root / 'TongHop.xlsx'
    wb = Workbook()
    for index in range(2):
        sheet = wb.active if index == 0 else wb.create_sheet()
        sheet.append(aw.HEADERS)
        sheet.append(['Ống hút', 'CHUA CO MA', '', 'cái', .95, 'CẦN KIỂM TRA', '',
                      'Thiết bị sky', '', '', '', '', 10, 0 if index == 0 else 4.2,
                      25000, 250000, f'2026-11-0{index+1}'])
    wb.save(report)
    wb.close()
    return template, directory, rules, report


class SupplierFlatTests(unittest.TestCase):
    def test_export_combines_duplicate_items_keeps_actual_zero_dates_text_codes_and_formulas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, catalog, rules, report = inputs(root)
            source_hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (template, catalog, report)]
            output = aw.create_delivery_workbook(report, {}, template, root / 'output',
                                                 excel_path=catalog, rules_path=rules)
            wb = load_workbook(output)
            self.assertEqual(wb.sheetnames, ['1'])
            sheet = wb.active
            self.assertEqual([sheet.cell(r, 1).value for r in (2, 3)], [1, 2])
            self.assertEqual([sheet.cell(r, 9).value for r in (2, 3)], [0, 4.2])
            self.assertEqual(sheet['B2'].value, CODE)
            self.assertEqual(sheet['B2'].data_type, 's')
            self.assertEqual(sheet['C2'].value, SKY)
            self.assertEqual(sheet['D2'].value, datetime(2026, 11, 1))
            self.assertEqual(sheet['D3'].value, datetime(2026, 11, 2))
            self.assertIsNone(sheet['E2'].value)
            self.assertEqual(sheet['F2'].value, sheet['F3'].value)
            self.assertEqual(sheet['K2'].value, '=I2*J2')
            self.assertEqual(sheet['K3'].value, '=I3*J3')
            self.assertEqual(sheet.column_dimensions['C'].width, 65)
            self.assertEqual(wb.calculation.calcMode, 'auto')
            wb.close()
            self.assertEqual(source_hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (template, catalog, report)])

    def test_repeat_preserves_manual_edits_and_restore_then_rule_change_creates_new_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, catalog, rules, report = inputs(root)
            kwargs = dict(template_path=template, output_dir=root/'output', excel_path=catalog, rules_path=rules)
            output = aw.create_delivery_workbook(report, {}, **kwargs)
            wb = load_workbook(output)
            wb.active['I2'] = 3
            wb.save(output)
            wb.close()
            self.assertEqual(aw.create_delivery_workbook(report, {}, **kwargs), output)
            output.unlink()
            self.assertEqual(aw.create_delivery_workbook(report, {}, **kwargs), output)
            wb = load_workbook(output)
            self.assertEqual(wb.active['I2'].value, 3)
            wb.close()
            rules.write_text('{"supplier_aliases":[]}', encoding='utf-8')
            self.assertEqual(aw.create_delivery_workbook(report, {}, **kwargs), output)
            wb = load_workbook(output)
            self.assertEqual(wb.active['B2'].value, CODE)
            wb.close()

    def test_old_backup_without_layout_is_not_reused_as_new_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, catalog, rules, report = inputs(root)
            output = root/'output'
            backup = aw.delivery_backup_directory(output)
            backup.mkdir(parents=True)
            old = backup/'Phieu giao hang ngay 01.xlsx'
            old.write_bytes(b'old-format')
            aw.delivery_backup_metadata_path(old).write_text(json.dumps({'tonghop_sha256':aw.delivery_report_digest(report)}))
            self.assertIsNone(aw.find_delivery_backup_for_report(output, report))
            result = aw.create_delivery_workbook(report, {}, template, output, excel_path=catalog, rules_path=rules)
            self.assertNotEqual(result.read_bytes(), b'old-format')

    def test_supplier_alias_exact_core_ambiguous_unknown_and_prefix_remain_distinct(self):
        directory = {CODE: SKY, '2': 'CÔNG TY TNHH PHÁP VIỆT'}
        aliases = supplier_aliases({'supplier_aliases':[{'invoice_name':'Thiết bị sky','supplier_code':CODE}]}, directory)
        self.assertEqual(resolve_supplier('THIẾT BỊ SKY', directory, aliases), (CODE, SKY))
        self.assertEqual(resolve_supplier('PHAP VIET', directory, aliases)[0], '2')
        self.assertEqual(resolve_supplier('Thiết bị', directory, aliases)[0], '')
        directory['3'] = 'CÔNG TY CỔ PHẦN PHÁP VIỆT'
        self.assertEqual(resolve_supplier('PHAP VIET', directory, aliases), ('', 'PHAP VIET'))
        self.assertEqual(resolve_supplier('Chưa rõ', directory, aliases), ('', ''))
        with self.assertRaises(ValueError):
            supplier_aliases({'supplier_aliases':[{'invoice_name':'x','supplier_code':'missing'}]}, directory)

    def test_numeric_supplier_code_uses_excel_zero_format_and_duplicate_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'catalog.xlsx'
            wb = Workbook()
            wb.active.title = 'DanhMucNCC'
            wb.active.append(['Mã nhà cung cấp','Tên nhà cung cấp'])
            wb.active.append([312281677, SKY])
            wb.active['A2'].number_format = '0000000000'
            wb.save(path)
            self.assertEqual(load_supplier_directory(path), {CODE:SKY})
            wb.active.append([CODE, 'Tên khác'])
            wb.save(path)
            wb.close()
            with self.assertRaises(ValueError):
                load_supplier_directory(path)

    def test_date_parser_and_missing_legacy_date_never_use_today(self):
        self.assertEqual(parse_delivery_date('31/10/2026'), date(2026,10,31))
        self.assertIsNone(parse_delivery_date(''))
        for value in ('02/11', '31/02/2026'):
            with self.assertRaises(ValueError):
                parse_delivery_date(value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, report = inputs(root)
            wb = load_workbook(report)
            for sheet in wb:
                sheet.delete_cols(17)
                sheet['N2'] = None
            wb.save(report)
            wb.close()
            row = aw.reviewed_delivery_rows(report, {})[0][0]
            self.assertIsNone(row['delivery_date'])
            self.assertEqual(row['received'], 10)

    def test_batch_date_comes_from_delivery_document_and_survives_matching_cache_and_report(self):
        documents = [{'path':'pr.jpg', 'document': {'document_type':'pr','delivery_date':'2026-10-01','items':[{}]}},
                     {'path':'delivery.jpg', 'document': {'document_type':'delivery','delivery_date':'2026-11-02',
                      'supplier_name':'Thiết bị sky','items':[{'item_name':'Ống hút', 'quantity':'10',
                      'received_quantity':'0','unit_price':'25000','line_amount':'250000'}]}}]
        delivery = aw.flatten_batch_items(documents,'delivery')
        resolved = {'items':[{'line_id':delivery[0]['line_id'], 'invoice_name':'Ống hút','catalog_code':'',
                             'confidence':0,'needs_review':True,'note':'', 'delivery_date':'wrong'}]}
        aw.restore_delivery_source_fields(resolved, delivery)
        row = aw.validate_rows(resolved,{})[0]
        self.assertEqual(row[16], '2026-11-02')
        self.assertEqual(row[7], 'Thiết bị sky')
        self.assertEqual(row[13], 0)
        self.assertIn('delivery_date', aw.BATCH_DOCUMENT_SCHEMA['required'])
        self.assertIn('delivery_date', aw.paired_extraction_schema({})['properties']['documents']['items']['required'])
        self.assertIn('Không dùng ngày yêu cầu trên PR', DELIVERY_DATE_PROMPT)

    def test_reordered_template_uses_headers_and_ocr_text_cannot_become_formula(self):
        wb = Workbook()
        wb.active.append(list(reversed(HEADERS)))
        item = dict(supplier_code=CODE, supplier_name=SKY, delivery_date=None, code='',
                    name='=HYPERLINK("bad")', unit='cái', received=0, unit_price=100)
        sheet = fill_flat_delivery(wb,[item])
        mapping = aw.delivery_columns(sheet)
        self.assertEqual(sheet.cell(2,mapping['ten mat hang']).data_type,'s')
        self.assertEqual(sheet.cell(2,mapping['tien hang']).value,'=K2*J2')
        wb.close()

    def test_failed_atomic_export_does_not_leave_workbook_or_modify_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template,catalog,rules,report = inputs(root)
            with patch.object(aw.os,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    aw.create_delivery_workbook(report,{},template,root/'output',excel_path=catalog,rules_path=rules)
            self.assertEqual(list((root/'output').glob('*.xlsx')),[])


if __name__ == '__main__':
    unittest.main()
