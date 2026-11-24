from pathlib import Path
import sys,json,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import AutoWatcher as aw
from catalog_recall import ranked_candidates,sizes

class CatalogRecallTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root=Path(aw.__file__).parent
  cls.cat,cls.groups=aw.load_catalog_data(root/'DanhMuc.xlsm')
  cls.rules=aw.read_rules(root/'NhaCungCap.json',cls.cat,cls.groups)
 def test_real_catalog_targets_in_top_ranked(self):
  for name,target in [('Há Cảo Cầu Tre Đóng gói 500 gr','11140015'),('Xíu Mại Cầu Tre Đóng gói 500 gr','11140011'),('Smooth Peanut Butter 340G','11520008')]:
   candidates=ranked_candidates(name,self.cat)
   self.assertIn(target,[row[0] for row in candidates[:5]],(name,candidates[:5]))
  self.assertEqual(sizes('500 gr'),sizes('0.5kg'))
 def test_unknown_supplier_bad_group_can_find_real_code_without_changing_values(self):
  item=dict(item_name='Há Cảo Cầu Tre Đóng gói 500 gr',group_id='1220',line_id='DE1:1',quantity='2',received_quantity='0',unit_price='10',line_amount='20')
  def resolve(api,model,items,pr,catalog,groups,rules,timeout,supplier):
   extracted={'supplier_name':supplier,'items':[{'invoice_name':items[0]['item_name'],'group_id':items[0]['group_id']}]}
   code='11140015' if code_in_scope(catalog) else ''
   return {'extracted':extracted,'items':[dict(invoice_name=item['item_name'],catalog_code=code,confidence=95,needs_review=not bool(code),note='test',line_id='DE1:1',quantity='2',received_quantity='0',unit_price='10',line_amount='20')]},aw.build_plans(extracted,self.cat,self.groups,rules)
  def code_in_scope(catalog):return '11140015' in catalog and len(catalog)<100
  with patch.object(aw,'_resolve_batch_items',side_effect=resolve):
   result,plans=aw.resolve_batch_items('','model',[item],[],self.cat,self.groups,self.rules,90,'DELI YOURS')
  self.assertEqual(result['items'][0]['catalog_code'],'11140015')
  self.assertEqual(result['items'][0]['received_quantity'],'0')
  row=aw.validate_rows(result,self.cat,plans,self.groups)[0]
  self.assertEqual(row[1],'11140015')
 def test_confirmed_peanut_overrides_incorrect_initial_group(self):
  plan=aw.build_plans({'supplier_name':'CÔNG TY TNHH THÀNH PHỐ THỰC PHẨM','items':[{'invoice_name':'Smooth Peanut Butter 340G','group_id':'1640'}]},self.cat,self.groups,self.rules)[0]
  self.assertEqual(plan['approved_code'],'11520008')
  self.assertFalse(plan['conflict'])
 def test_unapproved_supplier_scope_is_not_bypassed(self):
  item=dict(item_name='Nước ép thanh long',group_id='1920',line_id='DE1:1')
  result={'extracted':{'supplier_name':'Đức Tú','items':[{'invoice_name':item['item_name'],'group_id':'1920'}]},'items':[dict(catalog_code='',note='') ]}
  plans=aw.build_plans(result['extracted'],self.cat,self.groups,self.rules)
  with patch.object(aw,'_resolve_batch_items',return_value=(result,plans)):
   resolved,_=aw.resolve_batch_items('','model',[item],[],self.cat,self.groups,self.rules,90,'Đức Tú')
  self.assertEqual(resolved['items'][0]['catalog_code'],'')
 def test_wrong_size_selected_in_retry_is_rejected(self):
  cat={'a':('Brand flour 500g','Bag'),'b':('Brand flour 1kg','Bag')};groups={c:('1610','Bột') for c in cat}
  item=dict(item_name='Flour Brand 500g',group_id='1610',line_id='DE1:1')
  extracted={'supplier_name':'unknown','items':[dict(invoice_name=item['item_name'],group_id='1610')]}
  plans=aw.build_plans(extracted,cat,groups,{'suppliers':[]})
  initial={'extracted':extracted,'items':[dict(catalog_code='',note='')]}
  retry={'items':[dict(catalog_code='b',confidence=99,needs_review=False,note='wrong size')]}
  with patch.object(aw,'_resolve_batch_items',side_effect=[(initial,plans),(retry,[]) ]):
   result,_=aw.resolve_batch_items('','model',[item],[],cat,groups,{'suppliers':[]},90,'unknown')
  self.assertEqual(result['items'][0]['catalog_code'],'')
  self.assertIn('Quy cách',result['items'][0]['note'])
 def test_retry_failure_keeps_unresolved_row_and_original_values(self):
  name='Há Cảo Cầu Tre Đóng gói 500 gr';extracted={'supplier_name':'DELI YOURS','items':[dict(invoice_name=name,group_id='1220')]}
  initial={'extracted':extracted,'items':[dict(catalog_code='',note='',quantity='2',received_quantity='0')]}
  plans=aw.build_plans(extracted,self.cat,self.groups,self.rules)
  with patch.object(aw,'_resolve_batch_items',side_effect=[(initial,plans),TimeoutError('fixture')]):
   result,_=aw.resolve_batch_items('','model',[dict(item_name=name,line_id='DE1:1',group_id='1220')],[],self.cat,self.groups,self.rules,90,'DELI YOURS')
  self.assertEqual(result['items'][0]['catalog_code'],'');self.assertEqual(result['items'][0]['received_quantity'],'0')
