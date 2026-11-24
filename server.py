"""Local REC bridge: read snapshots and run explicitly selected OCR uploads through REC."""
import hashlib,json,mimetypes,sys,threading,re,time,secrets,logging,copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import date,datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,unquote,parse_qs

from local_runtime import APP,PROFILE,STORE,activate
activate()
ROOT=STORE/'Thang 11'/'Ngay 17'
REPORT=ROOT/'TongHopPhieuNgay_17-11-2026.xlsx'
sys.path.insert(0,str(APP))
from receiving_service import snapshot,day_images,invoice_pages,atomic_json
from receiving_preferences import nickname

try:
    from warehouse_directory import load_warehouse_directory
except ImportError:
    load_warehouse_directory=None
from AutoWatcher import parse_simple_quantity, excel_number

FIELDS=['Tên hàng trên phiếu (Ảnh)','Tên vật tư chuẩn','Tên chuẩn hệ thống','Mã vật tư','Đơn vị tính','Thực nhận','Đơn giá','Bộ phận','Mã kho','Tên kho','Nhà cung cấp','Thời gian chụp','Giờ nhận','Ngày nhận hàng xác nhận','Số lượng','Đơn vị trên phiếu','Trạng thái','Ghi chú','Thành tiền in trên phiếu','Số chứng từ trên phiếu','Ngày chứng từ trên phiếu','Tổng tiền in trên phiếu','Tiền hàng in trước thuế/chiết khấu','Tiền hàng tính lại từ lượng giao']
lock=threading.Lock();cache={};allowed_images={};pr_result_cache={}
PR_CACHE_FILE=STORE/'.receiving'/'react-pr-cache.json'
_pr_disk_cache=None

def _load_pr_disk_cache():
    global _pr_disk_cache
    if _pr_disk_cache is not None:return _pr_disk_cache
    try:
        value=json.loads(PR_CACHE_FILE.read_text(encoding='utf8'))
        _pr_disk_cache=value if isinstance(value,dict) else {}
    except (OSError,ValueError,TypeError):
        _pr_disk_cache={}
    return _pr_disk_cache

def _clear_pr_disk_cache():
    global _pr_disk_cache
    _pr_disk_cache={}
    try:PR_CACHE_FILE.unlink()
    except OSError:pass

def _store_pr_disk_cache(key,result,photos):
    disk=_load_pr_disk_cache();disk['|'.join(key)]={'result':result,'photos':[str(p) for p in photos]}
    if len(disk)>64:
        for old in list(disk)[:len(disk)-64]:disk.pop(old,None)
    atomic_json(PR_CACHE_FILE,disk)
from ocr_jobs import Jobs
from preview_cache import attach_lazy as attach_previews,resolve_preview,content_identity,saved_rotation
ocr_jobs=Jobs(STORE)
session_token=secrets.token_urlsafe(32)
sheets_worker=ThreadPoolExecutor(max_workers=1, thread_name_prefix='rec-sheets')


def sync_after_ledger_change():
    from rec_workspaces import ledger_path, sheets
    from receiving_ledger import pending_sync, sync_result

    path=ledger_path(STORE)
    try:
        with ocr_jobs.guard:
            job=ocr_jobs.public().get('job')
            if job and job.get('status') in ('importing','running'):
                raise ValueError('OCR đang chạy. Mở Đồng bộ Sheets để thử lại sau khi hoàn tất.')
        sheets(PROFILE,STORE,automatic=True)
    except Exception as error:
        logging.warning('Không hoàn tất tự đồng bộ Sheets',exc_info=True)
        message=str(error) if isinstance(error,ValueError) else 'Lỗi khi tự đồng bộ Google Sheets.'
        sync_result(path,pending_sync(path),message)

