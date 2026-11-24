import tempfile
import unittest
from pathlib import Path
from PIL import Image
from openpyxl import Workbook
import receiving_pr_auto as auto
import receiving_pr_library as library


class AutoPRTests(unittest.TestCase):
    def setUp(self):
        self.items=[dict(item_name='Bánh bột lọc',unit='cai',quantity='30'),dict(item_name='Bánh ít',unit='cai',quantity='60')]
        self.record=dict(number='02',date='04/11/2026',supplier='An Nhiên',department='KITCHEN',items=self.items)
        self.rows=[(2,{'Tên hàng trên phiếu (Ảnh)':'Bánh bột lọc','Đơn vị tính':'cai','Số lượng':30,'Thực nhận':30,'Nhà cung cấp':'An Nhiên'})]

    def test_number_is_not_unique_across_dates_and_departments(self):
        records={'a':self.record,'b':dict(self.record,date='05/11/2026')}
        doc=dict(document_type='delivery',reference_id='Invoice 999',pr_reference_id='PR 02')
        self.assertIsNone(auto.matching_candidate(records,self.rows,[doc])[0])
        self.assertEqual(auto.matching_candidate(records,self.rows,[dict(doc,pr_date='2026-11-04')])[0],'a')
        self.assertIsNone(auto.matching_candidate(records,self.rows,[dict(doc,pr_reference_id='03')])[0])
        self.assertEqual(auto.matching_candidate({'a':self.record},self.rows,[doc])[0],'a')
        self.assertEqual(self.record['number'],'02')

    def test_explicit_po_selects_one_of_two_orders_for_same_pr(self):
        records={
            'a':dict(self.record,number='PO11/26.018',order_type='po',related_pr_number='PR1126.008'),
            'b':dict(self.record,number='PO11/26.016',order_type='po',related_pr_number='PR1126.008'),
        }
        doc=dict(document_type='delivery',reference_id='PX-123',pr_reference_id='PR1126.008')
        self.assertIsNone(auto.matching_candidate(records,self.rows,[doc])[0])
        self.assertEqual(auto.matching_candidate(records,self.rows,[dict(doc,po_reference_id='PO11/26.016')])[0],'b')

    def test_supplier_product_and_completion_prevent_false_links(self):
        self.assertEqual(auto.matching_candidate({'a':self.record},self.rows)[0],'a')
        wrong=[(2,dict(self.rows[0][1],**{'Nhà cung cấp':'Other'}))]
        self.assertIsNone(auto.matching_candidate({'a':self.record},wrong)[0])
        wrong=[(2,dict(self.rows[0][1],**{'Tên hàng trên phiếu (Ảnh)':'Coca-Cola 320 ml'}))]
        self.assertIsNone(auto.matching_candidate({'a':self.record},wrong)[0])
        totals=[dict(order_id='a',remaining='0')]
        self.assertIsNone(auto.matching_candidate({'a':self.record},self.rows,totals=totals)[0])
        self.assertIsNone(auto.matching_candidate({'a':self.record},self.rows,totals=[dict(order_id='a',remaining=None)])[0])

    def test_header_metadata_and_separate_same_number_first_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);images=[]
            for name,color in [('one.jpg','white'),('two.jpg','black')]:
                p=root/name;Image.new('RGB',(10,10),color).save(p);images.append(p)
            doc=dict(reference_id='02',document_date='2026-11-04',department_name='KITCHEN',supplier_name='An Nhiên',items=self.items,page_number='1')
            keys=auto.register_pages(root/'library',[(p,doc) for p in images])
            self.assertEqual(len(set(keys)),2)
            record=library.load(root/'library')[keys[0]]
            self.assertEqual((record['number'],record['date'],record['department']),('02','2026-11-04','KITCHEN'))

    def test_automatic_link_preserves_manual_selection_and_does_not_change_excel(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pr=root/'pr.png';delivery=root/'delivery.png'
            for p in [pr,delivery]:Image.new('RGB',(10,10),'white').save(p)
            doc=dict(reference_id='02',document_date='2026-11-04',department_name='KITCHEN',supplier_name='An Nhiên',items=self.items)
            auto.register_pages(root/'library',[(pr,doc)])
            report=root/'report.xlsx';book=Workbook();sheet=book.active;sheet.title='Delivery'
            headers=list(self.rows[0][1])+['Ảnh nguồn'];sheet.append(headers);sheet.append(list(self.rows[0][1].values())+['delivery.png']);book.save(report);book.close()
            before=report.read_bytes()
            messages=auto.link_report(root/'library',root/'ledger.sqlite',root,report,[delivery],{'delivery.png':dict(document_type='delivery',pr_reference_id='02')})
            self.assertIn('Đã tự ghép',messages[0]);self.assertEqual(before,report.read_bytes())
            path=next((root/'.receiving/manual-pr-links').glob('*.json'));path.write_text('{"manual":"keep"}',encoding='utf-8')
            auto.link_report(root/'library',root/'ledger.sqlite',root,report,[delivery],{})
            self.assertEqual(path.read_text(encoding='utf-8'),'{"manual":"keep"}')
