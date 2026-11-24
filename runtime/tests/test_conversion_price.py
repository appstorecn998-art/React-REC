import sys,os,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';here=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(here),str(app),str(app/'tests')]
from PySide6.QtWidgets import QApplication,QMainWindow,QStackedWidget,QLineEdit,QPushButton,QDialogButtonBox,QLabel
from rec_unit_conversion_page import open_page
APP=QApplication.instance() or QApplication([])
class PriceTests(unittest.TestCase):
 def setUp(self):
  self.w=QMainWindow();self.w.main_pages=QStackedWidget();self.calls=[]
  self.item=dict(item_name='Kem xịt',unit='chai',quantity='2')
  self.delivery={'Tên hàng trên phiếu (Ảnh)':'Kem xịt','Đơn vị tính':'PACK','Thực nhận':2,'Đơn giá':None}
 def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents()
 def page(self,callback=None):
  with patch('rec_unit_conversion_page.show_modal'):
   return open_page(self.w,self.item,self.delivery,2,{'factor':'1','reason':'NCC xác nhận'},lambda rule:self.calls.append(rule),callback)
 def test_missing_price_edit_save_and_reopen(self):
  received=[];p=self.page(lambda price:received.append(price))
  price=p.findChild(QLineEdit,'conversionDeliveryPrice');self.assertFalse(price.isReadOnly());self.assertTrue(p.findChild(QLineEdit,'conversionReceived').isReadOnly())
  button=p.findChild(QDialogButtonBox).button(QDialogButtonBox.Save);self.assertFalse(button.isEnabled())
  self.assertFalse(any('Fraction' in x.text() for x in p.findChildren(QLabel)))
  price.setText('150000');self.assertFalse(button.isEnabled())
  p.findChild(QPushButton,'conversionSavePrice').click();self.assertEqual(received,['150000']);self.assertIsNone(self.delivery['Đơn giá'])
  self.delivery['Đơn giá']=150000;p=self.page(lambda price:None);self.assertTrue(p.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).isEnabled())
 def test_invalid_empty_negative_nonfinite_price_not_saved(self):
  received=[];p=self.page(lambda price:received.append(price));field=p.findChild(QLineEdit,'conversionDeliveryPrice')
  for text in ['', '-1','abc','NaN','inf']:
   field.setText(text);p.findChild(QPushButton,'conversionSavePrice').click()
  self.assertEqual(received,[])
 def test_zero_and_decimal_comma_are_valid(self):
  for text,expected in [('0','0'),('1500,5','1500.5')]:
   received=[];p=self.page(lambda price:received.append(price));p.findChild(QLineEdit,'conversionDeliveryPrice').setText(text);p.findChild(QPushButton,'conversionSavePrice').click();self.assertEqual(received,[expected])
 def test_price_button_writes_only_source_price(self):
  import tempfile
  from openpyxl import Workbook,load_workbook
  from receiving_service import edit_row,digest
  with tempfile.TemporaryDirectory() as td:
   report=Path(td)/'report.xlsx';book=Workbook();sheet=book.active;sheet.title='Receipt'
   sheet.append(['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Tên chuẩn hệ thống','Đơn vị tính','Thực nhận','Đơn giá','Thành tiền'])
   sheet.append(['Kem xịt','CHUA CO MA','','PACK',2,None,'=E2*F2']);sheet.append(['Khác','CHUA CO MA','','chai',3,100,'=E3*F3']);book.save(report);book.close()
   expected=digest(report)
   def persist(price):edit_row(report,expected,'Receipt',2,{'Đơn giá':price},{})
   p=self.page(persist);p.findChild(QLineEdit,'conversionDeliveryPrice').setText('150000');p.findChild(QPushButton,'conversionSavePrice').click()
   book=load_workbook(report);self.assertEqual(book['Receipt']['F2'].value,150000);self.assertEqual(book['Receipt']['E2'].value,2);self.assertEqual(book['Receipt']['G2'].value,'=E2*F2');self.assertEqual(book['Receipt']['F3'].value,100);book.close()
if __name__=='__main__':unittest.main(verbosity=1)
