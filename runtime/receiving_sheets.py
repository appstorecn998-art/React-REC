"""Preview-first Sheets sync. Only managed REC_ID rows may be updated."""
import hashlib,json
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote
from receiving_service import digest

try:
    SHEET_ID = json.loads((Path(__file__).resolve().parents[1]/'data-location.json').read_text(encoding='utf-8')).get('sheet_id', '')
except (OSError, ValueError, AttributeError):
    SHEET_ID = ''
HEADERS=['STT','Ngày nhận','Nhà cung cấp','Mã PO / DO','Tên hàng hóa / Quy cách','ĐVT','SL Đặt (PO)','Thực nhận','Thiếu','Trạng thái / Phương án xử lý','Ghi chú / Hẹn giao bù']

class SheetsClient:
    def __init__(self,root):
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import AuthorizedSession
        key=Path(root)/'google-sheets-key.json'
        if not key.is_file():raise ValueError('Chưa có google-sheets-key.json trong thư mục cấu hình REC (Cài đặt → Thiết lập máy).')
        self.session=AuthorizedSession(Credentials.from_service_account_file(str(key),scopes=['https://www.googleapis.com/auth/spreadsheets']))
        try:sheet_id=json.loads((Path(root)/'.receiving/runtime.json').read_text(encoding='utf-8')).get('sheet_id',SHEET_ID)
        except (OSError,ValueError):sheet_id=SHEET_ID
        if not sheet_id:raise ValueError('Chưa cấu hình mã Google Sheets trong Quản trị.')
        if not isinstance(sheet_id,str) or not __import__('re').fullmatch('[A-Za-z0-9_-]+',sheet_id):raise ValueError('Mã Google Sheets không hợp lệ.')
        self.base=f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}'
    def request(self,method,path,**kwargs):
        try:r=self.session.request(method,self.base+path,timeout=30,**kwargs)
        except Exception:raise ValueError('Không kết nối được Google Sheets. Kiểm tra mạng rồi xem trước lại.') from None
        if r.status_code==429:raise ValueError('Google Sheets đang giới hạn số lượt gọi. Thử tải lại sau một phút.')
        if not r.ok:raise ValueError(f'Google Sheets từ chối yêu cầu (HTTP {r.status_code}). Kiểm tra API và quyền chỉnh sửa của tài khoản dịch vụ.')
        return r.json()
    def read_tabs(self,titles):
        if not titles:return {}
        ranges=["'"+title.replace("'","''")+"'" for title in titles]
        values=self.request('GET','/values:batchGet',params={'ranges':ranges,'valueRenderOption':'UNFORMATTED_VALUE'})['valueRanges']
        return {title:entry.get('values',[]) for title,entry in zip(titles,values,strict=True)}

    def read(self,title=None):
        meta=self.request('GET','',params={'fields':'sheets.properties'})
        sheet=next((s['properties'] for s in meta['sheets'] if (s['properties']['sheetId']==0 if title is None else s['properties']['title']==title)),None)
        if not sheet:raise ValueError('Không tìm thấy trang tính gid=0. Chưa cập nhật.')
        self.current_sheet_id=sheet['sheetId']
        title="'"+sheet['title'].replace("'","''")+"'"
        rows=self.request('GET','/values/'+quote(title+'!A:N',safe=''),params={'valueRenderOption':'UNFORMATTED_VALUE'}).get('values',[])
        from receiving_sheets_layout import logical_rows
        rows=logical_rows(rows)
        return title,rows
    def write_and_delete(self,data,rows):
        # Update cells and remove only REC-managed rows in one atomic request.
        import re
        requests=[]
        for item in data:
            match=re.search(r'!([A-L])(\d+)',item['range'])
            start_col=ord(match[1])-ord('A');start_row=int(match[2])-1
            cells=[]
            from receiving_sheets_layout import physical_values
            for value in physical_values(item['values'][0]):
                if value is None or value=='':entry={}
                elif isinstance(value,bool):entry={'userEnteredValue':{'boolValue':value}}
                elif isinstance(value,(int,float)):entry={'userEnteredValue':{'numberValue':value}}
                else:entry={'userEnteredValue':{'stringValue':str(value)}}
                cells.append(entry)
            requests.append({'updateCells':{'start':{'sheetId':getattr(self,'current_sheet_id',0),'rowIndex':start_row,'columnIndex':start_col},'rows':[{'values':cells}],'fields':'userEnteredValue'}})
        for row in sorted(set(rows),reverse=True):
            requests.append({'deleteDimension':{'range':{'sheetId':getattr(self,'current_sheet_id',0),'dimension':'ROWS','startIndex':row-1,'endIndex':row}}})
        return self.request('POST',':batchUpdate',json={'requests':requests})

    def write(self,data):
        from receiving_sheets_layout import physical_values
        data=[dict(item,range=item['range'].replace(':L',':N'),values=[physical_values(row) for row in item['values']]) for item in data]
        return self.request('POST','/values:batchUpdate',json={'valueInputOption':'RAW','data':data})

