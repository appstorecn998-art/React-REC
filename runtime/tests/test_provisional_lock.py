import sys,unittest,tempfile,json
from pathlib import Path
from datetime import date
from unittest.mock import patch
here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app),str(app/'tests')]
import receiving_provisional_export as provisional
from test_multi_delivery_export import MultiExportTests
from receiving_service import digest
from multi_delivery import output_lock
class ProvisionalLockTests(unittest.TestCase):
 def fixture(self,root):
  template,catalog,rules,report=MultiExportTests().fixture(root)
  catalog.rename(root/'DanhMuc.xlsm');rules.rename(root/'NhaCungCap.json');template.rename(root/'Phieu giao hang ngay X.xlsx')
  return report
 def test_nested_source_lock_fixed_without_bypassing_real_lock(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);report=self.fixture(root);before=report.read_bytes();out=root/'output'
   with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('receiving_daily_report.stage_images',return_value=[]),patch('receiving_export_distribution.distribute') as distribute:
    folder=provisional.export(root,date(2026,11,13),out,report)
    self.assertTrue((folder/'Phieu giao hang 13-11-2026 - BẢN TẠM.xlsx').is_file());distribute.assert_called_once()
    self.assertEqual(report.read_bytes(),before)
    with output_lock(report),self.assertRaisesRegex(ValueError,'phiên xử lý'):
     provisional.export(root,date(2026,11,13),out,report)
 def test_source_mutation_before_publish_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);report=self.fixture(root)
   def mutate(*args):report.write_bytes(b'concurrent edit');return []
   with patch('AutoWatcher.load_catalog_data',return_value=({},{})),patch('receiving_daily_report.stage_images',side_effect=mutate),patch('receiving_export_distribution.distribute') as distribute:
    with self.assertRaisesRegex(ValueError,'Nguồn vừa thay đổi'):provisional.export(root,date(2026,11,13),root/'out',report)
    distribute.assert_not_called()
    self.assertFalse(list((root/'out').rglob('*BẢN TẠM.xlsx')))
if __name__=='__main__':unittest.main(verbosity=1)
