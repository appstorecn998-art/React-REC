import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from openpyxl import load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
sys.path.append('C:/Users/Fenn/Desktop/Auto/tests')
import multi_delivery_export as exporter
import AutoWatcher as aw
from test_supplier_flat import inputs


class MultiExportTests(unittest.TestCase):
    def test_today_cli_selects_daily_source_and_unpadded_output_on_each_machine_day(self):
        days=[datetime(2026,11,5),datetime(2026,11,6),datetime(2026,12,31),datetime(2027,1,1)]
        with tempfile.TemporaryDirectory(prefix='Auto export today dates ') as tmp:
            root=Path(tmp)
            for day in days:
                report=root/('TongHopPhieuNgay_'+day.strftime('%d-%m-%Y')+'.xlsx')
                report.touch()
                with self.subTest(day=day),patch.object(exporter,'BASE_DIR',root), \
                     patch.object(exporter,'datetime') as clock, \
                     patch.object(sys,'argv',['multi_delivery_export.py','--today','--template',str(root/'template.xlsx')]), \
                     patch.object(exporter.aw,'load_catalog_data',return_value=({},{})), \
                     patch.object(exporter,'export_multiple') as export:
                    clock.now.side_effect=[day,datetime(2030,1,1)]
                    self.assertEqual(exporter.main(),0)
                    self.assertEqual(export.call_args.args[0],report)
                    self.assertEqual(export.call_args.args[4],root/f'Phieu giao hang {day.day}-{day.month}-{day.year}.xlsx')
                    self.assertEqual(clock.now.call_count,1)

    def test_missing_today_source_does_not_fall_back_to_other_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'TongHopNhieuPhieuGiaoHang.xlsx').write_bytes(b'legacy report')
            (root/'TongHopPhieuNgay_04-11-2026.xlsx').write_bytes(b'yesterday report')
            with patch.object(exporter,'BASE_DIR',root),patch.object(exporter,'datetime') as clock, \
                 patch.object(sys,'argv',['multi_delivery_export.py','--today']), \
                 patch.object(exporter.aw,'load_catalog_data') as catalog, \
                 patch.object(exporter,'export_multiple') as export, \
                 self.assertLogs(level='ERROR') as messages:
                clock.now.return_value=datetime(2026,11,5)
                self.assertEqual(exporter.main(),1)
            self.assertIn('TongHopPhieuNgay_05-11-2026.xlsx',' '.join(messages.output))
            catalog.assert_not_called();export.assert_not_called()
            self.assertFalse((root/'Phieu giao hang 5-11-2026.xlsx').exists())

    def test_legacy_cli_defaults_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/'TongHopNhieuPhieuGiaoHang.xlsx';report.touch()
            with patch.object(exporter,'BASE_DIR',root), \
                 patch.object(sys,'argv',['multi_delivery_export.py','--template',str(root/'template.xlsx')]), \
                 patch.object(exporter.aw,'load_catalog_data',return_value=({},{})), \
                 patch.object(exporter,'export_multiple') as export:
                self.assertEqual(exporter.main(),0)
                self.assertEqual(export.call_args.args[0],report)
                self.assertEqual(export.call_args.args[4],root/'PhieuGiaoHangNhieuNgay.xlsx')

    def test_today_batch_exports_fixture_without_ai_and_rerun_keeps_manual_edits(self):
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='Auto export today BAT ') as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root)
            workbook=load_workbook(catalog)
            sheet=workbook.create_sheet('DanhMucGoc')
            sheet.append(['Mã','Tên','ĐVT','','','Mã nhóm','Tên nhóm'])
            sheet.append(['TEST01','Ống hút','cái','','','TEST','Hàng test'])
            workbook.save(catalog);workbook.close()
            today=datetime.now().date()
            daily=root/f'TongHopPhieuNgay_{today:%d-%m-%Y}.xlsx'
            report.rename(daily)
            output=root/f'Phieu giao hang {today.day}-{today.month}-{today.year}.xlsx'
            launcher=root/'Xuat_Phieu_Giao_Hang_Hom_Nay.bat'
            shutil.copy2(next(source.glob('*Xuat_Phieu_Giao_Hang_Hom_Nay.bat')),launcher)
            for path in source.glob('*.py'):shutil.copy2(path,root/path.name)
            originals={p:p.read_bytes() for p in (template,catalog,rules,daily)}
            def run():
                result=subprocess.run(
                    [os.environ.get('COMSPEC','cmd.exe'),'/d','/c','call',str(launcher),
                     '--excel',str(catalog),'--rules',str(rules),'--template',str(template)],
                    cwd=root.parent,input=b'\r\n',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
                self.assertEqual(result.returncode,0,result.stdout.decode('utf-8',errors='replace'))
            # No API key exists in this isolated folder; export uses saved data only.
            run()
            workbook=load_workbook(output)
            self.assertEqual(workbook.sheetnames,['1'])
            self.assertEqual(workbook.active.max_column,19)
            self.assertEqual(workbook.active['K2'].value,'=I2*J2')
            self.assertEqual(workbook.active['D2'].value,datetime(2026,10,29))
            workbook.active['I2']=7;workbook.save(output);workbook.close()
            run()
            workbook=load_workbook(output)
            self.assertEqual(workbook.active['I2'].value,7)
            workbook.close()
            for path,original in originals.items():self.assertEqual(path.read_bytes(),original)

    def test_slash_in_packing_does_not_replace_product_name_and_version_change_reexports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root)
            workbook=load_workbook(report)
            workbook.worksheets[0]['A2']='Saigon Special 330ml - 24 cans/lon'
            workbook.worksheets[1]['A2']='Perrier 330ml - 24 bottles/chai'
            workbook.save(report);workbook.close()
            source_bytes=report.read_bytes();output=root/'out.xlsx'
            with patch.object(exporter,'LAYOUT_VERSION','old-layout'):
                exporter.export_multiple(report,{},catalog,rules,output,template)
            workbook=load_workbook(output);workbook.active['F2']='lon';workbook.save(output);workbook.close()
            exporter.export_multiple(report,{},catalog,rules,output,template)
            workbook=load_workbook(output)
            self.assertEqual(workbook.active['F2'].value,'Saigon Special 330ml - 24 cans/lon')
            self.assertEqual(workbook.active['F3'].value,'Perrier 330ml - 24 bottles/chai')
            self.assertEqual(workbook.active['K2'].value,'=I2*J2');workbook.close()
            self.assertEqual(report.read_bytes(),source_bytes)
            self.assertEqual(len(list(root.glob('.autowatcher-backups/multi-export-*/out.xlsx'))),1)

    def fixture(self,root):
        template,catalog,rules,report=inputs(root)
        workbook=load_workbook(report)
        for sheet,received in zip(workbook,['29/10/2026','30/10/2026']):
            sheet['W1']='Ngày nhận hàng xác nhận';sheet['W2']=received
        workbook.save(report);workbook.close()
        return template,catalog,rules,report

    def test_many_sheets_one_template_sheet_uses_receipt_dates_and_preserves_sources(self):
        with tempfile.TemporaryDirectory(prefix='gop nhieu phieu ') as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root)
            originals={p:p.read_bytes() for p in (template,catalog,rules,report)}
            output=root/'PhieuGiaoHangNhieuNgay.xlsx'
            exporter.export_multiple(report,{},catalog,rules,output,template)
            workbook=load_workbook(output);sheet=workbook.active
            self.assertEqual(workbook.sheetnames,['1'])
            self.assertEqual(sheet.max_column,19)
            self.assertEqual(sheet['D2'].value,datetime(2026,10,29))
            self.assertEqual(sheet['D3'].value,datetime(2026,10,30))
            self.assertEqual([sheet[f'A{r}'].value for r in (2,3)],[1,2])
            self.assertEqual([sheet[f'I{r}'].value for r in (2,3)],[0,4.2])
            self.assertEqual(sheet['K2'].value,'=I2*J2')
            self.assertEqual(sheet['K3'].value,'=I3*J3')
            self.assertEqual(sheet['B2'].data_type,'s')
            self.assertEqual(sheet['F2'].font.name,'Calibri')
            self.assertEqual(sheet['F2'].font.sz,11)
            self.assertEqual(sheet.column_dimensions['C'].width,65)
            workbook.close()
            for p,original in originals.items():self.assertEqual(p.read_bytes(),original)

    def test_repeat_keeps_edits_restores_backup_and_changed_input_archives_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root);output=root/'out.xlsx'
            def export():return exporter.export_multiple(report,{},catalog,rules,output,template)
            export();workbook=load_workbook(output);workbook.active['I2']=7;workbook.save(output);workbook.close()
            export();workbook=load_workbook(output);self.assertEqual(workbook.active['I2'].value,7);workbook.close()
            output.unlink();export();workbook=load_workbook(output);self.assertEqual(workbook.active['I2'].value,7);workbook.close()
            workbook=load_workbook(report);workbook.active['N2']=5;workbook.save(report);workbook.close()
            export();workbook=load_workbook(output);self.assertEqual(workbook.active['I2'].value,5);workbook.close()
            backups=list((root/'.autowatcher-backups').glob('multi-export-*/out.xlsx'))
            self.assertEqual(len(backups),1)
            workbook=load_workbook(backups[0]);self.assertEqual(workbook.active['I2'].value,7);workbook.close()

    def test_missing_receipt_date_fails_without_overwriting_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root);output=root/'out.xlsx'
            exporter.export_multiple(report,{},catalog,rules,output,template);before=output.read_bytes()
            workbook=load_workbook(report);workbook.active['W2']=None;workbook.save(report);workbook.close()
            with self.assertRaisesRegex(ValueError,'Ngày nhận hàng'):
                exporter.export_multiple(report,{},catalog,rules,output,template)
            self.assertEqual(output.read_bytes(),before)

    def test_locked_destination_keeps_prior_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root);output=root/'out.xlsx'
            exporter.export_multiple(report,{},catalog,rules,output,template);before=output.read_bytes()
            workbook=load_workbook(report);workbook.active['N2']=8;workbook.save(report);workbook.close()
            with patch.object(exporter.os,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):exporter.export_multiple(report,{},catalog,rules,output,template)
            self.assertEqual(output.read_bytes(),before)
            self.assertEqual(set(root.glob('*.xlsx')),{template,catalog,report,output})

    def test_output_may_not_overwrite_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'File xuất phải khác'):
                exporter.export_multiple(report,{},catalog,rules,report,template)

    def test_numeric_excel_receipt_date_with_general_format_exports_using_workbook_epoch(self):
        from openpyxl.utils.datetime import to_excel, CALENDAR_MAC_1904
        for epoch in (None, CALENDAR_MAC_1904):
            with self.subTest(epoch=epoch), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);template,catalog,rules,report=self.fixture(root);output=root/'out.xlsx'
                book=load_workbook(report)
                if epoch is not None:book.epoch=epoch
                serial=to_excel(datetime(2026,10,6),epoch=book.epoch)
                book.active['W2']=serial;book.active['W2'].number_format='General'
                book.save(report);book.close()
                before=report.read_bytes()
                exporter.export_multiple(report,{},catalog,rules,output,template)
                book=load_workbook(output)
                self.assertEqual(book.active['D2'].value,datetime(2026,10,6))
                book.close();self.assertEqual(report.read_bytes(),before)

    def test_invalid_serial_is_rejected_without_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);template,catalog,rules,report=self.fixture(root);output=root/'out.xlsx'
            book=load_workbook(report);book.active['W2']=-10;book.save(report);book.close()
            with self.assertRaisesRegex(ValueError,'ngày Excel không hợp lệ'):
                exporter.export_multiple(report,{},catalog,rules,output,template)
            self.assertFalse(output.exists())

if __name__=='__main__':unittest.main(verbosity=2)
