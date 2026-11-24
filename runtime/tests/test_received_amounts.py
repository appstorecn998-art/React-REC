from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from openpyxl import load_workbook
import AutoWatcher as aw
import multi_delivery as multi
from received_amounts import apply_received_amounts,upgrade_received_amounts,ORIGINAL_AMOUNT_HEADER
from test_merge_saved_delivery import add_invoice
from manual_invoice_links import merge_saved_invoices


class ReceivedAmountsTests(unittest.TestCase):
    def test_new_report_has_formula_and_keeps_original_zero_and_unknown_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG')
            w=load_workbook(p);s=w.active
            h={c.value:c.column for c in s[1]}
            self.assertEqual(s['P2'].data_type,'f')
            self.assertEqual(s['P2'].value,'=IF(COUNT(N2,O2)=2,N2*O2,"CHƯA RÕ")')
            self.assertEqual(s['N2'].value,0)
            self.assertEqual(s.cell(2,h[ORIGINAL_AMOUNT_HEADER]).value,20)
            self.assertEqual(s['Y2'].data_type,'f');w.close()
            # data_only has no formula cache but exporter must get actual 0, not old 20.
            rows=aw.reviewed_delivery_rows(p,{},date_header='Ngày nhận hàng xác nhận')
            self.assertEqual(rows[0][0]['amount'],0)
            w=load_workbook(p);w.active['N2']='CHƯA RÕ';w.save(p);w.close()
            with self.assertRaisesRegex(ValueError,'chưa rõ số thực nhận'):aw.reviewed_delivery_rows(p,{})
            w=load_workbook(p);w.active['N2']=1;w.active['O2']=None;w.save(p);w.close()
            with self.assertRaisesRegex(ValueError,'đơn giá'):aw.reviewed_delivery_rows(p,{})

    def test_upgrade_preserves_existing_data_and_old_amount_then_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG')
            w=load_workbook(p);s=w.active
            original_col=next(c.column for c in s[1] if c.value==ORIGINAL_AMOUNT_HEADER)
            s.delete_cols(original_col);s['P2']=123456;s['N2']=0;s['G2']='Sửa tay'
            w.save(p);w.close();before=p.read_bytes()
            self.assertEqual(upgrade_received_amounts(p),1)
            w=load_workbook(p);s=w.active
            h={c.value:c.column for c in s[1]}
            self.assertEqual(s.cell(2,h[ORIGINAL_AMOUNT_HEADER]).value,123456)
            self.assertEqual(s['G2'].value,'Sửa tay');self.assertEqual(s['N2'].value,0);w.close()
            backups=list(p.parent.glob('.autowatcher-backups/received-amounts-*/*.xlsx'))
            self.assertEqual(backups[0].read_bytes(),before)
            after=p.read_bytes();self.assertEqual(upgrade_received_amounts(p),0);self.assertEqual(p.read_bytes(),after)

    def test_merge_rebases_formula_and_keeps_both_original_amounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG');add_invoice(p,'B.JPG')
            merge_saved_invoices(p,['A','B'])
            w=load_workbook(p);s=w.active
            h={c.value:c.column for c in s[1]}
            self.assertEqual(s['P3'].value,'=IF(COUNT(N3,O3)=2,N3*O3,"CHƯA RÕ")')
            self.assertEqual([s.cell(r,h[ORIGINAL_AMOUNT_HEADER]).value for r in (2,3)],[20,20])
            self.assertIn('P2:P3',s['Y2'].value);w.close()

    def test_failed_upgrade_keeps_original_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx';add_invoice(p,'A.JPG')
            w=load_workbook(p);s=w.active
            s.delete_cols(next(c.column for c in s[1] if c.value==ORIGINAL_AMOUNT_HEADER));s['P2']=20;w.save(p);w.close()
            before=p.read_bytes()
            with patch('received_amounts.os.replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):upgrade_received_amounts(p)
            self.assertEqual(p.read_bytes(),before)

    def test_single_order_path_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx'
            row=['Cá','CHUA CO MA','','kg',0,'CẦN KIỂM TRA','','NCC','','','','',2,1,10,20,'','','','']
            aw.write_result(p,Path('image.jpg'),[row])
            w=load_workbook(p);self.assertEqual(w.active['P2'].value,20);self.assertNotIn(ORIGINAL_AMOUNT_HEADER,[c.value for c in w.active[1]]);w.close()