def available_days():
    found={}
    candidates=list(STORE.glob('Thang */Ngay */TongHopPhieuNgay_*.xlsx'))
    candidates+=list(STORE.glob('[0-9][0-9][0-9][0-9]/Thang */Ngay */TongHopPhieuNgay_*.xlsx'))
    for report in sorted(candidates):
        match=re.fullmatch(r'TongHopPhieuNgay_(\d{2}-\d{2}-\d{4})',report.stem)
        if not match:continue
        day=datetime.strptime(match[1],'%d-%m-%Y').date()
        key=day.isoformat()
        if key in found:raise ValueError('Có nhiều báo cáo REC cùng ngày; cần chọn lại thư mục dữ liệu.')
        found[key]=report
    return dict(sorted(found.items(),reverse=True))

def receipt_row(number, row):
    result = {key: row.get(key) for key in FIELDS}
    delivered, received = (parse_simple_quantity(row.get(key)) for key in ('Số lượng', 'Thực nhận'))
    # Both values use the printed unit on REC exports. Older rows without
    # that unit have no reliable basis for this comparison.
    result['Chênh lệch thực nhận'] = (
        excel_number(received - delivered)
        if row.get('Đơn vị trên phiếu') and delivered is not None and received is not None
        else None
    )
    return dict(sourceRow=number, **result)


def receipt_time(rows):
    # Imported receipts can span several photos: use their earliest capture time.
    explicit=any('Giờ nhận' in value for _,value in rows)
    key='Giờ nhận' if explicit else 'Thời gian chụp'
    times={str(value.get(key) or '')[:5] for _,value in rows}
    if explicit:return next(iter(times)) if len(times)==1 else ''
    return min(times-{''},default='')


def image_version(paths):
    return hashlib.sha256(json.dumps([(content_identity(p),saved_rotation(p)) for p in paths]).encode()).hexdigest()


_department_cache={}

def department_options():
    path=PROFILE/'DanhMuc.xlsm'
    if not load_warehouse_directory or not path.exists():
        return [], 'Chưa có danh mục kho. Chưa thể chọn kho/bộ phận.'
    try:
        stat=path.stat()
        stamp=(stat.st_mtime_ns,stat.st_size,stat.st_ctime_ns)
        cached=_department_cache.get('value')
        if cached and cached[0]==stamp:return cached[1], ''
        directory=load_warehouse_directory(path)
    except (OSError, ValueError) as exc:
        logging.warning('Cannot load warehouse directory: %s',exc)
        return [], 'Chưa đọc được DanhMuc.xlsm. Nếu đang mở trong Excel, đóng file rồi tải lại ngày. Bạn vẫn có thể xem phiếu; tạm thời chưa thể chọn kho/bộ phận.'
    options=[{'code':code,'name':name,'department':department} for code,(name,department) in directory.items()]
    _department_cache['value']=(stamp,options)
    return options, ''


