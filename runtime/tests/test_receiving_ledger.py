import sys
from pathlib import Path
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
import tempfile
import unittest
import sqlite3
from decimal import Decimal
import receiving_ledger as ledger

class LedgerTests(unittest.TestCase):
    def test_fractional_deliveries_sum_exactly_without_false_shortage(self):
        lines=[dict(self.lines[0],ordered='1',unit='hộp')]
        ledger.save_receipt(self.path,'PR1','PR 1',lines,'a',self.payload('1/3'))
        ledger.save_receipt(self.path,'PR1','PR 1',lines,'b',self.payload('2/3'))
        row=ledger.summary(self.path)[0][0]
        self.assertEqual(row['received'],'1');self.assertEqual(row['remaining'],'0');self.assertEqual(row['status'],'Đã đủ')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.sqlite'
        self.lines=[{'index':0,'name':'Cam','unit':'kg','ordered':'10','price':'100','code':'001','specification':''}]
    def payload(self,qty,day='2026-11-06',sheet='A'):
        return {'allocations':{'0':str(qty)},'day':day,'sheet':sheet,'signature':'v1'}
    def save(self,rid,qty,revision=0,**kwargs):
        return ledger.save_receipt(self.path,'PR1','PR 1',self.lines,rid,self.payload(qty),revision,**kwargs)
    def test_partial_delivery_next_day_and_updates_are_not_double_counted(self):
        self.save('a',7)
        ledger.save_receipt(self.path,'PR1','PR 1',self.lines,'b',self.payload(2,'2026-11-07','B'))
        rows,_=ledger.summary(self.path);self.assertEqual(rows[0]['remaining'],'1')
        self.assertEqual(self.save('a',7),1)
        self.save('a',6,1)
        self.assertEqual(ledger.summary(self.path)[0][0]['remaining'],'2')
        with self.assertRaisesRegex(ValueError,'Sổ đã thay đổi'):self.save('a',5,1)
    def test_delivery_recalculates_existing_shortage_on_sheets(self):
        from receiving_sheets import HEADERS, plan

        self.save('a',7)
        remote=[['Theo dõi hàng thiếu'],[],[],HEADERS+['REC_ID']]
        rows,records=ledger.summary(self.path)
        first=plan("'Kitchen'",remote,rows,records,{'PR1':'NCC A'})['changes'][0]
        self.assertEqual(first['values'][8],3)
        remote.append(first['values'])

        ledger.save_receipt(
            self.path,'PR1','PR 1',self.lines,'b',self.payload(2,'2026-11-07','B'))
        rows,records=ledger.summary(self.path)
        next_change=plan("'Kitchen'",remote,rows,records,{'PR1':'NCC A'})['changes'][0]
        self.assertEqual(next_change['values'][8],1)
        self.assertEqual(next_change['values'][11],first['values'][11])
        remote[4]=next_change['values']
        ledger.save_receipt(self.path,'PR1','PR 1',self.lines,'c',self.payload(1,'2026-11-08','C'))
        rows,records=ledger.summary(self.path)
        self.assertTrue(plan("'Kitchen'",remote,rows,records,{'PR1':'NCC A'})['changes'][0]['delete'])
    def test_double_warning_requires_ack_and_does_not_hide_real_overreceipt(self):
        self.save('a',7)
        warnings=ledger.receipt_warnings(self.path,'PR1',self.lines,'b',self.payload(7))
        self.assertTrue(any('trùng' in w for w in warnings));self.assertTrue(any('vượt' in w for w in warnings))
        with self.assertRaisesRegex(ValueError,'trùng phiếu'):self.save('b',7)
        self.save('b',7,acknowledged=warnings)
        self.assertEqual(ledger.summary(self.path)[0][0]['remaining'],'-4')
    def test_department_cancel_reopen_and_audit(self):
        self.save('a',7);ledger.close_order(self.path,'PR1','KC báo hủy')
        row=ledger.summary(self.path)[0][0];self.assertEqual(row['cancelled'],'3');self.assertEqual(row['remaining'],'0')
        with self.assertRaisesRegex(ValueError,'báo hủy'):self.save('b',2)
        ledger.close_order(self.path,'PR1','KC yêu cầu giao tiếp',True);self.save('b',2)
        self.assertEqual(ledger.summary(self.path)[0][0]['remaining'],'1')
        self.assertTrue(list((self.path.parent/'ledger-backups').glob('*.sqlite')))
        c=sqlite3.connect(self.path)
        try:self.assertGreaterEqual(c.execute('SELECT count(*) FROM audit').fetchone()[0],4)
        finally:c.close()
    def test_stale_source_never_looks_like_zero_receipt_and_revoke_keeps_history(self):
        self.save('a',7)
        rows,_=ledger.summary(self.path,lambda p:False);self.assertIsNone(rows[0]['remaining'])
        ledger.revoke_receipt(self.path,'a',1)
        rows,history=ledger.summary(self.path);self.assertEqual(rows[0]['remaining'],'10');self.assertFalse(history[0]['active'])
    def test_receipts_are_totals_without_separate_history_confirmation(self):
        self.save('a',7)
        row=ledger.summary(self.path)[0][0]
        self.assertEqual(row['remaining'],'3')
        self.assertFalse(row['history_unverified'])
        self.assertEqual(row['local_received'],'7')
        row=ledger.summary(self.path,lambda p:False)[0][0]
        self.assertIsNone(row['remaining'])
        self.assertTrue(row['source_unverified'])
    def test_decimal_and_unknown_unit_duplicate_safety(self):
        items=[{'item_name':'Cam','quantity':'10','unit':'kg','unit_price':'100'}]
        rows=[(2,{'Thực nhận':0,'Đơn vị tính':'kg'})]
        self.assertEqual(ledger.allocations(items,rows,{0:2}),{'0':'0'})
        with self.assertRaises(ValueError):ledger.allocations(items,[(2,{'Thực nhận':None,'Đơn vị tính':'kg'})],{0:2})
        with self.assertRaises(ValueError):ledger.allocations(items,[(2,{'Thực nhận':1,'Đơn vị tính':'thùng'})],{0:2})
        with self.assertRaises(ValueError):ledger.allocations(items,rows,{})
        self.assertEqual(ledger.amount('0.1')+ledger.amount('0.2'),Decimal('0.3'))
        with self.assertRaises(ValueError):ledger.amount('NaN')
    def test_changed_order_definition_is_not_silently_merged(self):
        self.save('a',7)
        changed=[dict(self.lines[0],ordered='20')]
        with self.assertRaisesRegex(ValueError,'Nội dung PR khác'):ledger.save_receipt(self.path,'PR1','PR 1',changed,'b',self.payload(2))

if __name__=='__main__':unittest.main()
