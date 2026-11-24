import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from openpyxl import load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.append('C:/Users/Fenn/Desktop/Auto')
import AutoWatcher as aw
import warehouse_directory as wh
import pr_warehouse as pr

DIRECTORY={'1202':('Kho nhà hàng Caya','FB'),'1103':('Kho bếp Caya','KC'),'1900':('Kho nhiên liệu','ENG')}
RULES=json.loads(Path(aw.__file__).with_name('NhaCungCap.json').read_text(encoding='utf-8-sig'))

def record(name='Kem vani',requester='Nguyễn Thị Mỹ Thi',status=pr.VERIFIED_PR):
    return dict(line_id=1,invoice_name=name,supplier_name='Cửu Long',requester_name=requester,pr_status=status)

class PRWarehouseTests(unittest.TestCase):
    def classify(self,records):
        with tempfile.TemporaryDirectory() as tmp, patch.object(wh,'request_choices',side_effect=AssertionError('No API')):
            return wh.classify_records(records,DIRECTORY,'unused','model',5,tmp,RULES)

    def test_shared_items_follow_exact_requester_with_or_without_accents(self):
        for name in ['Cà phê Palazzo hạt-1kg','Nước ngọt Coca Cola','Kem vani','Ice cream vanilla']:
            for requester,code in [('Nguyễn Thị Mỹ Thi','1202'),('Nguyen Thi My Thi','1202'),('Cam Văn Phú','1103'),('Cam Van Phu','1103')]:
                with self.subTest(name=name,requester=requester):
                    self.assertEqual(self.classify([record(name,requester)])[0][:3],(code,*DIRECTORY[code]))

    def test_absent_unmatched_unknown_or_partial_requester_requires_confirmation(self):
        for requester,status in [('Nguyễn Thị Mỹ Thi','KHÔNG CÓ PR'),('',''),('Nguyễn Thị Mỹ Thi','PR KHÔNG KHỚP'),('Mỹ Thi',pr.VERIFIED_PR),('Other requester',pr.VERIFIED_PR)]:
            result=self.classify([record(requester=requester,status=status)])[0]
            self.assertEqual(result[:3],('','',''))
            self.assertTrue(result[3].startswith(pr.CONFIRM_PREFIX))

    def test_ai_food_category_also_uses_requester_and_revalidates_cache(self):
        records=[record('Sữa tươi 1L','Cam Van Phu')]
        payload={'items':[dict(line_id=1,category='kitchen_food',note='Sữa')]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(wh,'request_choices',return_value=payload) as request:
            result=wh.classify_records(records,DIRECTORY,'unused','model',5,tmp,RULES)
            self.assertEqual(result[0][0],'1103')
            records[0]['requester_name']='Nguyen Thi My Thi'
            result=wh.classify_records(records,DIRECTORY,'unused','model',5,tmp,RULES)
            self.assertEqual(result[0][0],'1202')
            self.assertEqual(request.call_count,2)

    def test_nonfood_cream_does_not_trigger_food_rule(self):
        for name in ['Kem đánh răng','Ly uống rượu','Máy đánh kem']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, patch.object(wh,'request_choices',return_value={'items':[dict(line_id=1,category='unknown',note='Không phải thực phẩm')]} ) as request:
                result=wh.classify_records([record(name)],DIRECTORY,'unused','model',5,tmp,RULES)
                self.assertEqual(result[0][0],'')
                request.assert_called_once()

    def test_pair_context_ignores_delivery_signer_and_rejects_mismatched_pr(self):
        analysis={'pr_document':{'requester_name':'Cam Văn Phú'},'delivery_document':{'requester_name':'Nguyễn Thị Mỹ Thi'},'rows':[dict(pr_index=1,delivery_index=1,status='match')]}
        self.assertEqual(pr.row_pr_context(analysis,1),('Cam Văn Phú',pr.VERIFIED_PR))
        analysis['reference_mismatch']=True
        self.assertNotEqual(pr.row_pr_context(analysis,1)[1],pr.VERIFIED_PR)
        self.assertEqual(pr.row_pr_context(None,1)[0],'')

    def test_multi_pr_names_are_bound_to_each_comparison_row(self):
        prs=[dict(line_id='PR1:1',requester_name='Nguyễn Thị Mỹ Thi'),dict(line_id='PR2:1',requester_name='Cam Văn Phú')]
        deliveries=[dict(line_id='DE3:1'),dict(line_id='DE3:2')]
        comparison=dict(status='match',summary='',rows=[dict(pr_line_ids=[p['line_id']],delivery_line_ids=[d['line_id']],status='match',note='') for p,d in zip(prs,deliveries)])
        analysis=aw.batch_pair_analysis(comparison,prs,deliveries)
        self.assertEqual(pr.row_pr_context(analysis,1),('Nguyễn Thị Mỹ Thi',pr.VERIFIED_PR))
        self.assertEqual(pr.row_pr_context(analysis,2),('Cam Văn Phú',pr.VERIFIED_PR))
        analysis['rows'][0]['requester_names']=['Nguyễn Thị Mỹ Thi','Cam Văn Phú']
        self.assertNotEqual(pr.row_pr_context(analysis,1)[1],pr.VERIFIED_PR)

    def test_interactive_confirmation_validates_code_and_can_defer(self):
        pending=[('', '', '', pr.CONFIRM_PREFIX+' Thiếu PR')]
        with patch.object(wh.sys.stdin,'isatty',return_value=True),patch('builtins.input',side_effect=['9999','1103']):
            result=wh.confirm_warehouse_results([record()],pending,DIRECTORY)
            self.assertEqual(result[0][0],'1103')
        with patch.object(wh.sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value=''):
            self.assertEqual(wh.confirm_warehouse_results([record()],[('','','',pr.CONFIRM_PREFIX)],DIRECTORY)[0][0],'')

    def test_requester_context_roundtrips_report_and_report_upgrade(self):
        row=['Kem vani','CHUA CO MA','','Hộp',0,'CẦN KIỂM TRA','','Cửu Long','','','','',1,1,10,10,'','','','']
        analysis={'pr_document':{'requester_name':'Nguyen Thi My Thi'},'rows':[dict(pr_index=1,delivery_index=1,status='match')]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); report=root/'TongHop.xlsx'
            args=SimpleNamespace(excel=Path('unused'),rules=Path(aw.__file__).with_name('NhaCungCap.json'),output=root,timeout=5)
            with patch.object(aw,'load_warehouse_directory',return_value=DIRECTORY),patch.object(wh.sys.stdin,'isatty',return_value=False):
                aw.enrich_report_rows([row],args,'unused',analysis)
            self.assertEqual(row[17:20],['1202','Kho nhà hàng Caya','FB'])
            aw.write_result(report,Path('test.jpg'),[row])
            workbook=load_workbook(report); sheet=workbook.active
            self.assertEqual(sheet['U1'].value,pr.PR_HEADERS[0]);self.assertEqual(sheet['U2'].value,'Nguyen Thi My Thi')
            for col in ('R','S','T'):sheet[f'{col}2']=None
            workbook.save(report);workbook.close()
            with patch.object(wh,'request_choices',side_effect=AssertionError('No API')):
                wh.update_report_warehouses(report,DIRECTORY,'unused','model',5,root/'cache',RULES)
            workbook=load_workbook(report);self.assertEqual(workbook.active['R2'].value,'1202');workbook.close()

    def test_ocr_schemas_require_pr_requester(self):
        self.assertIn('requester_name',aw.BATCH_DOCUMENT_SCHEMA['required'])
        self.assertIn('requester_name',aw.paired_extraction_schema([])['properties']['documents']['items']['required'])

    def test_pr_number_is_not_compared_with_delivery_invoice_number(self):
        purchase={'document_type':'pr','reference_id':'13','requester_name':'CAM VĂN PHÚ'}
        delivery={'document_type':'delivery','reference_id':'DH9598'}
        self.assertFalse(pr.pr_reference_conflict([purchase],[delivery]))
        delivery['reference_id']='HD0000204395'
        self.assertFalse(pr.pr_reference_conflict([purchase],[delivery]))
        delivery['pr_reference_id']='PR-013'
        self.assertFalse(pr.pr_reference_conflict([purchase],[delivery]))
        delivery['pr_reference_id']='12'
        self.assertTrue(pr.pr_reference_conflict([purchase],[delivery]))
        self.assertTrue(pr.pr_reference_conflict([purchase,dict(purchase,reference_id='12')],[]))

    def test_linked_quantity_mismatch_keeps_requester_and_warning(self):
        comparison={'status':'mismatch','summary':'PR 10kg, thực nhận 9.9kg','rows':[
            {'pr_line_ids':['PR2:1'],'delivery_line_ids':['DE1:1'],'status':'mismatch','note':'Số lượng khác'}]}
        analysis=aw.batch_pair_analysis(comparison,[dict(line_id='PR2:1',requester_name='CAM VĂN PHÚ')],[dict(line_id='DE1:1')])
        requester,status=pr.row_pr_context(analysis,1)
        self.assertEqual((requester,status),('CAM VĂN PHÚ',pr.VERIFIED_PR))
        self.assertEqual(analysis['rows'][0]['status'],'mismatch')
        result=pr.requester_warehouse(record('Tôm sú',requester,status),DIRECTORY,RULES)
        self.assertEqual(result[:3],('1103','Kho bếp Caya','KC'))
        analysis['rows'][0]['pr_index']=0
        self.assertNotEqual(pr.row_pr_context(analysis,1)[1],pr.VERIFIED_PR)

if __name__=='__main__':unittest.main(verbosity=2)
