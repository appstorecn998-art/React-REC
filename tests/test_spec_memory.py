import sys,os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
stage=Path(__file__).resolve().parents[1]
original=Path(r'C:/Users/Fenn/Desktop/React REC')
sys.path.insert(0,str(original))
from local_runtime import activate
activate()
sys.path.insert(0,str(stage));sys.path.insert(0,str(stage/'runtime'))
from receiving_spec_memory import remember,lookup,packaging
from receiving_units import factor_for
from receiving_pr import compare
from pr_row_actions import apply

class MemoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  (self.root/'NhaCungCap.json').write_text(json.dumps({'suppliers':[],'keep':'untouched'}),encoding='utf-8')
  self.env=patch.dict(os.environ,{'REC_DATA_DIR':str(self.root)});self.env.start()
  self.item={'item_name':'Sữa 200ml','catalog_code':'1','unit':'hộp','quantity':'24','unit_price':'10000'}
  self.row={'Nhà cung cấp':'NCC A','Tên hàng trên phiếu (Ảnh)':'Sữa 200ml','Mã vật tư':'1','Đơn vị tính':'thùng','Thực nhận':1,'Số lượng':1,'Đơn giá':240000}
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def test_reuses_new_row_and_new_pr_quantity_preserves_source(self):
  before=dict(self.row)
  remember(self.root,self.item,self.row,'conversion','24','NCC xác nhận')
  item={**self.item,'quantity':'48'}
  result=compare([item],[(9,self.row)],{0:9})[0]
  self.assertEqual(result['received'],24);self.assertEqual(result['remaining'],24)
  self.assertEqual(result['delivery_price'],10000);self.assertEqual(self.row,before)
  self.assertEqual(json.loads((self.root/'NhaCungCap.json').read_text())['keep'],'untouched')
 def test_supplier_spec_and_source_unit_isolation(self):
  remember(self.root,self.item,self.row,'conversion','24','checked')
  for changes in ({'Nhà cung cấp':'NCC B'},{'Tên hàng trên phiếu (Ảnh)':'Sữa 500ml'},{'Đơn vị trên phiếu':'chai'},{'Mã vật tư':'2'}):
   self.assertIsNone(factor_for({},0,9,self.item,{**self.row,**changes})[0])
 def test_packaging_memory_does_not_approve_purchase(self):
  remember(self.root,self.item,self.row,'packaging','24','1 thùng 24 hộp')
  self.assertEqual(packaging(self.item,self.row)['value'],'24')
  self.assertEqual(compare([self.item],[(9,self.row)],{0:9})[0]['ordered'],24)
 def test_invalid_and_unknown_supplier_rejected(self):
  for value in ('0','-1','NaN','1/0'):
   with self.assertRaises(ValueError):remember(self.root,self.item,self.row,'conversion',value,'test')
  with self.assertRaises(ValueError):remember(self.root,self.item,{**self.row,'Nhà cung cấp':'Chưa rõ'},'conversion','24','test')
 def test_explicit_override_and_correction_not_replaced(self):
  from receiving_units import conversion
  remember(self.root,self.item,self.row,'conversion','24','test')
  rule=conversion(9,self.item,self.row,'12','once')
  self.assertEqual(factor_for({0:rule},0,9,self.item,self.row)[0],12)
  self.assertIsNone(factor_for({0:{'receipt_correction':{'test':1}}},0,9,self.item,self.row)[0])
 def test_pr_quantity_and_price_actions(self):
  entry=apply('pr_quantity',self.item,self.row,9,{},dict(value='48',reason='ảnh PR'))
  self.assertEqual(compare([self.item],[(9,self.row)],{0:9},{0:entry})[0]['ordered'],48)
  with self.assertRaises(ValueError):apply('price',self.item,self.row,9,{},dict(value='10',reason='x'))

