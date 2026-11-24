import sys,unittest
from pathlib import Path
here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app),str(app/'tests')]
import delivery_export
from openpyxl import Workbook
from delivery_export import fill_flat_delivery,HEADERS
class MoneyFormatTests(unittest.TestCase):
 def test_integer_fraction_and_product_precision(self):
  b=Workbook();b.active.append(HEADERS)
  rows=[dict(invoice_key=str(i),supplier_code='',supplier_name='NCC',delivery_date=None,code='',name='Hàng',unit='kg',received=q,unit_price=p) for i,(q,p) in enumerate([(50,4000),(0.5,1.25),(4,1.25)])]
  s=fill_flat_delivery(b,rows)
  self.assertEqual([s.cell(r,10).number_format for r in [2,3,4]],['#,##0','#,##0.00','#,##0.00'])
  self.assertEqual([s.cell(r,11).number_format for r in [2,3,4]],['#,##0','#,##0.000','#,##0'])
  self.assertEqual(s['K3'].value,'=I3*J3');self.assertEqual(s['J3'].value,1.25)
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(MoneyFormatTests)
 for n in ['test_multi_delivery_export','test_delivery_formulas','test_supplier_flat']:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(n))
 r=unittest.TextTestRunner(verbosity=0).run(suite);sys.exit(not r.wasSuccessful())
