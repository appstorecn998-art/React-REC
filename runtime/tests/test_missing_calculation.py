import sys,unittest,tempfile,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app),str(app/'tests')]
import delivery_export
from openpyxl import load_workbook
import multi_delivery_export as exporter
from test_multi_delivery_export import MultiExportTests
class MissingCalculationTests(unittest.TestCase):
 def test_template_without_calcpr_exports(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);template,catalog,rules,report=MultiExportTests().fixture(root)
   book=load_workbook(template);book.calculation=None;book.save(template);book.close()
   self.assertIsNone(load_workbook(template).calculation)
   original=template.read_bytes()
   exporter.export_multiple(report,{},catalog,rules,root/'out.xlsx',template)
   book=load_workbook(root/'out.xlsx');self.assertEqual(book.calculation.calcMode,'auto');self.assertTrue(book.calculation.fullCalcOnLoad);self.assertEqual(book.active['K2'].value,'=I2*J2');book.close()
   self.assertEqual(template.read_bytes(),original)
 def test_actual_active_template(self):
  from rec_runtime import user_root
  base=user_root();template=Path('C:/Users/Fenn/Desktop/REC_Software/Data/Phieu giao hang hang thang/Phieu giao hang ngay X.xlsx');report=template.parent/'Thang 11/Ngay 13/TongHopPhieuNgay_13-11-2026.xlsx'
  tracked=[template,report,base/'DanhMuc.xlsm',base/'NhaCungCap.json'];before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
  with tempfile.TemporaryDirectory() as td:
   catalog,_=exporter.aw.load_catalog_data(base/'DanhMuc.xlsm')
   import shutil
   copied=Path(td)/report.name;shutil.copy2(report,copied)
   exporter.export_multiple(copied,catalog,base/'DanhMuc.xlsm',base/'NhaCungCap.json',Path(td)/'out.xlsx',template)
   book=load_workbook(Path(td)/'out.xlsx');self.assertEqual(book.active.max_column,19);self.assertEqual(sum(bool(book.active.cell(r,6).value) for r in range(2,book.active.max_row+1)),6);self.assertEqual(book.calculation.calcMode,'auto');book.close()
  self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked})
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(MissingCalculationTests)
 for n in ['test_multi_delivery_export','test_supplier_flat','test_delivery_formulas']:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(n))
 r=unittest.TextTestRunner(verbosity=0).run(suite);sys.exit(not r.wasSuccessful())