class ActionTests(MemoryTests):
 def test_cumulative_overreceipt(self):
  remember(self.root,self.item,self.row,'conversion','24','test')
  item={**self.item,'quantity':'30'}
  entry=apply('overreceipt',item,self.row,9,{},dict(person='Purchase',reason='Duyệt dư'),previous=12)
  self.assertEqual(entry['overreceipt_approval']['previous'],'12')
  self.assertEqual(entry['overreceipt_approval']['excess'],'6')
 def test_pack_preview_and_accept(self):
  from pr_row_actions import package_preview
  remember(self.root,self.item,self.row,'conversion','24','test')
  item={**self.item,'quantity':'25'}
  fields=dict(value='24',reason='Bán nguyên thùng')
  preview=package_preview(item,self.row,9,{},fields)
  self.assertEqual(preview['approved'],'48');self.assertEqual(preview['extra_cost'],'230000')
  with self.assertRaises(ValueError):apply('packaging',item,self.row,9,{},fields)
  fields.update(confirmed_quantity=preview['approved'],confirmed_cost=preview['extra_cost'])
  self.assertEqual(apply('packaging',item,self.row,9,{},fields)['purchase_approval']['approved'],'48')
 def test_web_save_conversion_and_memory(self):
  from receipt_actions import save_pr
  from receiving_service import digest
  report=self.root/'report.xlsx';report.touch()
  image=self.root/'image.png'
  from PIL import Image
  Image.new('RGB',(20,20),'white').save(image)
  link=self.root/'link.json';link.write_text('{}')
  state=dict(status='ready',items=[self.item],links={0:9},conversions={},images=[image])
  payload=dict(sheet='A',version='v',token='t',action='row_action',kind='conversion',index=0,row=9,fields=dict(value='24',reason='Đã kiểm',remember='yes'))
  with patch('receipt_actions.get_rows',return_value={'A':[(9,self.row)]}),patch('receipt_actions.day_images',return_value=[image]),patch('receipt_actions.active',return_value=False),patch('receipt_actions.pr_paths',return_value=[link]),patch('receipt_actions.pr_token',return_value='t'),patch('receipt_actions.pr_state',return_value=state):
   self.assertTrue(save_pr(self.root,report,payload)['saved'])
  saved=json.loads(link.with_suffix('.comparison.json').read_text(encoding='utf-8'))
  self.assertEqual(saved['conversions']['0']['factor'],'24')
  self.assertEqual(lookup(self.item,self.row)['conversion']['value'],'24')
  self.assertEqual(saved['results'][0]['received'],'24')

 def test_opening_provenance_and_revision(self):
  from PIL import Image
  from receiving_pr_library import register,load
  from pr_opening import context,commit
  from receiving_opening_balance import read,validate
  from receiving_service import atomic_json
  store=self.root/'receipts';store.mkdir()
  from receipt_actions import pr_library
  library=pr_library(store)
  image=self.root/'pr.png';Image.new('RGB',(20,20),'white').save(image)
  self.item.update(pr_reference_id='TEST-01',pr_date='2026-10-20')
  key=register(library,[image],[self.item])
  index=json.loads((library/'index.json').read_text(encoding='utf-8'));index['orders'][key].update(number='TEST-01',date='2026-10-20');atomic_json(library/'index.json',index)
  record=load(library)[key];state=dict(items=[self.item],images=[Path(p) for p in record['images']])
  data=context(store,state,library)
  fields=dict(revision=str(data['revision']),receipts=data['receipts'],quantities='{"0":"5"}',before='2026-11-01',person='Tester',reason='Sổ cũ',consent='yes')
  commit(store,state,library,fields)
  record=read(data['path'],data['oid'])[data['oid']]
  self.assertTrue(record['pr_context']);validate(record,data['lines'])
  with self.assertRaises(ValueError):commit(store,state,library,fields)
  source=__import__('json').loads((library/'index.json').read_text(encoding='utf-8'))
  source['orders'][key]['items'][0]['quantity']='999'
  atomic_json(library/'index.json',source)
  with self.assertRaises(ValueError):validate(record,data['lines'])