def fingerprint(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def padded(row):return (list(row)+['']*12)[:12]
def number(value):
    f=Fraction(value)
    return f.numerator if f.denominator==1 else float(f)

def display_unit(value):return str(value or '').strip().capitalize()

def unverified_values(old,row):
    values=old[:]
    values[9]='Nguồn đã đổi / cần kiểm tra lại'
    recorded=row.get('recorded_received')
    if recorded is not None and (old[7]=='' or old[8]==''):
        received=Fraction(recorded)
        if old[7]=='':values[7]=number(received)
        if old[8]=='':values[8]=number(max(Fraction(0),Fraction(row['ordered'])-received))
        values[9]+=' · Số theo lần ghi sổ trước'
    elif 'Số theo lần ghi sổ trước' in str(old[9]):
        values[9]=old[9]
    return values

def plan(title,remote,summary,records,suppliers,*,renumber=True):
    if len(remote)<4 or padded(remote[3])[:11]!=HEADERS:raise ValueError('Tiêu đề Google Sheets đã khác mẫu 11 cột. Chưa cập nhật để tránh ghi sai cột.')
    if len(remote[3])>12 or (len(remote[3])==12 and remote[3][11] not in ('','REC_ID')):raise ValueError('Cột L đang được sử dụng. Cần chọn vị trí mã đồng bộ trước.')
    managed={}
    for index,row in enumerate(remote[4:],5):
        key=padded(row)[11]
        if key:
            if not str(key).startswith('REC-'):raise ValueError('Cột REC_ID có dữ liệu không hợp lệ.')
            if key in managed:raise ValueError('Google Sheets có REC_ID trùng. Kiểm tra bảng trước khi đồng bộ.')
            managed[key]=(index,padded(row))
    days={};date_issues={}
    for receipt in records:
        if not receipt['active'] or (not receipt['valid'] and 'uncertain_indices' not in receipt):continue
        if 'source_rows' not in receipt:
            days.setdefault((receipt['order_id'],None),[]).append(receipt['day'])
            continue
        values={int(index):value for index,value in receipt['source_rows']}
        for index,source in receipt.get('allocation_rows',{}).items():
            if source is None or str(index) in receipt.get('uncertain_indices',[]):continue
            for physical in source if isinstance(source,(list,tuple)) else [source]:
                raw=values.get(int(physical),{}).get('Ngày nhận hàng xác nhận')
                day=confirmed_receipt_date(raw)
                if not day:
                    date_issues[(receipt['order_id'],int(index))]='Thiếu/sai Ngày nhận hàng xác nhận: '+str(receipt.get('sheet',''))+' dòng '+str(physical)
                    continue
                days.setdefault((receipt['order_id'],int(index)),[]).append(day)
    history_review=[]
    changes=[];skipped=0;append=max(5,len(remote)+1)
    for row in summary:
        key='REC-'+fingerprint([row['order_id'],row['index']])[:32]
        existing=managed.get(key)
        if row.get('history_unverified'):
            skipped+=1
            if existing:history_review.append(row['name'])
            continue
        if row['remaining'] is None or row.get('source_unverified'):
            skipped+=1
            if existing:
                index,old=existing;values=unverified_values(old,row)
                if values!=old:changes.append({'action':'Đánh dấu cần rà','row':index,'name':row['name'],'supplier':old[2],'values':values,'old':old})
            continue
        remaining=Fraction(row['remaining'])
        if remaining==0:
            if existing:
                index,old=existing;values=old[:];values[8]=0
                action='Xóa dòng đã ngừng giao bù' if row.get('reason') else 'Xóa dòng đã nhận đủ'
                changes.append({'action':action,'row':index,'name':row['name'],'supplier':old[2],'values':values,'old':old,'delete':True})
            continue # history stays in the local ledger, shortage report only
        supplier=suppliers.get(row['order_id'],'Chưa xác định nhà cung cấp')
        if supplier=='Chưa xác định nhà cung cấp':skipped+=1;continue
        if not existing and any(str(padded(r)[2]).strip()==supplier and str(padded(r)[4]).strip()==row['name'] and not padded(r)[11] for r in remote[4:]):
            raise ValueError('Bảng có dòng nhập tay cùng nhà cung cấp và mặt hàng. Cần đối chiếu dòng cũ trước để tránh ghi trùng: '+row['name'])
        date_key=(row['order_id'],int(row['index']))
        if date_key in date_issues:
            skipped+=1
            if existing:
                index,old=existing;values=old[:];values[9]=date_issues[date_key]
                if values!=old:changes.append(dict(action='Báo thiếu ngày xác nhận',row=index,name=row['name'],supplier=old[2],values=values,old=old))
            continue
        date=max(days.get(date_key,days.get((row['order_id'],None),[''])))
        if date:
            from datetime import datetime
            date=datetime.strptime(date,'%Y-%m-%d').strftime('%d/%m/%Y')
        index,old=existing if existing else (append,None)
        if not date and old:date=old[1]
        if not existing:append+=1
        status='Đã ngừng nhận phần còn thiếu' if row['reason'] else 'Còn thiếu' if remaining>0 else 'Đã nhận đủ' if remaining==0 else 'Nhận dư — kiểm tra'
        if remaining<0:
            reasons=[]
            for receipt in records:
                if receipt.get('active') and receipt.get('valid') and receipt['order_id']==row['order_id']:
                    entry=(receipt.get('conversions') or {}).get(str(row['index']),(receipt.get('conversions') or {}).get(row['index'],{})) or {}
                    rule=entry.get('overreceipt_approval')
                    if rule:
                        reason=str(rule.get('reason','')).strip()
                        from supplier_rules import normalize_name
                        reasons.append('Hàng nguyên khối' if 'nguyen khoi' in normalize_name(reason) else reason)
            status='Dư '+str(number(-remaining)).replace('.',',')+' '+display_unit(row['unit'])+' · Chờ mở PR'
            if reasons:status+=' · '+'; '.join(dict.fromkeys(reasons))
        values=[old[0] if old else index-4,date,supplier,row['title'],row['name'],display_unit(row['unit']),number(row['ordered']),number(row['received']),number(max(Fraction(0),remaining)),status,old[10] if old else '',key]
        if old==values:continue
        changes.append({'action':'Cập nhật' if old else 'Thêm mới','row':index,'name':row['name'],'supplier':supplier,'values':values,'old':old})
    # Previously synced rows absent locally are never silently removed.
    local_ids={'REC-'+fingerprint([r['order_id'],r['index']])[:32] for r in summary}
    for key in set(managed)-local_ids:
        index,old=managed[key];values=old[:];values[9]='Không còn trong sổ REC — cần kiểm tra'
        if values!=old:changes.append({'action':'Đánh dấu cần rà','row':index,'name':old[4],'supplier':old[2],'values':values,'old':old})
    deleted={c['row'] for c in changes if c.get('delete')}
    if deleted and renumber:
        by_row={c['row']:c for c in changes}
        protected={'REC-'+fingerprint([r['order_id'],r['index']])[:32] for r in summary if r.get('history_unverified')}
        for key,(index,old) in managed.items():
            if key in protected or index in deleted:continue
            sequence=index-4-sum(r<index for r in deleted)
            if index in by_row:by_row[index]['values'][0]=sequence
            elif old[0]!=sequence:
                values=old[:];values[0]=sequence
                changes.append({'action':'Đánh lại STT','row':index,'name':old[4],'supplier':old[2],'values':values,'old':old})
        for c in changes:
            if c['old'] is None:c['values'][0]=c['row']-4-sum(r<c['row'] for r in deleted)
    skipped+=len(set(managed)-local_ids)
    return {'history_review':history_review,'title':title,'remote_hash':fingerprint(remote),'changes':changes,'skipped':skipped,'add_key':len(remote[3])<12 or remote[3][11]!='REC_ID'}

def apply(client,preview):
    if preview.get('history_review'):raise ValueError('Có dòng đã tồn tại trên Sheets nhưng lịch sử PR chưa xác minh. Giữ nguyên Sheets; xác minh trên REC trước: '+', '.join(preview['history_review']))
    title,remote=client.read()
    if title!=preview['title'] or fingerprint(remote)!=preview['remote_hash']:raise ValueError('Google Sheets đã thay đổi sau khi xem trước. Xem trước lại rồi duyệt.')
    data=[]
    if preview['add_key'] and preview['changes']:data.append({'range':title+'!L4','values':[['REC_ID']]})
    for change in preview['changes']:
        if change.get('delete'):continue
        i=change['row'];data.append({'range':f'{title}!A{i}:L{i}','values':[change['values']]})
    deleted=[c['row'] for c in preview['changes'] if c.get('delete')]
    if deleted:client.write_and_delete(data,deleted)
    elif data:client.write(data)
    return len(preview['changes'])

def file_signature(path):
    path=Path(path)
    return tuple(digest(p) if p.exists() else None for p in (path,Path(str(path)+'-wal')))


def confirmed_receipt_date(value):
    from datetime import datetime,date
    if isinstance(value,datetime):return value.date().isoformat()
    if isinstance(value,date):return value.isoformat()
    raw=str(value or '').strip()
    for fmt in ('%d/%m/%Y','%Y-%m-%d','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S'):
        try:return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:pass
    return None


def table_borders(sheet_id,last_row):
    """Visible accounting columns only; REC_ID and title rows stay untouched."""
    edge={'style':'SOLID','color':{'red':0,'green':0,'blue':0}}
    return {'updateBorders':{'range':{'sheetId':sheet_id,'startRowIndex':3,'endRowIndex':max(4,last_row),'startColumnIndex':0,'endColumnIndex':13},**{key:dict(edge) for key in ('top','bottom','left','right','innerHorizontal','innerVertical')}}}
