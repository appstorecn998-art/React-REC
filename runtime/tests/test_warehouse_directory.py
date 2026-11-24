import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

import AutoWatcher as aw
import warehouse_directory as wh
from test_supplier_flat import inputs

DIRECTORY = {'1103': ('Kho bếp Caya', 'KC'), '1400': ('Kho kỹ thuật', 'ENG'),
             '1600': ('Kho kid club', 'Kid Club'), '1800': ('Kho hóa chất', 'Steward'),
             '1900': ('Kho nhiên liệu', '')}


def choice(category, line_id=1):
    return {'line_id': line_id, 'category': category, 'note': 'Căn cứ loại hàng.'}


class WarehouseTests(unittest.TestCase):
    def test_request_reads_completed_sdk_output_text_and_disables_storage(self):
        with patch('google.genai.Client') as client:
            create=client.return_value.__enter__.return_value.interactions.create
            create.return_value=SimpleNamespace(status='completed',output_text=json.dumps({'items':[choice('unknown')]}))
            result=wh.request_choices([{'line_id':1}],DIRECTORY,'unused','model',5)
            self.assertEqual(result['items'][0]['category'],'unknown')
            self.assertFalse(create.call_args.kwargs['store'])
            create.return_value=SimpleNamespace(status='in_progress',output_text='')
            with self.assertRaises(ValueError):
                wh.request_choices([{'line_id':1}],DIRECTORY,'unused','model',5)

    def test_directory_header_mapping_blank_department_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'catalog.xlsx'
            w = Workbook()
            s = w.active
            s.title = 'Danhmuckho'
            s.append(['Bộ phận', 'Tên kho', 'Mã kho'])
            s.append(['KC', 'Kho bếp Caya', 1103])
            s.append([None, 'Kho nhiên liệu', '1900'])
            w.save(p)
            self.assertEqual(wh.load_warehouse_directory(p), {'1103':DIRECTORY['1103'], '1900':DIRECTORY['1900']})
            s.append(['ENG', 'Tên khác', '1103'])
            w.save(p)
            w.close()
            with self.assertRaisesRegex(ValueError, 'khác tên'):
                wh.load_warehouse_directory(p)

    def test_ai_categories_resolve_only_from_directory_and_unknown_stays_blank(self):
        records = [{'line_id': i} for i in range(1, 6)]
        payload = {'items':[choice(c, i) for i, c in enumerate([*wh.CATEGORY_CODES, 'unknown'], 1)]}
        results = wh.validate_choices(payload, records, DIRECTORY)
        self.assertEqual([r[:3] for r in results], [
            ('1103','Kho bếp Caya','KC'), ('1800','Kho hóa chất','Steward'),
            ('1400','Kho kỹ thuật','ENG'), ('1600','Kho kid club','Kid Club'), ('','','')])
        results = wh.validate_choices({'items':[choice('engineering_parts')]}, [{'line_id':1}], {})
        self.assertEqual(results[0][:3], ('','',''))
        self.assertIn('không có', results[0][3])

    def test_invented_category_duplicate_missing_extra_and_wrong_types_reject_entire_response(self):
        records = [{'line_id':1}, {'line_id':2}]
        bad = [[choice('unknown')], [choice('unknown'), choice('unknown')],
               [choice('unknown'), choice('invented',2)],
               [choice('unknown'), choice('unknown',3)],
               [choice('unknown'), choice('unknown','2')]]
        for items in bad:
            with self.subTest(items=items), self.assertRaises(ValueError):
                wh.validate_choices({'items':items}, records, DIRECTORY)

    def test_cache_reuses_choices_but_directory_or_rule_change_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            kwargs = ( [{'line_id':1,'invoice_name':'Ốc vít'}], DIRECTORY, 'unused', 'model', 5, Path(tmp))
            with patch.object(wh,'request_choices',return_value={'items':[choice('engineering_parts')]}) as request:
                wh.classify_records(*kwargs)
                wh.classify_records(*kwargs)
                self.assertEqual(request.call_count, 1)
                with patch.object(wh,'WAREHOUSE_PROMPT',wh.WAREHOUSE_PROMPT+' rule change'):
                    wh.classify_records(*kwargs)
                self.assertEqual(request.call_count, 2)
                updated = dict(DIRECTORY, **{'1400': ('Tên kho mới', 'ENG')})
                result = wh.classify_records(kwargs[0],updated,*kwargs[2:])
                self.assertEqual(request.call_count, 3)
                self.assertEqual(result[0][1], 'Tên kho mới')

    def test_enrichment_api_failure_keeps_ocr_figures_and_adds_review_note(self):
        rows = aw.validate_rows({'items':[{'invoice_name':'Cá', 'catalog_code':'', 'confidence':0,
            'needs_review':True,'note':'','quantity':'2','received_quantity':'0','unit_price':'5'}]}, {})
        original = list(rows[0][:17])
        with tempfile.TemporaryDirectory() as tmp, patch.object(wh,'request_choices',side_effect=TimeoutError('timeout')):
            wh.enrich_rows(rows,DIRECTORY,'unused','model',5,tmp)
        self.assertEqual(rows[0][:6], original[:6])
        self.assertEqual(rows[0][7:17], original[7:17])
        self.assertEqual(rows[0][13],0)
        self.assertEqual(rows[0][17:20],['','',''])
        self.assertIn('[Kho]',rows[0][6])

    def test_migrate_old_report_preserves_every_existing_cell_and_uses_no_image_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _,_,_,report = inputs(root)
            w=load_workbook(report)
            for s in w:
                s.delete_cols(18,3)
            w.save(report); w.close()
            w=load_workbook(report)
            before={s.title: [[c.value for c in r] for r in s] for s in w}; w.close()
            with patch.object(wh,'request_choices',return_value={'items':[choice('engineering_parts',1),choice('unknown',2)]}):
                result=wh.update_report_warehouses(report,DIRECTORY,'unused','model',5,root/'cache')
            self.assertEqual(result, {'rows':2,'assigned':1,'unknown':1})
            w=load_workbook(report)
            for s in w:
                for r in (1,2):
                    for c in range(1,18):
                        if c==7 and s==w.worksheets[1] and r==2: continue
                        self.assertEqual(s.cell(r,c).value,before[s.title][r-1][c-1])
            self.assertEqual(w.active['R2'].value,'1400')
            self.assertEqual(w.active['S2'].value,'Kho kỹ thuật')
            self.assertEqual(w.active['T2'].value,'ENG')
            self.assertEqual(w.active['N2'].value,0)
            w.close()
            self.assertEqual(len(list(root.glob('.autowatcher-backups/warehouse-report-*/*.xlsx'))),1)

    def test_valid_manual_warehouse_is_kept_and_department_is_read_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,_,_,report=inputs(root)
            w=load_workbook(report)
            for s in w:
                s['R2']='1900';s['S2']='wrong';s['T2']='invented'
            w.save(report);w.close()
            with patch.object(wh,'request_choices') as request:
                wh.update_report_warehouses(report,DIRECTORY,'unused','model',5,root/'cache')
            request.assert_not_called()
            w=load_workbook(report)
            self.assertEqual(w.active['S2'].value,'Kho nhiên liệu')
            self.assertIsNone(w.active['T2'].value)
            w.close()

    def test_partial_ai_response_or_locked_write_leaves_original_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,_,_,report=inputs(root)
            before=report.read_bytes()
            with patch.object(wh,'request_choices',return_value={'items':[choice('unknown')]}):
                with self.assertRaises(ValueError):
                    wh.update_report_warehouses(report,DIRECTORY,'unused','model',5,root/'cache')
            self.assertEqual(report.read_bytes(),before)
            with patch.object(wh,'classify_records',return_value=[('','','','unknown')]*2), \
                 patch.object(wh.os,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    wh.update_report_warehouses(report,DIRECTORY,'unused','model',5,root/'cache')
            self.assertEqual(report.read_bytes(),before)

    def test_final_export_fills_headers_preserves_zero_stt_formula_and_manual_edits_on_warehouse_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            template,catalog,rules,report=inputs(root)
            w=load_workbook(catalog); s=w.create_sheet('DanhMucKho');s.append(wh.WAREHOUSE_HEADERS)
            for c,(name,department) in DIRECTORY.items():s.append([c,name,department])
            w.save(catalog);w.close()
            kwargs=dict(template_path=template,output_dir=root/'out',excel_path=catalog,rules_path=rules)
            output=aw.create_delivery_workbook(report,{},**kwargs)
            w=load_workbook(output);w.active['I2']=7;w.active['D2']='Ngày sửa tay';w.save(output);w.close()
            with patch.object(wh,'request_choices',return_value={'items':[choice('engineering_parts',1),choice('kid_club_toys',2)]}):
                wh.update_report_warehouses(report,DIRECTORY,'unused','model',5,root/'cache')
            self.assertEqual(aw.create_delivery_workbook(report,{},**kwargs),output)
            w=load_workbook(output);s=w.active
            self.assertEqual((s['H2'].value,s['N2'].value),('1400','ENG'))
            self.assertEqual((s['H3'].value,s['N3'].value),('1600','Kid Club'))
            self.assertEqual(s['I2'].value,7)
            self.assertEqual(s['I3'].value,4.2)
            self.assertEqual(s['D2'].value,'Ngày sửa tay')
            self.assertEqual(s['K2'].value,'=I2*J2')
            self.assertEqual(s['A2'].number_format,'00')
            self.assertEqual(s['H2'].data_type,'s')
            w.close()


if __name__=='__main__':unittest.main()