def load(day=None,force=False):
    with lock:
        days=available_days()
        day=day or next(iter(days),date.today().isoformat())
        selected=date.fromisoformat(day)
        if selected.isoformat()!=day:raise ValueError('Ngày không hợp lệ')
        if day not in days:
            departments,warning=department_options()
            return dict(day=selected.strftime('%d/%m/%Y'),dayId=day,days=[{'value':key,'label':date.fromisoformat(key).strftime('%d/%m/%Y')} for key in days],receipts=[],departments=departments,directoryWarning=warning,scope='Chưa có phiếu ngày '+selected.strftime('%d/%m/%Y'),readOnly=True)
        report=days[day]
        stat=report.stat();review_path=report.parent/'.receiving/reviewed.json'
        source_review=review_path.with_name('reviewed-sources.json')
        current=(stat.st_mtime_ns,stat.st_size,hashlib.sha256(review_path.read_bytes()).hexdigest() if review_path.exists() else None,hashlib.sha256(source_review.read_bytes()).hexdigest() if source_review.exists() else None)
        existing=cache.get(day)
        # Keep recent days hot; reload explicitly refreshes archive/page identity.
        if not force and existing and existing[0]==current:
            try:
                images_unchanged=all(d.get('imageVersion')==image_version([allowed_images[url.rsplit('/',1)[-1]] for url in d['pages']]) for d in existing[1]['receipts'])
            except (OSError,KeyError):images_unchanged=False
            if images_unchanged:
                result=dict(existing[1])
                result['departments'],result['directoryWarning']=department_options()
                from receipt_workflow import reviewed
                states=reviewed(report,existing[2])
                result['receipts']=[dict(d,reviewed=states.get(d['file'],False)) for d in result['receipts']]
                result['days']=[{'value':key,'label':date.fromisoformat(key).strftime('%d/%m/%Y')} for key in days];return result
        started=time.perf_counter()
        version,sheets=snapshot(report)
        from receipt_workflow import reviewed,review_token
        review_states=reviewed(report,sheets)
        images=day_images(report.parent);docs=[];known={}
        for name,rows in sheets:
            if not rows:continue
            pages=[];source_paths=[]
            for image in invoice_pages(name,rows,images):
                st=image.stat();identity=f'{image.resolve()}:{st.st_mtime_ns}:{st.st_size}'
                key=hashlib.sha256(identity.encode()).hexdigest()[:24]
                known[key]=image;pages.append('/api/image/'+key);source_paths.append(image)
            values=[receipt_row(r,v) for r,v in rows]
            corrected=attach_previews(source_paths,known)
            warehouses={str(r.get('Mã kho') or '') for r in values}
            docs.append(dict(id=day+'::'+name,file=name,reviewed=review_states.get(name,False),reviewToken=review_token(report,name,rows,images),supplier=rows[0][1].get('Nhà cung cấp',''),supplierNickname=nickname(PROFILE,rows[0][1].get('Nhà cung cấp') or ''),pages=pages,rows=values,correctedPages=corrected,imageVersion=image_version(source_paths),receiptTime=receipt_time(rows),warehouseCode=next(iter(warehouses)) if len(warehouses)==1 else None))
        departments,directory_warning=department_options()
        result=dict(day=date.fromisoformat(day).strftime('%d/%m/%Y'),dayId=day,days=[{'value':key,'label':date.fromisoformat(key).strftime('%d/%m/%Y')} for key in days],report=report.name,receipts=docs,departments=departments,scope=f'{len(docs)} phiếu REC ngày '+date.fromisoformat(day).strftime('%d/%m/%Y'),readOnly=True,readMs=round((time.perf_counter()-started)*1000))
        result['version']=version
        result['directoryWarning']=directory_warning
        allowed_images.update(known)
        cache[day]=(current,result,sheets)
        while len(cache)>4:cache.pop(next(iter(cache)))
        return result

def encode(v):
    if isinstance(v,(date,datetime)):return v.isoformat()
    raise TypeError(type(v).__name__)

