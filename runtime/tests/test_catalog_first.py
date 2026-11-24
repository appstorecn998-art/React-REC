from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import AutoWatcher as aw
import supplier_rules as sr
from catalog_recall import CATALOG_FIRST_PROMPT, product_mismatch


class CatalogFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(aw.__file__).parent
        cls.catalog,cls.groups=aw.load_catalog_data(cls.root/'DanhMuc.xlsm')
        cls.rules=aw.read_rules(cls.root/'NhaCungCap.json',cls.catalog,cls.groups)

    def extraction(self,name,supplier='TRÁI CÂY ĐỨC TÚ',group='1310'):
        return {'supplier_name':supplier,'items':[{'invoice_name':name,'group_id':group}]}

    def item(self,name,line='DE1:1',**extra):
        return dict(item_name=name,line_id=line,group_id='1310',quantity='15',received_quantity='0',
                    unit_price='17000',line_amount='255000',supplier_name='TRÁI CÂY ĐỨC TÚ',**extra)

    def test_every_supplier_policy_sees_whole_catalog_before_context(self):
        for supplier in ('TRÁI CÂY ĐỨC TÚ','Mega','Đảo Ngọc','unknown'):
            plan=sr.build_plans(self.extraction('Kumquat/Tắc',supplier),self.catalog,self.groups,self.rules)[0]
            self.assertEqual(set(plan['catalog']),set(self.catalog))
            self.assertFalse(plan['conflict'])
            self.assertIn('11310053',plan['catalog'])

    def test_four_confirmed_fruit_codes_no_matching_api_and_zero_unchanged(self):
        names=[('Yellow lemon/Chanh vàng','11410062'),('Kumquat/Tắc','11310053'),
               ('Sanh orange/Cam sành','11410110'),('Pineapple/Khóm','11410101')]
        items=[self.item(name,line=f'DE1:{index}') for index,(name,_) in enumerate(names,1)]
        before=deepcopy(items)
        with patch.object(aw.genai,'Client',side_effect=AssertionError('No matching API for confirmed names')):
            result,plans=aw.resolve_batch_items('unused','model',items,[],self.catalog,self.groups,self.rules,90,'TRÁI CÂY ĐỨC TÚ')
        rows=aw.validate_rows(result,self.catalog,plans,self.groups)
        self.assertEqual([row[1] for row in rows],[code for _,code in names])
        self.assertEqual(rows[1][8],self.groups['11310053'][1])
        self.assertTrue(all(row[13]==0 for row in rows))
        self.assertTrue(all(row[4] is None for row in rows))
        self.assertEqual(items,before)

    def test_confirmed_short_names_work_without_bilingual_ocr_but_not_other_suppliers(self):
        for name,code in [('Chanh vàng','11410062'),('Tắc','11310053'),('Cam sành','11410110'),('Khóm','11410101')]:
            plan=sr.build_plans(self.extraction(name),self.catalog,self.groups,self.rules)[0]
            self.assertEqual(plan['approved_code'],code)
            other=sr.build_plans(self.extraction(name,'other supplier'),self.catalog,self.groups,self.rules)[0]
            self.assertEqual(other['approved_code'],'')
        for name in ('Chanh vàng Mỹ','Cam sành 3-4 quả/kg','Nước ép khóm','Khóm Tắc Cậu'):
            self.assertEqual(sr.build_plans(self.extraction(name),self.catalog,self.groups,self.rules)[0]['approved_code'],'')

    def test_single_pair_entrypoint_uses_same_confirmed_names(self):
        extracted={'supplier_name':'TRÁI CÂY ĐỨC TÚ','delivery_date':'2026-11-04',
                   'items':[dict(invoice_name='Tắc',group_id='1410',quantity='10',received_quantity='0')]}
        fake=MagicMock()
        with patch.object(aw.genai,'Client',return_value=fake),patch.object(aw,'response_json',return_value=extracted):
            result=aw.request_items('unused','model',b'fixture',self.catalog,90,self.groups,self.rules)
        self.assertEqual(fake.__enter__.return_value.interactions.create.call_count,1)
        self.assertEqual(result['items'][0]['catalog_code'],'11310053')
        self.assertEqual(result['items'][0]['received_quantity'],'0')

    def test_unconfirmed_full_catalog_candidates_and_prompt_reach_ai_on_first_pass(self):
        item=self.item('Kumquat/Tắc')
        rules=deepcopy(self.rules)
        next(s for s in rules['suppliers'] if s['id']=='duc_tu')['confirmed_items']=[]
        fake=MagicMock()
        response={'items':[dict(line_id=item['line_id'],invoice_name=item['item_name'],catalog_code='11310053',
            confidence=95,needs_review=False,note='Khớp tên trong danh mục',quantity='999',received_quantity='999')]}
        with patch.object(aw.genai,'Client',return_value=fake),patch.object(aw,'response_json',return_value=response):
            resolved,plans=aw._resolve_batch_items('unused','model',[item],[],self.catalog,self.groups,rules,90,'TRÁI CÂY ĐỨC TÚ')
        prompt=fake.__enter__.return_value.interactions.create.call_args.kwargs['input']
        self.assertIn(CATALOG_FIRST_PROMPT,prompt)
        self.assertIn('11310053',prompt)
        self.assertIn('supplier_context',prompt)
        self.assertEqual(resolved['items'][0]['received_quantity'],'0')
        self.assertEqual(resolved['items'][0]['quantity'],'15')
        row=aw.validate_rows(resolved,self.catalog,plans,self.groups)[0]
        self.assertEqual(row[1],'CHUA CO MA')
        self.assertIn('nhiều mã',row[6])

    def test_wrong_size_or_form_rejected_at_any_confidence(self):
        for source,code in [('Nước ép thanh long','11410050'),('Beer Heineken Can 250ml','22120001')]:
            result={'items':[dict(invoice_name=source,catalog_code=code,confidence=99,needs_review=False,note='fixture')]}
            plans=sr.build_plans(self.extraction(source),self.catalog,self.groups,self.rules)
            self.assertEqual(aw.validate_rows(result,self.catalog,plans,self.groups)[0][1],'CHUA CO MA')
        self.assertTrue(product_mismatch('Brand 500g','Brand 1kg'))
        self.assertFalse(product_mismatch('Brand 500gr','Brand 0.5kg'))

    def test_unrelated_printed_code_must_be_confirmed_by_name(self):
        item=self.item('Kumquat/Tắc',catalog_code='11410050')
        rules={'suppliers':[]}
        fake=MagicMock()
        result={'items':[dict(line_id=item['line_id'],invoice_name=item['item_name'],catalog_code='11310053',
                             confidence=95,needs_review=False,note='Tên tắc, không phải thanh long')]}
        with patch.object(aw.genai,'Client',return_value=fake),patch.object(aw,'response_json',return_value=result):
            resolved,plans=aw._resolve_batch_items('unused','model',[item],[],self.catalog,self.groups,rules,90,'unknown')
        self.assertEqual(fake.__enter__.return_value.interactions.create.call_count,1)
        self.assertEqual(resolved['items'][0]['catalog_code'],'11310053')

    def test_confirmed_mapping_can_cross_supplier_group_but_code_must_exist(self):
        rules=deepcopy(self.rules)
        supplier=next(s for s in rules['suppliers'] if s['id']=='duc_tu')
        self.assertEqual(supplier['allowed_group_ids'],['1410'])
        self.assertTrue(any(item['catalog_code']=='11310053' for item in supplier['confirmed_items']))
        sr.validate_rules(rules,self.catalog,self.groups)
        supplier['confirmed_items'][-1]['catalog_code']='made-up-code'
        with self.assertRaises(ValueError):sr.validate_rules(rules,self.catalog,self.groups)

    def test_exact_unique_catalog_name_is_found_before_supplier_rules_without_api(self):
        name=self.catalog['11310053'][0]
        item=self.item(name)
        with patch.object(aw.genai,'Client',side_effect=AssertionError('Exact catalog name needs no matching API')):
            resolved,plans=aw.resolve_batch_items('unused','model',[item],[],self.catalog,self.groups,self.rules,90,'Đảo Ngọc')
        rows=aw.validate_rows(resolved,self.catalog,plans,self.groups)
        self.assertEqual(rows[0][1],'11310053')
        self.assertEqual(rows[0][9],'Khớp tên danh mục')
        self.assertIsNone(rows[0][4])

    def test_duplicate_catalog_name_is_not_resolved_automatically(self):
        catalog={'a':('Tên giống nhau','kg'),'b':('Tên giống nhau','Bag')}
        groups={code:('1310','Rau củ') for code in catalog}
        plan=sr.build_plans(self.extraction('Tên giống nhau','unknown'),catalog,groups,{'suppliers':[]})[0]
        self.assertEqual(plan['matched_code'],'')
