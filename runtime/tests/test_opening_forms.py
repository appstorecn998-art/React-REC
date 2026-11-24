import os,sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';stage=Path(__file__).resolve().parent;app=Path('C:/Users/Fenn/Desktop/REC_Software/App');sys.path[:0]=[str(stage),str(app),str(app/'tests')]
import receiving_ledger,receiving_cumulative,receiving_item_closure,receiving_ledger_loader,receiving_packaging,receiving_quantity_correction,rec_pr_library_layout,rec_pr_compare_layout,rec_substitution_page,rec_packaging_page,rec_quantity_correction_page,rec_unit_conversion_page,rec_price_approval_page,rec_shortage_layout
import test_receiving_qt as fixture_module
APP=fixture_module.APP;pump_until=fixture_module.pump_until
artifacts=stage if stage.name!='tests' else Path(tempfile.mkdtemp(prefix='rec-opening-proof-qa-'))
from PySide6.QtWidgets import QTableWidget,QLineEdit,QCheckBox,QPushButton,QDialogButtonBox,QWidget
from PySide6.QtGui import QImage,QColor
from rec_approval_evidence import EvidencePanel
from rec_opening_balance_page import show
from receiving_opening_balance import read
class FormTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixture_module.DesktopTests('runTest');self.fixture.setUp();self.w=self.fixture.window;self.w.inbox_timer.stop();self.w.pr_panel=QWidget(self.w);self.w.show()
 def tearDown(self):self.fixture.doCleanups()
 def test_opening_save_reopen_and_no_workbook_mutation(self):
  w=self.w;image=next(p for p in w.images if p.name=='unlinked.png');key=w.remember_pr([dict(item_name='A',quantity='5',unit='kg',unit_price='100',pr_reference_id='07',pr_document_date='2026-10-29',pr_supplier_name='NCC',pr_department='Kitchen')],[image]);original=self.fixture.report.read_bytes()
  page=show(w,key);self.assertIsNotNone(page);table=page.findChild(QTableWidget,'openingQuantities');table.item(0,3).setText('3');page.findChild(QLineEdit,'openingPerson').setText('Kitchen A');page.findChild(QLineEdit,'openingReason').setText('Bộ phận xác nhận sổ cũ');page.findChild(QCheckBox,'openingConsent').setChecked(True)
  proof=page.findChild(EvidencePanel);picture=QImage(160,100,QImage.Format_RGB32);picture.fill(QColor('blue'));proof.add_image(picture,'Xác nhận Kitchen');page.findChild(QPushButton,'saveOpeningBalance').click();pump_until(lambda:not w.busy and not w._workers)
  self.assertEqual(read(w.ledger_path(),key)[key]['quantities']['0'],'3');rows,history=receiving_ledger.summary(w.ledger_path());self.assertEqual(rows[0]['remaining'],'2');self.assertEqual(len(history),0)
  APP.processEvents();page.grab().save(str(artifacts/'opening-ui.png'))
  page=show(w,key);self.assertEqual(page.findChild(QTableWidget,'openingQuantities').item(0,3).text(),'3');self.assertEqual(page.findChild(EvidencePanel).list.count(),1)
  self.assertEqual(self.fixture.report.read_bytes(),original)
  import json
  index=Path(w.pr_library_directory())/'index.json';data=json.loads(index.read_text(encoding='utf-8'));data['orders'][key]['items'][0]['quantity']='6';index.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');self.assertIsNone(receiving_ledger.summary(w.ledger_path())[0][0]['remaining'])
 def test_unknown_receipt_sources_not_presented_as_verified_remaining(self):
  w=self.w;image=next(p for p in w.images if p.name=='unlinked.png');key=w.remember_pr([dict(item_name='A',quantity='5',unit='kg',unit_price='100',pr_reference_id='08',pr_supplier_name='NCC')],[image]);lines=receiving_ledger.order_lines(w.stored_pr_items([image]));receiving_ledger.save_receipt(w.ledger_path(),key,'PR08',lines,'uncertain',dict(day='2026-11-05',sheet='FIRST',allocations={'0':'2'},signature='old',report=str(self.fixture.report)))
  page=show(w,key);table=page.findChild(QTableWidget,'openingQuantities');table.item(0,3).setText('3');self.assertIn('Chưa xác minh',table.item(0,4).text());self.assertIn('Chưa xác minh',table.item(0,5).text())
 def test_packaging_evidence_survives_clear(self):
  from receiving_evidence import with_history
  from receiving_packaging import effective
  w=self.w;w.current_sheet='FIRST';item=dict(item_name='A',quantity='5',unit='kg',unit_price='15000');delivery=dict(w.data_by_sheet['FIRST'][0][1]);applied=[]
  with patch('rec_packaging_page.show_modal'),patch('rec_packaging_page.close_modal'):
   p=rec_packaging_page.open_page(w,item,delivery,2,{},applied.append);p.findChild(QLineEdit,'purchasePackSize').setText('1');p.findChild(QLineEdit,'purchasePackReason').setText('Pur A xác nhận');pic=QImage(120,80,QImage.Format_RGB32);pic.fill(QColor('green'));p.findChild(EvidencePanel).add_image(pic,'Pur A');p.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click();rule=applied[-1]
   self.assertTrue(rule.get('attachments'));self.assertIsNotNone(effective(item,{'purchase_approval':rule},delivery['Nhà cung cấp'])[1])
   p=rec_packaging_page.open_page(w,item,delivery,2,{'purchase_approval':rule},applied.append);next(b for b in p.findChildren(QPushButton) if b.text()=='Bỏ duyệt cũ').click();self.assertIsNone(applied[-1])
   history=with_history(w,'packaging',2,item,delivery,{});self.assertGreaterEqual(len(history['attachment_history']),2)
   p=rec_packaging_page.open_page(w,item,delivery,2,{},applied.append);self.assertTrue(p.findChild(QPushButton,'approvalEvidenceHistory').isEnabled());p.show();APP.processEvents();p.grab().save(str(artifacts/'packaging-ui.png'))
if __name__=='__main__':unittest.main()