class Handler(BaseHTTPRequestHandler):
    def trusted(self):
        if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'):
            self.send_error(403);return False
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:8767','http://127.0.0.1:8768','http://localhost:8767','http://'+self.headers.get('Host','')):
            self.send_error(403);return False
        if self.headers.get('Sec-Fetch-Site')=='cross-site':self.send_error(403);return False
        return True
    def do_POST(self):
        if not self.trusted():return
        if not secrets.compare_digest(self.headers.get('X-REC-Token',''),session_token):self.send_error(403);return
        if self.headers.get_content_type()!='application/json':self.send_error(415);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=115*1024*1024:self.send_error(413);return
            self.connection.settimeout(90)
            body=self.rfile.read(size)
            if len(body)!=size:raise ValueError('Nhập ảnh chưa đầy đủ, chọn lại nhóm ảnh.')
            payload=json.loads(body)
            if not isinstance(payload,dict):raise ValueError('Dữ liệu gửi không hợp lệ.')
            path=urlsplit(self.path).path
            if path=='/api/ocr/upload':result=ocr_jobs.stage(payload)
            elif path=='/api/ocr/start':result=ocr_jobs.start(payload)
            elif path=='/api/assistant':
                from rec_assistant import ask
                result=ask(PROFILE,STORE,available_days(),payload)
            elif path in ('/api/receipt/review','/api/export'):
                from receipt_workflow import review, export
                day=payload.get('day');report=available_days().get(day)
                if report is None:raise ValueError('Ngày không có báo cáo REC.')
                with ocr_jobs.guard:
                    job=ocr_jobs.public().get('job')
                    if job and job.get('day')==day and job.get('status') in ('importing','running'):
                        raise ValueError('Ngày này đang được OCR. Chờ hoàn tất rồi thử lại.')
                    result=review(report,payload,store=STORE) if path.endswith('/review') else export(STORE,PROFILE,report,payload)
                with lock:
                    cache.clear();pr_result_cache.clear();_clear_pr_disk_cache()
            elif path=='/api/knowledge/pair':
                from knowledge import update_pair
                result=update_pair(PROFILE,payload)
            elif path=='/api/debt/supplier':
                from rec_supplier_reconciliation import SupplierResolver, guard
                with guard:
                    result = SupplierResolver(PROFILE, STORE).confirm(available_days(), payload)
            elif path.startswith('/api/workspace/'):
                import rec_workspaces as workspace
                if path=='/api/workspace/settings':
                    result=workspace.update_settings(PROFILE,payload)
                elif path=='/api/workspace/library':
                    result=workspace.update_pr(STORE,payload)
                elif path=='/api/workspace/prices':
                    from receiving_price_pr import save_reference
                    day,sheet,number,signature,previous=(payload.get(key) for key in
                        ('day','sheet','number','signature','previous'))
                    report=available_days().get(day) if isinstance(day,str) else None
                    if report is None or any(not isinstance(s,str) for s in (sheet,number,signature,previous)) or len(number)>200:
                        raise ValueError('Phiếu hoặc số PR không hợp lệ.')
                    with ocr_jobs.guard:
                        job=ocr_jobs.public().get('job')
                        if job and job.get('day')==day and job.get('status') in ('importing','running'):
                            raise ValueError('Chờ OCR hoàn tất trước khi lưu.')
                        save_reference(report,sheet,number,signature,previous)
                    result={'saved':True}
                elif path=='/api/workspace/ledger':
                    from receipt_workflow import guard
                    with ocr_jobs.guard,guard:
                        job=ocr_jobs.public().get('job')
                        if job and job.get('status') in ('importing','running'):
                            raise ValueError('Chờ OCR hoàn tất trước khi ghi sổ.')
                        result=(workspace.post_day(STORE,available_days(),payload)
                                if payload.get('action')=='post_day' else workspace.update_ledger(STORE,payload))
                        if result.get('saved') or any(status=='Đã ghi sổ' for _,status,_ in result.get('results',[])):
                            with lock:
                                pr_result_cache.clear()
                                _clear_pr_disk_cache()
                            sheets_worker.submit(sync_after_ledger_change)
                elif path=='/api/workspace/sheets':
                    from receipt_workflow import guard
                    token=payload.get('token')
                    if not isinstance(token,str) or not token:
                        raise ValueError('Mở bản xem trước trước khi cập nhật.')
                    with ocr_jobs.guard,guard:
                        job=ocr_jobs.public().get('job')
                        if job and job.get('status') in ('importing','running'):
                            raise ValueError('Chờ OCR hoàn tất trước khi đồng bộ.')
                        result=workspace.sheets(PROFILE,STORE,token)
                else:
                    self.send_error(404);return
            elif path in ('/api/receipt/action','/api/receipt/pr'):
                from receipt_actions import receipt_action, save_pr
                day=payload.get('day')
                report=available_days().get(day)
                if report is None:
                    raise ValueError('Ngày không có báo cáo REC.')
                with ocr_jobs.guard:
                    job=ocr_jobs.public().get('job')
                    if job and job.get('day')==day and job.get('status') in ('importing','running'):
                        raise ValueError('Ngày này đang được OCR. Chờ hoàn tất rồi thử lại.')
                    if path=='/api/receipt/pr':
                        outcome=save_pr(STORE,report,payload)
                        result={'saved':True,**(outcome or {})}
                    else:
                        result=receipt_action(PROFILE,report,payload,store=STORE)
                with lock:
                    cache.clear()
                    pr_result_cache.clear();_clear_pr_disk_cache()
            elif path=='/api/receipt/row':
                with ocr_jobs.guard:
                    day, sheet, row = (payload.get(key) for key in ('day', 'sheet', 'row'))
                    changes = payload.get('changes')
                    allowed = {'Tên hàng trên phiếu (Ảnh)', 'Mã vật tư', 'Đơn vị tính', 'Số lượng', 'Thực nhận', 'Đơn giá'}
                    days = available_days()
                    if not isinstance(day, str) or day not in days or not isinstance(sheet, str) or type(row) is not int or row < 2:
                        raise ValueError('Không xác định được dòng hàng cần sửa.')
                    if not isinstance(changes, dict) or not changes or changes.keys() - allowed or any(not isinstance(value, str) for value in changes.values()):
                        raise ValueError('Dữ liệu sửa dòng không hợp lệ.')
                    if 'Tên hàng trên phiếu (Ảnh)' in changes and not changes['Tên hàng trên phiếu (Ảnh)'].strip():
                        raise ValueError('Tên hàng trên phiếu không được để trống.')
                    job = ocr_jobs.public().get('job')
                    if job and job.get('day') == day and job.get('status') in ('importing', 'running'):
                        raise ValueError('Ngày này đang được OCR. Chờ hoàn tất rồi lưu.')
                    version, sheets = snapshot(days[day])
                    if version != payload.get('version') or not any(name == sheet and any(index == row for index, _ in rows) for name, rows in sheets):
                        raise ValueError('Dòng hàng đã thay đổi. Tải lại phiếu trước khi lưu.')
                    from AutoWatcher import load_catalog_data
                    from receiving_service import edit_row
                    catalog, _ = load_catalog_data(PROFILE/'DanhMuc.xlsm')
                    if 'Mã vật tư' in changes:
                        changes['Mã vật tư'] = changes['Mã vật tư'].strip() or 'CHUA CO MA'
                    edit_row(days[day], version, sheet, row, changes, catalog)
                    cache.pop(day, None)
                    result = {'saved': True}
            elif path=='/api/receipt/metadata':
                with ocr_jobs.guard:
                    day=payload.get('day');days=available_days()
                    if day not in days:raise ValueError('Ngày không có báo cáo REC.')
                    job=ocr_jobs.public().get('job')
                    if job and job.get('day')==day and job.get('status') in ('importing','running'):raise ValueError('Ngày này đang được OCR; chờ hoàn tất rồi lưu.')
                    if 'sheets' in payload and not isinstance(payload['sheets'],list):raise ValueError('Danh sách phiếu không hợp lệ.')
                    from receipt_metadata import save
                    directory=load_warehouse_directory(PROFILE/'DanhMuc.xlsm')
                    save(days[day],payload.get('version'),payload.get('sheets') if 'sheets' in payload else payload.get('sheet'),payload.get('changes'),directory)
                    cache.pop(day,None);result={'saved':True}
            else:self.send_error(404);return
            self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store')
        except (ValueError,TypeError,KeyError) as exc:
            self.reply(json.dumps({'error':ocr_jobs._redact(str(exc))},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',400)
        except PermissionError:
            self.reply(json.dumps({'error':'Chưa lưu được. Đóng báo cáo trong Excel/WPS rồi thử lại; bản trước được giữ nguyên.'},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',409)
        except Exception:
            self.reply(json.dumps({'error':'Chưa nhận được ảnh. Kiểm tra định dạng, dung lượng và cấu hình REC.'},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',500)
    def do_GET(self):
        if not self.trusted():return
        path=urlsplit(self.path).path
        try:
            if path=='/api/receipts/search':
                from receipt_history import search
                query=parse_qs(urlsplit(self.path).query)
                result=search(available_days(),PROFILE,query.get('start',[''])[0],query.get('end',[''])[0],query.get('q',[''])[0])
                self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
            if path in ('/api/export/preview','/api/export/download'):
                from receipt_workflow import preview, download, guard
                query=parse_qs(urlsplit(self.path).query);day=query.get('day',[''])[0]
                report=available_days().get(day)
                if report is None:raise ValueError('Ngày không có báo cáo REC.')
                with guard:
                    if path.endswith('/preview'):
                        result=preview(STORE,report)
                        self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
                    index=int(query.get('file',['-1'])[0]);target=download(STORE,report,index)
                    self.reply(target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream','no-store');return
            if path=='/api/ocr/status':
                result=ocr_jobs.public();result['token']=session_token
                self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
            if path=='/api/knowledge':
                from knowledge import inventory
                self.reply(json.dumps(inventory(PROFILE),ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
            if path.startswith('/api/workspace/'):
                import rec_workspaces as workspace
                query=parse_qs(urlsplit(self.path).query)
                def pr_pages():
                    from receipt_actions import library_photos, pr_library
                    from receiving_pr_library import load, title
                    library=pr_library(STORE)
                    key=query.get('key',[''])[0]
                    record=load(library).get(key)
                    if record is None:
                        raise ValueError('Không tìm thấy PR.')
                    registered={}
                    def register_page(photo):
                        identity=hashlib.sha256(f'library:{photo}:{content_identity(photo)}'.encode()).hexdigest()[:24]
                        registered[identity]=photo
                        return '/api/image/'+identity
                    photos=library_photos(library,key,record)
                    pages=[]
                    for photo in photos:
                        if not photo.resolve().is_relative_to(library.resolve()):
                            raise ValueError('Ảnh nằm ngoài thư viện PR.')
                        pages.append(register_page(photo))
                    result=dict(label=title(record),pages=pages)
                    if query.get('deliveries')==['1']:
                        from receipt_actions import local_ledger_source
                        from receiving_ledger import resolve_order, summary
                        from receiving_service import digest
                        from fractions import Fraction
                        ledger=workspace.ledger_path(STORE)
                        _,history=summary(ledger,order_id=resolve_order(ledger,key))
                        resolve=local_ledger_source(STORE,photos)
                        deliveries=[]
                        for entry in sorted(history,key=lambda row:(row['day'],row['sheet']),reverse=True):
                            if not entry['active'] or not any(Fraction(q)>0 for q in entry['allocations'].values()):
                                continue
                            if (entry['day'],entry['sheet'])==(query.get('day',[''])[0],query.get('sheet',[''])[0]):
                                continue
                            sources=resolve(entry)['source_images']
                            delivery_pages=[]
                            for filename,expected in sorted(sources.items()):
                                photo=Path(filename).resolve()
                                if photo.is_relative_to(STORE.resolve()) and photo.is_file() and digest(photo)==expected:
                                    delivery_pages.append(register_page(photo))
                            deliveries.append(dict(id=entry['receipt_id'],day=entry['day'],sheet=entry['sheet'],pages=delivery_pages))
                        result['deliveries']=deliveries
                    with lock:
                        allowed_images.update(registered)
                    return result
                handlers={
                    'overview':lambda:workspace.overview(STORE,available_days(),query.get('day',[''])[0]),
                    'library':lambda:workspace.library_view(STORE),
                    'ledger':lambda:workspace.ledger_view(STORE),
                    'directory':lambda:workspace.directory(PROFILE),
                    'settings':lambda:workspace.settings(PROFILE),
                    'prices':lambda:workspace.prices(PROFILE,STORE,query.get('month',[''])[0]),
                    'sheets':lambda:workspace.sheets(PROFILE,STORE),
                    'sync-history':lambda:workspace.sync_history(STORE),
                    'pr-images':pr_pages,
                }
                handler=handlers.get(path.rsplit('/',1)[-1])
                if handler is None:
                    self.send_error(404);return
                try:
                    result=handler()
                    self.reply(json.dumps(result,ensure_ascii=False,default=encode).encode(),'application/json; charset=utf-8','no-store')
                except (OSError,ValueError) as exc:
                    self.reply(json.dumps({'error':ocr_jobs._redact(str(exc))},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',400)
                return
            if path=='/api/debt/suppliers':
                from rec_supplier_reconciliation import reconciliation
                month = parse_qs(urlsplit(self.path).query).get('month', [''])[0]
                try:
                    result = reconciliation(PROFILE, STORE, available_days(), month)
                except ValueError as exc:
                    self.reply(json.dumps({'error':str(exc)},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',400);return
                self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
            if path in ('/api/catalog/search','/api/receipt/pr','/api/pr/library'):
                from receipt_actions import catalog_search, pr_result, list_pr
                query=parse_qs(urlsplit(self.path).query)
                try:
                    if path=='/api/catalog/search':
                        result={'items':catalog_search(PROFILE,query.get('q',[''])[0])}
                    elif path=='/api/pr/library':
                        q=query.get('q',[''])[0]
                        rows=None
                        aliases=()
                        if not q.strip() and 'sheet' in query:
                            from receipt_actions import get_rows
                            report=available_days().get(query.get('day',[''])[0])
                            if report is None:
                                raise ValueError('Ngày không có báo cáo REC.')
                            sheet=query['sheet'][0]
                            rows=get_rows(report,sheet,query.get('version',[''])[0])[sheet]
                            suppliers={str(row.get('Nhà cung cấp') or '') for _,row in rows}-{''}
                            aliases=[nickname(PROFILE,supplier) for supplier in suppliers]
                        result={'items':list_pr(STORE,q,rows=rows,supplier_aliases=aliases)}
                    else:
                        report=available_days().get(query.get('day',[''])[0])
                        if report is None:
                            raise ValueError('Ngày không có báo cáo REC.')
                        day_key=query.get('day',[''])[0];sheet_key=query.get('sheet',[''])[0];version_key=query.get('version',[''])[0]
                        from rec_workspaces import ledger_path
                        ledger_file=ledger_path(STORE)
                        ledger_version=[]
                        for file in (ledger_file,ledger_file.with_name(ledger_file.name+'-wal')):
                            try:ledger_version.append(str(file.stat().st_mtime_ns))
                            except FileNotFoundError:ledger_version.append('0')
                        pr_key=(day_key,sheet_key,version_key,'delivery-v5',*ledger_version)
                        with lock:saved_pr=pr_result_cache.get(pr_key)
                        if saved_pr is None:
                            disk_entry=_load_pr_disk_cache().get('|'.join(pr_key))
                            if isinstance(disk_entry,dict) and isinstance(disk_entry.get('result'),dict) and (
                                disk_entry['result'].get('status')!='ready' or 'deliveryItems' in disk_entry['result']
                            ):
                                stored_photos=tuple(Path(p) for p in disk_entry.get('photos',[]) if Path(p).is_file())
                                saved_pr=(disk_entry['result'],stored_photos)
                                with lock:pr_result_cache[pr_key]=saved_pr
                        if saved_pr is None:
                            photos=[]
                            result=pr_result(STORE,report,sheet_key,version_key,photos=photos)
                            with lock:
                                if len(pr_result_cache)>=64:pr_result_cache.pop(next(iter(pr_result_cache)))
                                pr_result_cache[pr_key]=(copy.deepcopy(result),tuple(photos))
                                _store_pr_disk_cache(pr_key,result,photos)
                        else:
                            result,stored_photos=saved_pr
                            result=copy.deepcopy(result);photos=list(stored_photos)
                        registered={}
                        pages=[]
                        for photo in photos:
                            photo=photo.resolve()
                            if not photo.is_relative_to(STORE.resolve()):
                                raise ValueError('Ảnh PR nằm ngoài kho dữ liệu REC.')
                            stat=photo.stat()
                            key=hashlib.sha256(f'pr:{photo}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()[:24]
                            registered[key]=photo
                            pages.append('/api/image/'+key)
                        with lock:
                            allowed_images.update(registered)
                        result['prPages']=pages
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    self.reply(json.dumps({'error':ocr_jobs._redact(str(exc))},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',400);return
                self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
            if path=='/api/receipts':
                query=parse_qs(urlsplit(self.path).query)
                self.reply(json.dumps(load(query.get('day',[None])[0],query.get('refresh',['0'])[0]=='1'),ensure_ascii=False,default=encode).encode(),'application/json; charset=utf-8','no-store');return
            if path=='/api/receipt/locations':
                query=parse_qs(urlsplit(self.path).query)
                day=query.get('day',[None])[0];sheet=query.get('sheet',[None])[0]
                data=load(day)
                if query.get('version',[None])[0]!=data.get('version'):
                    self.reply(json.dumps({'error':'Phiếu đã thay đổi. Tải lại dữ liệu trước khi định vị.'},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',409);return
                doc=next((d for d in data['receipts'] if d['file']==sheet),None)
                if doc is None:self.send_error(404);return
                if query.get('images',[None])[0]!=doc.get('imageVersion'):
                    self.reply(json.dumps({'error':'Ảnh đã thay đổi. Tải lại phiếu trước khi định vị.'},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',409);return
                paths=[allowed_images[url.rsplit('/',1)[-1]] for url in doc['pages']]
                from row_locations import locate
                result=locate(paths,doc['rows'],allowed_images)
                result.update(version=data['version'],sheet=sheet)
                self.reply(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store');return
            if path.startswith('/api/pr/thumbnail/'):
                from io import BytesIO
                from PIL import Image, ImageOps
                from receipt_actions import pr_library
                from receiving_pr_library import load as load_pr_library
                from receiving_service import digest
                library=pr_library(STORE)
                key=path.removeprefix('/api/pr/thumbnail/')
                record=load_pr_library(library).get(key) if re.fullmatch(r'[a-f0-9]{64}', key) else None
                first=next(iter(record.get('images', {}).items()), None) if record else None
                if first is None:self.send_error(404);return
                name, expected=first
                photo=(library/key/Path(name).name).resolve()
                try:
                    if not photo.is_relative_to(library.resolve()) or digest(photo)!=expected:
                        self.send_error(404);return
                    with Image.open(photo) as source:
                        source.draft('RGB', (240, 300))
                        thumbnail=ImageOps.exif_transpose(source)
                        thumbnail.thumbnail((240, 300), Image.Resampling.LANCZOS)
                        output=BytesIO()
                        thumbnail.convert('RGB').save(output, 'JPEG', quality=83)
                except (OSError, ValueError, Image.DecompressionBombError):
                    self.send_error(404);return
                self.reply(output.getvalue(),'image/jpeg','private, max-age=60');return
            if path.startswith('/api/preview/'):
                image=allowed_images.get(path.removeprefix('/api/preview/'))
                if image is None:self.send_error(404);return
                preview=resolve_preview(image)
                self.reply(preview.read_bytes(),mimetypes.guess_type(preview.name)[0] or 'application/octet-stream','private, max-age=60');return
            if path.startswith('/api/image/'):
                image=allowed_images.get(path.removeprefix('/api/image/'))
                if image is None:self.send_error(404);return
                self.reply(image.read_bytes(),mimetypes.guess_type(image.name)[0] or 'application/octet-stream','private, max-age=60');return
            dist=Path(__file__).parent/'dist';target=(dist/unquote(path).lstrip('/')).resolve()
            if not target.is_relative_to(dist.resolve()):self.send_error(403);return
            if path=='/':target=dist/'index.html'
            if target.is_file():self.reply(target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream','no-cache');return
            self.send_error(404)
        except Exception:
            logging.exception('REC GET failed: %s',urlsplit(self.path).path)
            self.reply(json.dumps({'error':'Không đọc được dữ liệu REC. Kiểm tra báo cáo ngày đã chọn rồi thử tải lại.'},ensure_ascii=False).encode(),'application/json; charset=utf-8','no-store',500)
    def reply(self,data,kind,cache,code=200):
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control',cache);self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

if __name__=='__main__':
    print('REC local bridge + OCR: http://127.0.0.1:8771',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8771),Handler).serve_forever()