class VatAndPendingTests(MemoryTests):
 def test_pending_preserves_assigned_and_confirmed_rows(self):
  from receipt_actions import pending_unreceived
  item2=dict(item_name='Bánh mì',catalog_code='2',unit='cái',quantity='5',unit_price='1000')
  self.assertEqual([r['pr_index'] for r in pending_unreceived([self.item,item2],[(9,self.row)],{0:9},{})],[1])
  self.assertEqual(pending_unreceived([self.item,item2],[(9,self.row)],{0:9,1:None},{}),[])
  extra={**self.row,'Tên hàng trên phiếu (Ảnh)':'Trà đen','Mã vật tư':'3'}
  with self.assertRaises(ValueError):pending_unreceived([self.item,item2],[(9,self.row),(10,extra)],{0:9},{})
 def test_bulk_save_requires_exact_preview_and_preserves_links(self):
  from receipt_actions import save_pr
  from PIL import Image
  report=self.root/'report.xlsx';report.touch();image=self.root/'source.png';Image.new('RGB',(20,20),'white').save(image)
  link=self.root/'link.json';link.write_text('{}')
  second=dict(item_name='Bánh mì',catalog_code='2',unit='cái',quantity='5',unit_price='1000')
  state=dict(status='ready',items=[self.item,second],links={0:9},conversions={},images=[image])
  payload=dict(sheet='A',version='v',token='t',action='mark_unreceived',indices=[])
  with patch('receipt_actions.get_rows',return_value={'A':[(9,self.row)]}),patch('receipt_actions.day_images',return_value=[image]),patch('receipt_actions.active',return_value=False),patch('receipt_actions.pr_paths',return_value=[link]),patch('receipt_actions.pr_token',return_value='t'),patch('receipt_actions.pr_state',return_value=state):
   with self.assertRaises(ValueError):save_pr(self.root,report,payload)
   payload['indices']=[1];self.assertEqual(save_pr(self.root,report,payload)['marked'],1)
  saved=json.loads(link.with_suffix('.comparison.json').read_text(encoding='utf-8'));self.assertEqual(saved['links'],{'0':9,'1':None})

 def test_vat_repeat_restore_and_comparison_retained(self):
  from openpyxl import Workbook,load_workbook
  from receiving_service import snapshot,sheet_signature
  from receipt_actions import receipt_action
  report=self.root/'report.xlsx';book=Workbook();ws=book.active;ws.title='A'
  headers=['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Nhà cung cấp']
  ws.append(headers);ws.append(['Sữa','1','hộp',2,2,108000,'NCC A']);book.save(report);book.close()
  version,data=snapshot(report);link=self.root/'link.json';draft=link.with_suffix('.comparison.json')
  draft.write_text(json.dumps(dict(signature=sheet_signature('A',dict(data)['A']),links={'0':2},conversions={},results=[])))
  def run(rate):
   version,_=snapshot(report)
   with patch('receipt_actions.day_images',return_value=[]),patch('receipt_actions.pr_paths',return_value=[link]):
    result=receipt_action(self.root,report,dict(action='vat',sheet='A',version=version,row=2,rate=rate))
   self.assertTrue(result['saved']);self.assertNotIn('warning',result)
   _,now=snapshot(report);saved=json.loads(draft.read_text());self.assertEqual(saved['links'],{'0':2});self.assertEqual(saved['signature'],sheet_signature('A',dict(now)['A']))
   return dict(dict(now)['A'])[2]
  row=run(8);self.assertEqual(row['Đơn giá'],100000)
  row=run(8);self.assertEqual(row['Đơn giá'],100000)
  row=run(0);self.assertEqual(row['Đơn giá'],108000)
  self.assertTrue(list((self.root/'.autowatcher-backups').glob('gui-edit-*')))
  version,_=snapshot(report)
  with self.assertRaises(ValueError):receipt_action(self.root,report,dict(action='vat',sheet='A',version=version,row=2,rate=True))

class ReviewFixTests(MemoryTests):
 def test_corrected_pr_packaging_preview_and_reapproval(self):
  from receiving_pr_quantity import approve
  from receiving_packaging import effective
  from pr_row_actions import package_preview,apply
  item={**self.item,'unit':'kg','quantity':'10'}
  row={**self.row,'Đơn vị tính':'kg','Đơn giá':1000}
  entry={'pr_quantity':approve(item,{},'12','Ảnh PR ghi12')}
  fields=dict(value='5',reason='Bán nguyên gói')
  preview=package_preview(item,row,9,entry,fields)
  self.assertEqual(preview['requested'],'12');self.assertEqual(preview['approved'],'15');self.assertEqual(preview['extra_cost'],'3000')
  fields.update(confirmed_quantity='15',confirmed_cost='3000')
  entry=apply('packaging',item,row,9,entry,fields)
  self.assertEqual(effective(item,entry,row['Nhà cung cấp'])[0],15)
  changed={**entry,'pr_quantity':approve(item,entry,'17','Ảnh mới')}
  self.assertIsNone(effective(item,changed,row['Nhà cung cấp'])[1])
  updated=apply('pr_quantity',item,row,9,entry,dict(value='17',reason='Ảnh mới'))
  self.assertNotIn('purchase_approval',updated)
  self.assertEqual(package_preview(item,row,9,updated,fields)['approved'],'20')
 def test_disable_remembered_pair_blocks_auto_only_and_is_scoped(self):
  from receiving_link_memory import remember,for_suppliers,set_active,inferred
  from receiving_pr import compare
  self.assertEqual(remember(self.root,[self.item],[(9,self.row)],{0:9}),1)
  rule=for_suppliers([(9,self.row)])[0]
  self.assertTrue(rule['active']);self.assertEqual(inferred([self.item],[(9,self.row)],{}),{0:9})
  with self.assertRaises(ValueError):set_active(self.root,[(9,{**self.row,'Nhà cung cấp':'NCC khác'})],rule['id'],False,'Sai hàng')
  set_active(self.root,[(9,self.row)],rule['id'],False,'Sai hàng đã kiểm')
  self.assertEqual(inferred([self.item],[(9,self.row)],{}),{})
  self.assertIsNone(compare([self.item],[(9,self.row)])[0]['row'])
  self.assertEqual(compare([self.item],[(9,self.row)],{0:9})[0]['row'],9)
  with self.assertRaises(ValueError):set_active(self.root,[(9,self.row)],rule['id'],True,'Stale token')
  current=for_suppliers([(9,self.row)])[0]
  self.assertFalse(current['active'])
  set_active(self.root,[(9,self.row)],current['id'],True,'Đã kiểm lại')
  self.assertEqual(compare([self.item],[(9,self.row)])[0]['row'],9)
  self.assertEqual(json.loads((self.root/'NhaCungCap.json').read_text())['keep'],'untouched')

