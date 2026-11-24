import argparse
from datetime import date, datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import AutoWatcher as aw
from test_supplier_flat import inputs


class ManualDeliveryDateTests(unittest.TestCase):
    def test_prompt_rejects_incomplete_and_invalid_date_then_accepts_full_date(self):
        with patch('builtins.input', side_effect=['02/99', '31/02/2026', '15/10/2026']) as prompt:
            self.assertEqual(aw.choose_delivery_date(), date(2026, 10, 15))
        self.assertEqual(prompt.call_count, 3)

    def test_blank_prompt_uses_today_after_old_days_are_finished(self):
        with patch('builtins.input', return_value=''):
            self.assertEqual(aw.choose_delivery_date(), datetime.now().date())

    def test_explicit_date_needs_no_prompt_and_accepts_leap_day(self):
        with patch('builtins.input') as prompt:
            self.assertEqual(aw.choose_delivery_date('2028-02-29'), date(2028, 2, 29))
        prompt.assert_not_called()
        with self.assertRaises(ValueError):
            aw.choose_delivery_date('29/02/2027')

    def test_day_only_uses_current_month_and_year(self):
        with patch('AutoWatcher.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 3)
            self.assertEqual(aw.choose_delivery_date('2'), date(2026, 11, 2))

    def test_eof_or_cancel_does_not_fall_back_to_machine_date(self):
        with patch('builtins.input', side_effect=EOFError), self.assertRaisesRegex(ValueError, 'Chưa nhập ngày'):
            aw.choose_delivery_date()
        with patch('builtins.input', return_value='q'), self.assertRaisesRegex(ValueError, 'Đã hủy'):
            aw.choose_delivery_date()

    def test_same_day_versions_keep_day_and_ignore_other_day_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            selected = date(2026, 11, 2)
            (output/'Phieu giao hang ngay 31.xlsx').write_bytes(b'old')
            first = aw.next_delivery_path(output, selected)
            self.assertEqual(first.name, 'Phieu giao hang ngay 02.xlsx')
            first.write_bytes(b'old-02')
            second = aw.next_delivery_path(output, selected)
            self.assertEqual(second, first)
            self.assertEqual(aw.next_delivery_path(output, selected), first)
            self.assertEqual(first.read_bytes(), b'old-02')

    def test_backup_reserves_same_day_version_without_advancing_day(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup = aw.delivery_backup_directory(root)
            backup.mkdir()
            (backup/'Phieu giao hang ngay 09.xlsx').write_bytes(b'preserve')
            (backup/'Phieu giao hang ngay 09 (ban 3).xlsx').write_bytes(b'preserve')
            self.assertEqual(aw.next_delivery_path(root, date(2026,12,9)).name,
                             'Phieu giao hang ngay 09.xlsx')

    def test_export_prompts_and_routes_selected_date_but_reads_todays_tonghop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root/'TongHop_2026-11-02.xlsx'
            report.touch()
            args = argparse.Namespace(output=root)
            with (patch('builtins.input', return_value='15/10/2026'),
                  patch.object(aw,'create_delivery_workbook',return_value=root/'final.xlsx') as create):
                aw.export_reviewed_tonghop(args, {}, now=datetime(2026,11,2))
            self.assertEqual(create.call_args.args[0], report)
            selected = create.call_args.kwargs['now']
            self.assertEqual(selected, date(2026,10,15))
            output = aw.delivery_output_directory(selected)
            self.assertEqual(output.parts[-2:], ('Thang 10','Ngay 15'))

    def test_export_cancel_creates_no_delivery_and_calls_no_generator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'TongHop_2026-11-02.xlsx').touch()
            with (patch('builtins.input',return_value='q'), patch.object(aw,'create_delivery_workbook') as create,
                  self.assertRaises(ValueError)):
                aw.export_reviewed_tonghop(argparse.Namespace(output=root),{},now=datetime(2026,11,2))
            create.assert_not_called()

    def test_selected_day_repeats_restore_manual_edits_and_changes_only_revision_after_report_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, catalog, rules, report = inputs(root)
            kwargs = dict(template_path=template,output_dir=root/'output',excel_path=catalog,
                          rules_path=rules,now=date(2026,10,15))
            first = aw.create_delivery_workbook(report,{},**kwargs)
            self.assertEqual(first.name,'Phieu giao hang ngay 15.xlsx')
            wb = load_workbook(first)
            wb.active['I2'] = 7
            wb.save(first)
            wb.close()
            self.assertEqual(aw.create_delivery_workbook(report,{},**kwargs), first)
            first.unlink()
            self.assertEqual(aw.create_delivery_workbook(report,{},**kwargs), first)
            wb = load_workbook(first)
            self.assertEqual(wb.active['I2'].value,7)
            self.assertEqual(wb.active['D2'].value,datetime(2026,11,1))
            wb.close()
            wb = load_workbook(report)
            wb.active['N2'] = 2
            wb.save(report)
            wb.close()
            second = aw.create_delivery_workbook(report,{},**kwargs)
            self.assertEqual(second.name,'Phieu giao hang ngay 15.xlsx')
            wb = load_workbook(second)
            self.assertEqual(wb.active['I2'].value, 2)
            self.assertEqual(wb.active['K2'].value, '=I2*J2')
            wb.close()
            self.assertEqual(aw.create_delivery_workbook(report,{},**kwargs),second)

    def test_different_selected_day_never_restores_the_previous_days_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template,catalog,rules,report = inputs(root)
            kwargs = dict(template_path=template,output_dir=root/'output',excel_path=catalog,rules_path=rules)
            first = aw.create_delivery_workbook(report,{},now=date(2026,11,2),**kwargs)
            second = aw.create_delivery_workbook(report,{},now=date(2026,11,3),**kwargs)
            self.assertEqual(first.name,'Phieu giao hang ngay 02.xlsx')
            self.assertEqual(second.name,'Phieu giao hang ngay 03.xlsx')
            self.assertTrue(first.is_file())

    def test_cli_asks_date_writes_selected_path_and_keeps_it_on_repeat_without_api_key(self):
        with tempfile.TemporaryDirectory(prefix='Auto ngay nhap ') as temporary:
            root = Path(temporary)
            template,catalog,rules,report = inputs(root)
            wb = load_workbook(catalog)
            sheet = wb.create_sheet('DanhMucGoc')
            sheet.append(['Mã','Tên','ĐVT','','','Nhóm','Tên nhóm'])
            sheet.append(['001','Ống hút','cái','','','1410','Nhóm thử'])
            wb.save(catalog)
            wb.close()
            auto = root/'Auto'
            auto.mkdir()
            for name in ['AutoWatcher.py','supplier_rules.py','supplier_directory.py','receipt_rules.py','delivery_export.py','warehouse_directory.py','pr_warehouse.py','delivery_pages.py']:
                shutil.copy2(Path(aw.__file__).parent/name,auto/name)
            today = datetime.now()
            source = root/f'TongHop_{today:%Y-%m-%d}.xlsx'
            report.rename(source)
            master = root/'Công việc'/'Kế toán'/'Phieu giao hang hang thang'/'Phieu giao hang ngay X.xlsx'
            master.parent.mkdir(parents=True)
            shutil.copy2(template,master)
            command = [sys.executable,'-B','-X','utf8',str(auto/'AutoWatcher.py'),'--export-reviewed',
                       '--excel',str(catalog),'--rules',str(rules),'--output',str(root)]
            first = subprocess.run(command,input='31/02/2026\n15/10/2026\n',text=True,
                                   encoding='utf-8',capture_output=True,timeout=20)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            self.assertIn('Nhập ngày tạo phiếu', first.stdout)
            expected = master.parent/'Thang 10'/'Ngay 15'/'Phieu giao hang ngay 15.xlsx'
            self.assertTrue(expected.is_file(),first.stderr)
            second = subprocess.run(command,input='15/10/2026\n',text=True,
                                    encoding='utf-8',capture_output=True,timeout=20)
            self.assertEqual(second.returncode,0,second.stdout+second.stderr)
            self.assertEqual(list(expected.parent.glob('*.xlsx')),[expected])
            self.assertTrue(source.is_file())
