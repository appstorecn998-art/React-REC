import sys,unittest,copy
from pathlib import Path
sys.path.append(str(Path.home()/'Desktop'/'Auto'))
from receiving_sheets import HEADERS,plan,apply

class SheetsTests(unittest.TestCase):
    def setUp(self):
        self.remote=[['Title'],[],[],HEADERS[:]]
        self.row=dict(order_id='order',index=0,name='Muối',unit='kg',ordered='10',received='7',remaining='3',reason='',title='PR 14')
        self.records=[dict(active=True,valid=True,order_id='order',day='2026-11-07')]
    def preview(self,remote=None,row=None):return plan("'1'",remote or self.remote,[row or self.row],self.records,{'order':'NCC A'})
    def test_repeat_is_noop_and_delivery_updates_old_row_preserving_notes(self):
        first=self.preview();self.assertEqual(len(first['changes']),1)
        remote=copy.deepcopy(self.remote);remote[3]=HEADERS+['REC_ID'];remote.append(first['changes'][0]['values'])
        remote[4][10]='Hẹn giao ngày mai'
        self.assertEqual(self.preview(remote)['changes'],[])
        row=dict(self.row,received='10',remaining='0')
        update=self.preview(remote,row)['changes'][0]
        self.assertEqual(update['row'],5);self.assertTrue(update['delete']);self.assertEqual(update['old'][10],'Hẹn giao ngày mai')
    def test_missing_sources_and_surplus_requires_supplemental_pr(self):
        self.assertIn('Chờ mở PR',self.preview(row=dict(self.row,remaining='-1'))['changes'][0]['values'][9])
        result=self.preview(row=dict(self.row,remaining=None));self.assertEqual(result['skipped'],1)

    def test_unverified_source_keeps_quantities_and_recovers_only_blank_cells(self):
        remote=copy.deepcopy(self.remote)
        remote[3]=HEADERS+['REC_ID']
        remote.append(self.preview()['changes'][0]['values'][:])
        remote[4][10]='Giữ ghi chú'
        row=dict(self.row,remaining=None,recorded_received='7')
        self.assertEqual(self.preview(remote,row)['changes'][0]['values'][7:9],[7,3])
        remote[4][8]=''
        restored=self.preview(remote,row)['changes'][0]['values']
        self.assertEqual(restored[7:9],[7,3])
        self.assertIn('Số theo lần ghi sổ trước',restored[9])
        self.assertEqual(restored[10],'Giữ ghi chú')
        remote[4]=restored
        self.assertEqual(self.preview(remote,row)['changes'],[])

    def test_department_removes_verified_completion_on_old_tab(self):
        from receiving_department_sheets import preview,apply_preview
        from receiving_sheets_layout import PHYSICAL_HEADERS,physical_values

        old=self.preview()['changes'][0]['values']
        header=[['Title'],[],[],PHYSICAL_HEADERS]
        remote={'Kitchen':header+[physical_values(old)],'FB':header}
        class Client:
            def read_tabs(s,titles):return {title:remote[title] for title in titles}
            def request(s,method,path,**kwargs):
                if method=='GET':
                    return {'sheets':[{'properties':{'title':title,'sheetId':i,
                        'gridProperties':{'rowCount':1000,'columnCount':26}}} for i,title in enumerate(remote)]}
                s.requests=kwargs['json']['requests']
        client=Client()
        complete=dict(self.row,received='10',remaining='0')
        result=preview(client,[complete],self.records,{'order':'NCC A'},{'order':{'department':'FB'}})
        self.assertEqual([(c['tab'],c.get('delete')) for c in result['changes']],[('Kitchen',True)])
        apply_preview(client,result)
        deleted=[r['deleteDimension']['range'] for r in client.requests if 'deleteDimension' in r]
        self.assertEqual(deleted,[dict(sheetId=0,dimension='ROWS',startIndex=4,endIndex=5)])
        remote['Kitchen'][4]+=['Ghi chú ngoài bảng']
        result=preview(client,[complete],self.records,{'order':'NCC A'},{})
        self.assertEqual(result['changes'],[])
        self.assertEqual(len(result['department_issues']),1)
    def test_manual_duplicates_and_changed_headers_are_blocked(self):
        remote=copy.deepcopy(self.remote);remote.append([1,'','NCC A','','Muối'])
        with self.assertRaises(ValueError):self.preview(remote)
        remote=copy.deepcopy(self.remote);remote[3][1]='Changed'
        with self.assertRaises(ValueError):self.preview(remote)
    def test_changed_sheet_prevents_write_and_raw_values_are_used(self):
        preview=self.preview()
        class Client:
            def read(s):return "'1'",[['Changed']]
            def write(s,data):raise AssertionError('No write permitted')
        with self.assertRaises(ValueError):apply(Client(),preview)
        class Good:
            def read(s):return "'1'",self.remote
            def write(s,data):s.data=data
        client=Good();self.assertEqual(apply(client,preview),1)
        self.assertEqual(client.data[0]['range'],"'1'!L4")
        self.assertEqual(client.data[1]['values'][0][8],3)

if __name__=='__main__':unittest.main()
