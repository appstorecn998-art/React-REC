"""Isolated local OCR playground; never invokes the report-writing worker."""
import hashlib,json,secrets,threading,time,traceback,re,io
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image,ImageOps
from statistics import median
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from benchmark_ocr import OUT,ROOT,server,aw
from local_runtime import STORE
from ocr_quality import prepare,audit
from ocr_details import install as install_details
plain_request=aw.request_batch_document
install_details(aw)

TOKEN=secrets.token_urlsafe(32)
guard=threading.Lock()
job={'status':'idle'}
state_lock=threading.RLock()
library={hashlib.sha256(str(p).encode()).hexdigest()[:24]:p for p in sorted((STORE/'AnhPhieu').rglob('*')) if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.heic','.heif'}}

def estimate(name):
    samples=[];same=[]
    for file in sorted((OUT/'new-tests').glob('*/result.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
        try:data=json.loads(file.read_text(encoding='utf-8'));seconds=float(data['seconds'])
        except (OSError,ValueError,KeyError,TypeError):continue
        if seconds<=0:continue
        samples.append(seconds)
        if data.get('name')==name:same.append(seconds)
    values=same or samples
    return {'seconds':round(median(values),1) if values else None,'samples':len(values)}

def timing(current,now=None):
    now=time.time() if now is None else now
    if current.get('status')=='done':elapsed=current.get('newResult',{}).get('seconds')
    elif current.get('status')=='error':elapsed=(current.get('events') or [{}])[-1].get('seconds',0)
    else:elapsed=None
    if elapsed is None:elapsed=max(0,now-current.get('startedAt',now))
    prediction=current.get('estimate',{})
    total=prediction.get('seconds')
    return {'elapsed':round(elapsed,1),'estimatedTotal':total,'estimateSamples':prediction.get('samples',0),'remaining':round(max(0,total-elapsed),1) if total is not None and current.get('status')=='running' else None}

def clean(value):
    if isinstance(value,dict):return {k:('[HIDDEN]' if any(x in k.lower() for x in ('api_key','authorization','credential','password')) else clean(v)) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if not isinstance(value,str):return value
    for secret in server.ocr_jobs._secrets():value=value.replace(secret,'[KEY]')
    return re.sub(r'(?i)(Bearer\s+)[^\s"\']+',r'\1[HIDDEN]',re.sub(r'AIza[\w-]+|sk-[\w-]+','[KEY]',value))

def progress(stage,message,details=None,level='info',**values):
    with state_lock:
        job.update(stage=stage,message=message,**values)
        if values.get('status') in {'done','error'}:job['finishedAt']=time.time()
        job.setdefault('events',[]).append(clean({'seconds':round(time.time()-job.get('startedAt',time.time()),3),'time':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='milliseconds'),'stage':stage,'level':level,'message':message,'details':details or {}}))
        if job.get('kind')=='new' and job.get('id'):
            aw.atomic_cache_json(OUT/'new-tests'/job['id']/'status.json',dict(job))

def error_details(exc):
    response=getattr(exc,'response',None)
    return clean({'exception':type(exc).__name__,'message':str(exc),'http_status':getattr(exc,'status_code',None) or getattr(exc,'code',None) or getattr(response,'status_code',None),'traceback':''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))})

def run_new(key):
    source=library[key]
    from ocr_events import listener
    token=listener.set(lambda stage,message,details:progress(stage,message,details=details))
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(10):
            with state_lock:stage=job.get('stage')
            if stage in {'api_send','waiting','heartbeat'}:progress('heartbeat','Kết nối đang chờ Gemini trả phản hồi; chưa nhận dữ liệu kết quả.',details={'api_timeout_seconds':120,'attempt':job.get('attempt',1)})
    reporter=threading.Thread(target=heartbeat,daemon=True);reporter.start()
    try:
        from preview_cache import saved_rotation
        with Image.open(source) as image:
            dimensions=image.size;image_format=image.format;orientation=image.getexif().get(274,1)
        progress('prepare','Đang đọc ảnh nguồn và kiểm tra thông tin ảnh.',details={'file':str(source.relative_to(STORE)),'bytes':source.stat().st_size,'format':image_format,'width':dimensions[0],'height':dimensions[1],'exif_orientation':orientation,'reviewed_rotation':saved_rotation(source),'mode':'original-first + 3 details','source':'Kho bản web riêng'})
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        data=prepare(source)
        with Image.open(io.BytesIO(data)) as image:prepared_size=image.size
        progress('image_ready','Đã chuẩn bị ảnh gốc màu cho OCR; không nắn phối cảnh.',details={'width':prepared_size[0],'height':prepared_size[1],'jpeg_bytes':len(data),'limit_pixels':3200,'jpeg_quality':94,'source_sha256':before})
        folder=OUT/'new-tests'/job['id'];folder.mkdir(parents=True,exist_ok=True)
        (folder/'original.jpg').write_bytes(data)
        progress('configure','Đang tải nhóm danh mục từ cấu hình riêng.')
        catalog,groups=aw.load_catalog_data(server.ocr_jobs.profile/'DanhMuc.xlsm')
        api_key=server.ocr_jobs._secrets()[0]
        progress('config_ready','Đã tải cấu hình OCR riêng; khóa API đã có và được che.',details={'catalog_items':len(catalog),'product_groups':len(set(groups.values())),'model':aw.MODEL,'timeout_seconds':120,'max_attempts':3,'cache':'Đọc mới; không lấy kết quả thử cũ','scope':'Trích chứng từ; chưa đối chiếu SKU, chưa xuất báo cáo kế toán'})
        from ocr_retry import transient,retry_delay
        for attempt in range(1,4):
            progress('waiting',f'Đang chờ Gemini: ảnh gốc + 3 vùng chi tiết, lượt {attempt}/3. API chưa cung cấp tiến độ từng dòng.',attempt=attempt)
            try:
                document=aw.request_batch_document(api_key,aw.MODEL,data,groups,120)
                break
            except Exception as exc:
                progress('api_error','Lượt gọi Gemini thất bại.',details=error_details(exc),level='error')
                if attempt==3 or not transient(exc):raise
                delay=retry_delay(exc,attempt)
                progress('retry',f'Lỗi tạm thời {type(exc).__name__}; chờ {delay:.0f} giây rồi thử lại.',details={'delay_seconds':delay,'next_attempt':attempt+1,'max_attempts':3},level='warning')
                time.sleep(delay)
        progress('validate',f'Đã nhận {len(document["items"])} dòng; đang kiểm cấu trúc và cảnh báo.')
        aw.validate_batch_document(document)
        if hashlib.sha256(source.read_bytes()).hexdigest()!=before:raise ValueError('source changed')
        warnings=audit(document)
        progress('document','Đã kiểm cấu trúc chứng từ.',details={'type':document.get('document_type'),'supplier':document.get('supplier_name'),'reference':document.get('reference_id'),'delivery_date':document.get('delivery_date'),'rows':len(document['items'])})
        for index,item in enumerate(document['items'],1):
            progress('row',f'Dòng {index}: {item.get("item_name","")}',details={k:item.get(k) for k in ('source_stt','catalog_code','quantity','received_quantity','receipt_mark','receipt_needs_review','receipt_note','unit','unit_price','line_amount')})
        for warning in warnings:progress('audit',warning,level='warning')
        progress('integrity','Đã kiểm SHA256: ảnh nguồn giữ nguyên.',details={'sha256':before})
        elapsed=round(time.time()-job['startedAt'],2)
        payload={'name':source.name,'document':document,'seconds':elapsed,'warnings':warnings,'sourceUnchanged':True,'model':aw.MODEL}
        progress('saving','Đang lưu kết quả JSON riêng bằng thao tác ghi nguyên tử.',details={'file':str((folder/'result.json').relative_to(OUT)),'writes_accounting_report':False})
        aw.atomic_cache_json(folder/'result.json',payload)
        progress('done',f'Đã đọc xong {len(document["items"])} dòng trong {elapsed} giây. Kết quả test được lưu riêng.',status='done',newResult=payload)
        aw.atomic_cache_json(folder/'status.json',dict(job))
    except Exception as exc:
        progress('error','Chưa đọc xong: '+type(exc).__name__+'. Nhật ký lỗi được giữ để kiểm tra.',details=error_details(exc),level='error',status='error',error=clean(str(exc)))
    finally:
        stop.set();listener.reset(token);guard.release()
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
names={Path(row['source']).name for row in manifest['pairs']}

def result(name,mode):
    target=OUT/(name+'.'+mode+'.json')
    return json.loads(target.read_text(encoding='utf-8')) if target.exists() else None

def run_pair(name):
    try:
        _,groups=aw.load_catalog_data(server.ocr_jobs.profile/'DanhMuc.xlsm')
        key=server.ocr_jobs._secrets()[0]
        results={}
        for mode in ('original','processed'):
            started=time.monotonic()
            data=(OUT/(name+'.'+mode+'.jpg')).read_bytes()
            progress('waiting','Đang đọc bản '+mode+' bằng Gemini.')
            results[mode]={'document':plain_request(key,aw.MODEL,data,groups,120),'seconds':round(time.monotonic()-started,2)}
        # Retain original benchmark runs; UI retries are separate, complete pairs.
        target=OUT/'retries';target.mkdir(exist_ok=True)
        (target/(str(time.time_ns())+'.json')).write_text(json.dumps({'name':name,'results':results},ensure_ascii=False),encoding='utf-8')
        job.update(status='done',results=results)
    except Exception as exc:job.update(status='error',error='Không đọc xong cặp ảnh: '+type(exc).__name__+'. Kết quả trước vẫn giữ nguyên.')
    finally:guard.release()

class Handler(BaseHTTPRequestHandler):
    def trusted(self):
        if self.headers.get('Host') not in ('127.0.0.1:8769','localhost:8769'):return False
        if self.headers.get('Origin') not in (None,'http://127.0.0.1:8769','http://localhost:8769'):return False
        return self.headers.get('Sec-Fetch-Site')!='cross-site'
    def send(self,data,kind='application/json; charset=utf-8',code=200):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if not self.trusted():self.send_error(403);return
        url=urlsplit(self.path)
        if url.path=='/':self.send((ROOT/'ocr-test.html').read_bytes(),'text/html; charset=utf-8');return
        if url.path=='/api/state':
            pairs=[{'name':Path(row['source']).name,'method':row['method'],'rotation':row['rotation'],'original':result(Path(row['source']).name,'original'),'processed':result(Path(row['source']).name,'processed')} for row in manifest['pairs']]
            findings=OUT/'findings.json'
            with state_lock:public_job=dict(job,events=list(job.get('events',[])),**timing(job))
            self.send({'pairs':pairs,'model':manifest['model'],'token':TOKEN,'job':public_job,'library':[{'id':key,'name':p.name,'folder':str(p.parent.relative_to(STORE))} for key,p in library.items()],'findings':json.loads(findings.read_text(encoding='utf-8')) if findings.exists() else {}});return
        if url.path=='/new-image':
            key=parse_qs(url.query).get('id',[''])[0]
            if key not in library:self.send_error(404);return
            self.send(prepare(library[key]),'image/jpeg');return
        if url.path=='/image':
            query=parse_qs(url.query);name=query.get('name',[''])[0];mode=query.get('mode',[''])[0]
            if name not in names or mode not in ('original','processed'):self.send_error(404);return
            self.send((OUT/(name+'.'+mode+'.jpg')).read_bytes(),'image/jpeg');return
        self.send_error(404)
    def do_POST(self):
        if not self.trusted() or not secrets.compare_digest(self.headers.get('X-REC-Token',''),TOKEN):self.send_error(403);return
        route=urlsplit(self.path).path
        if route not in ('/api/run','/api/new-run'):self.send_error(404);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<1024 or self.headers.get_content_type()!='application/json':raise ValueError()
            self.connection.settimeout(10)
            payload=json.loads(self.rfile.read(size));name=payload.get('name') if route=='/api/run' else payload.get('id')
            if name not in (names if route=='/api/run' else library):raise ValueError()
        except (ValueError,TypeError,AttributeError):self.send({'error':'Ảnh không hợp lệ.'},code=400);return
        if not guard.acquire(blocking=False):self.send({'error':'Đang đọc một cặp ảnh; chờ hoàn tất.'},code=409);return
        with state_lock:
            job.clear();job.update(status='running',name=name,id=secrets.token_hex(8),startedAt=time.time(),events=[],kind='new' if route=='/api/new-run' else 'pair',estimate=estimate(library[name].name) if route=='/api/new-run' else {})
        progress('queued','Đã nhận yêu cầu; chuẩn bị xử lý.')
        threading.Thread(target=run_pair if route=='/api/run' else run_new,args=(name,),daemon=False).start()
        self.send({'started':True},code=202)
    def log_message(self,*args):pass

if __name__=='__main__':
    previous=sorted((OUT/'new-tests').glob('*/status.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if previous:
        try:
            saved=json.loads(previous[0].read_text(encoding='utf-8'))
            if saved.get('name') in library:
                job.update(saved)
                if job.get('status')=='running':progress('error','Server đã dừng giữa lượt đọc. Nhật ký trước đó được giữ; chưa tự gửi lại ảnh.',level='error',status='error',error='Lượt đọc bị gián đoạn khi server dừng.')
        except (OSError,ValueError,TypeError):pass
    print('OCR test: http://127.0.0.1:8769/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8769),Handler).serve_forever()
