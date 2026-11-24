import sys,unittest,copy,os,tempfile
from pathlib import Path
from decimal import Decimal
sys.path[:0]=[str(Path(__file__).resolve().parent),'C:/Users/Fenn/Desktop/REC_Software/App','C:/Users/Fenn/Desktop/REC_Software/App/tests']
from receiving_pr import compare
from receiving_overreceipt import approve
from rec_pr_review import eligible
from receiving_sheets import HEADERS,plan

class OverreceiptTests(unittest.TestCase):
 def setUp(self):
  self.item=dict(item_name='Sườn heo',quantity='10',unit='kg',unit_price='160000',catalog_code='001',specification='')
  self.delivery={'Tên hàng trên phiếu (Ảnh)':'Sườn heo','Mã vật tư':'001','Đơn vị tính':'kg','Thực nhận':11.62,'Số lượng':11.62,'Đơn giá':160000,'Nhà cung cấp':'Yêu Thực Phẩm'}
  self.rows=[(2,self.delivery)]
 def test_approval_only_clears_over_and_invalidates_on_changes(self):
  result=compare([self.item],self.rows,{0:2})[0];self.assertIn('over',result['alerts'])
  rule=approve(2,self.item,self.delivery,{},result['ordered'],result['received'],'Fenn','Nguyên khối')
  conversions={0:{'overreceipt_approval':rule}}
  checked=compare([self.item],self.rows,{0:2},conversions)
  self.assertTrue(eligible(checked));self.assertEqual(checked[0]['ordered'],Decimal('10'));self.assertEqual(checked[0]['received'],Decimal('11.62'))
  self.assertIn('bổ sung PR',checked[0]['status'])
  changed=dict(self.delivery,**{'Thực nhận':12})
  self.assertIn('overreceipt_stale',compare([self.item],[(2,changed)],{0:2},conversions)[0]['alerts'])
  changed=dict(self.delivery,**{'Đơn giá':170000})
  alerts=compare([self.item],[(2,changed)],{0:2},conversions)[0]['alerts'];self.assertIn('price',alerts)
 def test_surplus_sheet_row_is_retained_repeatable_and_preserves_notes(self):
  remote=[['Title'],[],[],HEADERS+['REC_ID']]
  row=dict(order_id='order',index=0,name='Sườn heo',unit='kg',ordered='10',received='11.62',remaining='-1.62',reason='',title='PR01')
  records=[dict(active=True,valid=True,order_id='order',day='2026-11-16',conversions={'0':{'overreceipt_approval':{'reason':'Nguyên khối','person':'Fenn'}}})]
  result=plan("'Kitchen'",remote,[row],records,{'order':'NCC'})
  change=result['changes'][0];self.assertNotIn('delete',change)
  self.assertEqual(change['values'][6:9],[10,11.62,0]);self.assertIn('Chờ mở PR',change['values'][9]);self.assertIn('1,62',change['values'][9]);self.assertIn('Hàng nguyên khối',change['values'][9])
  remote.append(change['values']);remote[-1][10]='Ghi chú bộ phận'
  self.assertEqual(plan("'Kitchen'",remote,[row],records,{'order':'NCC'})['changes'],[])
 def test_cumulative_approval_and_changed_history(self):
  from receiving_cumulative import apply
  delivery=dict(self.delivery,**{'Thực nhận':6,'Số lượng':6})
  rule=approve(2,self.item,delivery,{},Decimal('10'),Decimal('6'),'Fenn','Nguyên khối',previous=5)
  self.assertEqual(rule['excess'],'1')
  def calculate(previous):
   return apply(compare([self.item],[(2,delivery)],{0:2},{0:{'overreceipt_approval':rule}}),{0:previous},set(),1)
  self.assertTrue(eligible(calculate(5)));self.assertIn('Chờ bộ phận bổ sung PR',calculate(5)[0]['status'])
  self.assertFalse(eligible(calculate(6)))
  self.assertFalse(eligible(apply(compare([self.item],[(2,delivery)],{0:2},{0:{'overreceipt_approval':rule}}),{},set(),0)))

 def test_dialog_requires_person_and_applies_scoped_rule(self):
  os.environ['QT_QPA_PLATFORM']='offscreen'
  from PySide6.QtWidgets import QApplication,QDialog,QLineEdit,QDialogButtonBox
  from unittest.mock import patch
  from rec_overreceipt_dialog import show
  app=QApplication.instance() or QApplication([]);accepted=[]
  def execute(dialog):
   dialog.findChild(QLineEdit,'overreceiptPerson').setText('Fenn')
   dialog.findChild(QDialogButtonBox).accepted.emit()
  with patch.object(QDialog,'exec',execute):show(None,2,self.item,self.delivery,{},Decimal('10'),Decimal('11.62'),accepted.append)
  self.assertEqual(accepted[0]['excess'],'1.62');self.assertEqual(accepted[0]['status'],'pending_pr')

if __name__=='__main__':unittest.main()