class KnowledgeTests(MemoryTests):
 def test_global_inventory_covers_all_supplier_and_legacy_rules(self):
  from knowledge import inventory,update_pair
  from receiving_link_memory import remember
  remember(self.root,[self.item],[(9,self.row)],{0:9})
  data=json.loads((self.root/'NhaCungCap.json').read_text())
  data['suppliers']=[dict(id='a',name='NCC A',aliases=['NCC A','Alias A'],confirmed_items=[dict(invoice_name='Hàng A',catalog_code='001')],allowed_group_ids=['G1'])]
  data.update(supplier_aliases=[dict(invoice_name='NCC B',supplier_code='02')],unit_conversions=[dict(supplier_name='NCC B',pr_item_name='Oil',delivery_unit='thùng',pr_unit='chai',factor='24')],packaging_rules=[dict(key=dict(supplier='NCC B',item_name='Bánh',unit='cái'),pack_size='50')],pr_spec_equivalences=[dict(key=dict(supplier='a',pr=dict(item_name='Hàng A'),delivery={}),reason='Đã duyệt')],warehouse_rules=[dict(supplier_id='a',warehouse_code='1101')],warehouse_departments={'1101':'Bếp'})
  data['pr_spec_rules']=[dict(key=dict(supplier='a',pr=dict(item_name='Milk'),delivery={}),conversion=dict(value='24',reason='1 thùng 24 hộp'))]
  (self.root/'NhaCungCap.json').write_text(json.dumps(data),encoding='utf-8')
  folder=self.root/'.receiving/vocabulary';folder.mkdir(parents=True)
  (folder/'yes.json').write_text(json.dumps(dict(names=['A','B'],confirmed=True,explanation='Đã kiểm')))
  (folder/'no.json').write_text(json.dumps(dict(names=['Cache only'],confirmed=False)))
  rows=inventory(self.root)['items'];kinds={r['type'] for r in rows}
  self.assertTrue({'supplier_names','confirmed_items','pr_link_rules','unit_conversions','packaging_rules','pr_spec_equivalences','warehouse_rules','warehouse_departments','vocabulary'}<=kinds)
  self.assertEqual(len([r for r in rows if r['type']=='vocabulary']),1)
  self.assertTrue(any(r['supplier']=='NCC B' for r in rows))
  modern=next(r for r in rows if r['type']=='pr_spec_rules')
  self.assertIn('24',modern['summary']);self.assertIn('1 thùng',modern['reason'])
  pair=next(r for r in rows if r['pair'])
  update_pair(self.root,dict(rule=pair['id'],active=False,reason='Sai cặp'))
  current=next(r for r in inventory(self.root)['items'] if r['pair'])
  self.assertFalse(current['active'])
  with self.assertRaises(ValueError):update_pair(self.root,dict(rule=pair['id'],active=True,reason='Stale'))
  self.assertEqual(json.loads((self.root/'NhaCungCap.json').read_text())['warehouse_departments'],{'1101':'Bếp'})

if __name__=='__main__':unittest.main()
