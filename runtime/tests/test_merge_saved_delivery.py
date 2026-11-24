from pathlib import Path
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import merge_saved_delivery as cli
import multi_delivery as multi
import AutoWatcher as aw


def add_invoice(report,name,day='15/10/2026'):
    rows=[['Cá','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','Đã sửa tay','NCC','','','','',2,0,10,20,'2026-10-15','','','','','',day,name,'','1',hashlib.sha256(name.encode()).hexdigest()]]
    multi.save_one(report,multi.image_key(hashlib.sha256(name.encode()).hexdigest()),rows,sheet_title=Path(name).stem)


class MergeLauncherTests(unittest.TestCase):
    def test_real_bat_in_path_with_spaces_merges_preserves_edits_and_backup(self):
        with tempfile.TemporaryDirectory(prefix='Gop phieu co dau ') as tmp:
            report=Path(tmp)/'TongHop da doc.xlsx'
            add_invoice(report,'PAGE_A.JPG');add_invoice(report,'PAGE_B.JPG')
            before=report.read_bytes()
            launcher=Path(cli.__file__).with_name('08_Gop_phieu_da_tach.bat')
            env=dict(os.environ,PYTHONPATH='C:/Users/Fenn/Desktop/Auto',GEMINI_API_KEY='')
            result=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c','call',str(launcher),'--report',str(report)],input='PAGE_A, PAGE_B\nCO\nQ\n\n',text=True,encoding='utf-8',capture_output=True,env=env,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('ĐÃ GỘP',result.stdout)
            wb=aw.load_workbook(report)
            self.assertEqual(wb.sheetnames,['PAGE_A+PAGE_B']);self.assertEqual(wb.active.max_row,3)
            self.assertEqual(wb.active['G2'].value,'Đã sửa tay');self.assertEqual(wb.active['N2'].value,0)
            wb.close()
            backups=list(report.parent.glob('.autowatcher-backups/manual-group-*/*.xlsx'))
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),before)

    def test_cancel_and_wrong_names_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.xlsx';add_invoice(report,'PAGE_A.JPG');add_invoice(report,'PAGE_B.JPG')
            before=report.read_bytes()
            with patch('builtins.input',side_effect=['PAGE_A.JPG, absent.JPG','PAGE_A.JPG, PAGE_B.JPG','','Q']):
                self.assertEqual(cli.run(report),0)
            self.assertEqual(before,report.read_bytes())

    def test_date_conflict_does_not_change_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.xlsx';add_invoice(report,'PAGE_A.JPG');add_invoice(report,'PAGE_B.JPG','16/10/2026')
            before=report.read_bytes()
            with patch('builtins.input',side_effect=['PAGE_A.JPG, PAGE_B.JPG','CO','Q']):
                self.assertEqual(cli.run(report),0)
            self.assertEqual(before,report.read_bytes())

    def test_multiple_groups_and_already_merged_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.xlsx'
            for name in ['A.JPG','B.JPG','C.JPG','D.JPG']:add_invoice(report,name)
            with patch('builtins.input',side_effect=['A.JPG B.JPG','CO','C.JPG; D.JPG','CO','A.JPG B.JPG','Q']):
                self.assertEqual(cli.run(report),0)
            wb=aw.load_workbook(report);self.assertEqual(wb.sheetnames,['A+B','C+D']);wb.close()

    def test_missing_report_returns_error_without_creating_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'missing.xlsx'
            self.assertEqual(cli.run(report),1)
            self.assertFalse(report.exists())


if __name__=='__main__':unittest.main()
