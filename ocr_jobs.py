"""One local OCR queue; selected uploads only. Reuse REC import, worker and save guards."""
import base64,hashlib,io,json,os,re,subprocess,sys,threading,time,uuid
from pathlib import Path
from datetime import date,datetime
from zoneinfo import ZoneInfo
from PIL import Image

from local_runtime import APP,PROFILE,activate
activate()
MAX_FILE=20*1024*1024;MAX_BATCH=80*1024*1024
EXT={'.jpg','.jpeg','.png','.webp','.heic','.heif'}

class Jobs:
    def __init__(self,store,job_root=None,profile=PROFILE):
        self.store=Path(store);self.root=Path(job_root or Path(__file__).parent/'.ocr-jobs');self.profile=Path(profile)
        self.guard=threading.RLock();self.current=None;self.uploads={}
        for path in sorted(self.root.glob('*/status.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job['id'] != path.parent.name or job['status'] not in {'importing', 'running', 'error', 'complete'}:
                    continue
            except (OSError, ValueError, KeyError, TypeError):
                continue
            self.current = job
            if job.get('preview', {}).get('status') == 'running':
                job['preview'] = {**job['preview'], 'status': 'interrupted', 'file': ''}
                self._persist(job)
            if job['status'] in {'importing', 'running'}:
                message = 'Lượt đọc bị gián đoạn khi máy chủ đóng. Chọn lại nhóm ảnh để tiếp tục từ phần chưa lưu.'
                self._update(status='error', message=message, finishedAt=time.time())
                self._event('error', message)
            break
    def public(self):
        with self.guard:
            key_available=bool(self._secrets())
            job=dict(self.current) if self.current else None
            if job:
                job['elapsed']=round(max(0,(job.get('finishedAt') or time.time())-job.get('startedAt',time.time())),1)
                estimate=job.get('estimatedSeconds')
                job['remaining']=max(0,round(estimate-job['elapsed'])) if estimate and job['status'] in ('importing','running') else None
            return {'job':job,'ready':key_available and all((self.profile/n).is_file() for n in ('DanhMuc.xlsm','NhaCungCap.json')),'today':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()}
    def _estimate(self,count,enhanced):
        from statistics import median
        samples=[]
        for file in sorted(self.root.glob('*/status.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            try:
                old=json.loads(file.read_text(encoding='utf-8'))
                if old.get('status')=='complete' and old.get('enhanced')==enhanced and old.get('count',0)>0:
                    samples.append((old['finishedAt']-old['startedAt'])/old['count'])
            except (OSError,ValueError,TypeError,KeyError):continue
        return (round(median(samples)*count),len(samples)) if samples else (None,0)
    def _event(self,stage,message,**details):
        with self.guard:
            if not self.current:return
            self.current.setdefault('events',[]).append({'stage':stage,'message':self._redact(message),'seconds':round(time.time()-self.current.get('startedAt',time.time()),1),**details})
            self.current['events']=self.current['events'][-2000:]
        self._persist()
    def _check_idle(self):
        if self.current and self.current['status'] in ('importing','running'):raise ValueError('Đang có tác vụ OCR. Chờ tác vụ hiện tại kết thúc.')
    def stage(self,payload):
        day=date.fromisoformat(payload.get('day',''));files=payload.get('files')
        if not isinstance(files,list) or not 1<=len(files)<=200:raise ValueError('Chọn từ 1 đến 200 ảnh.')
        with self.guard:
            self._check_idle();token=uuid.uuid4().hex;folder=self.root/token/'sources';folder.mkdir(parents=True)
            decoded=[];total=0;names=set()
            try:
                for f in files:
                    name=f.get('name','')
                    if not isinstance(name,str) or Path(name).name!=name or any(c in name for c in '<>:"/\\|?*') or len(name)>180 or name.rstrip('. ')!=name or name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:raise ValueError('Tên ảnh không hợp lệ.')
                    if Path(name).suffix.lower() not in EXT or name.casefold() in names:raise ValueError('Ảnh không hỗ trợ hoặc trùng tên trong nhóm.')
                    names.add(name.casefold());content=base64.b64decode(f.get('content',''),validate=True)
                    total+=len(content)
                    if not content or len(content)>MAX_FILE or total>MAX_BATCH:raise ValueError('Ảnh tối đa 20 MB; cả nhóm tối đa 80 MB.')
                    if Path(name).suffix.lower() in {'.heic','.heif'}:
                        from pillow_heif import register_heif_opener
                        register_heif_opener()
                    with Image.open(io.BytesIO(content)) as im:
                        if im.width*im.height>80_000_000:raise ValueError('Ảnh quá lớn (trên 80 triệu điểm ảnh).')
                        im.verify()
                    target=folder/name;target.write_bytes(content);decoded.append(target)
                self.uploads[token]={'day':day.isoformat(),'paths':decoded,'folder':folder.parent}
                return {'uploadId':token,'day':day.isoformat(),'count':len(decoded),'bytes':total}
            except Exception:
                # Leave no partial accepted batch. Only remove this job's own staged files.
                for file in folder.iterdir():file.unlink()
                folder.rmdir();folder.parent.rmdir();raise
    def start(self,payload):
        token=payload.get('uploadId');enhanced=payload.get('enhanced',True)
        if type(enhanced) is not bool:raise ValueError('Tùy chọn chất lượng không hợp lệ.')
        with self.guard:
            self._check_idle()
            upload=self.uploads.get(token)
            if not upload:raise ValueError('Không còn nhóm ảnh đã chọn. Chọn lại ảnh.')
            if not self.public()['ready']:raise ValueError('REC chưa đủ cấu hình Gemini/danh mục. Mở Cài đặt REC cũ để kiểm tra.')
            job_id=uuid.uuid4().hex
            self.current={'id':job_id,'day':upload['day'],'count':len(upload['paths']),'status':'importing','message':'Đang đưa ảnh vào kho REC…','logs':[],'enhanced':enhanced,'warnings':[],'receipts':0,'rows':0,'startedAt':time.time()}
            prediction,samples=self._estimate(len(upload['paths']),enhanced)
            self.current.update(events=[],stage='import',imagesRead=0,imagesFailed=0,savedCount=0,estimatedSeconds=prediction,estimateSamples=samples)
            self._event('import','Đã nhận nhóm ảnh; đang lưu vào kho riêng.')
            # A normal server shutdown must let the active save/worker finish.
            threading.Thread(target=self._run,args=(dict(upload),job_id,enhanced),daemon=False).start()
            return dict(self.current)
    def _update(self,**kwargs):
        with self.guard:self.current.update(kwargs)
    def _secrets(self):
        secrets=[os.environ.get('GEMINI_API_KEY','').strip()]
        try:secrets.append((self.profile/'gemini_api_key.txt').read_text(encoding='utf-8-sig').strip())
        except OSError:pass
        return [s for s in secrets if s]
    def _redact(self,text):
        for key in self._secrets():text=text.replace(key,'[KEY]')
        return re.sub(r'AIza[\w-]+|sk-[\w-]+','[KEY]',text)[-1500:]
    def _log(self,text):
        if text.startswith('REC_OCR_EVENT '):
            try:
                data=json.loads(text[len('REC_OCR_EVENT '):]);stage=data['stage'];details=data.get('details') or {}
                name=str(details.get('file') or '')
                if stage=='image_start':
                    self._update(stage='read',currentImage=name)
                    self._event('read',f'Đang đọc ảnh {name}.')
                elif stage=='image_done':
                    with self.guard:self.current['imagesRead']=self.current.get('imagesRead',0)+1
                    self._event('image_done',f'Đã đọc {name}: {details.get("rows",0)} dòng.',file=name,rows=details.get('rows',0))
                elif stage=='orders_saved':
                    count=details['count']
                    self._update(ordersRead=count)
                    self._event('orders_saved',f'Đã lưu hoặc nhận diện {count} chứng từ PR/PO trong thư viện.')
                elif stage=='po_catalog_warning':
                    with self.guard:
                        self.current.setdefault('poWarnings',[]).append(self._redact(data['message']))
                    self._persist()
                elif stage=='image_error':
                    from ocr_messages import reading_error
                    with self.guard:self.current['imagesFailed']=self.current.get('imagesFailed',0)+1
                    reason=reading_error(name,details.get('exception',''),self._redact(str(details.get('error_message',''))),details.get('http_status'))
                    self._update(lastReadingError=reason)
                    self._event('warning',reason,file=name)
                elif stage in {'needs_pages', 'suspected_duplicate', 'retry_held', 'invoice_error'}:
                    files = str(details.get('files') or '')
                    message = self._redact(str(data.get('message') or ''))
                    if stage == 'invoice_error':
                        from ocr_messages import invoice_error
                        message = invoice_error(details.get('exception', ''), message, details.get('http_status'))
                    if files:
                        message = f'{files} — {message}'
                    existing = self._redact(str(details.get('existing') or ''))
                    if existing:
                        message += f' Phiếu đã lưu: {existing}.'
                    self._update(lastInvoiceIssue=message)
                    self._event(stage,message,files=files)
                elif stage=='api_send':self._event('detail','Đã gửi ảnh; đang chờ Gemini trả nội dung.')
                return
            except (ValueError,KeyError,TypeError):pass
        text=self._redact(text.strip())
        if not text:return
        with self.guard:
            self.current['logs']=(self.current['logs']+[text])[-70:]
            self.current['message']=text
        if 'Đang đối chiếu một phiếu gồm' in text:
            self._update(stage='match');self._event('match','Đang ghép trang và đối chiếu mặt hàng với danh mục.')
        elif 'ĐÃ LƯU ' in text:
            with self.guard:self.current['savedCount']=self.current.get('savedCount',0)+1
            self._update(stage='save');self._event('saved','Đã lưu một phiếu vào báo cáo riêng.')
        elif 'Bỏ qua ảnh đã lưu:' in text:
            self._event('skipped','Giữ nguyên ảnh/phiếu đã lưu; không đọc lại.',detail=text)
        elif 'thử lại' in text.lower():self._event('warning','Dịch vụ chưa trả kết quả. Đang chờ để thử lại; các phần đã đọc vẫn được giữ.')
    def _build_previews(self, job, paths):
        from preview_cache import build

        progress = dict(status='running', total=len(paths), processed=0,
                        cropped=0, straightened=0, original=0, failed=0, file='')
        def publish():
            with self.guard:
                job['preview'] = dict(progress)
                self._persist(job)

        try:
            for path in paths:
                progress['file'] = path.name
                publish()
                try:
                    method = build(path)['method']
                except Exception:
                    progress['failed'] += 1
                else:
                    if method.startswith('paper-crop'):
                        progress['cropped'] += 1
                    elif method == 'original':
                        progress['original'] += 1
                    else:
                        progress['straightened'] += 1
                progress['processed'] += 1
        finally:
            status = 'complete' if progress['processed'] == progress['total'] else 'interrupted'
            progress.update(status=status, file='')
            publish()

    def _run(self,upload,job_id,enhanced):
        try:
            from receiving_service import import_images,paths,day_images,digest,snapshot
            from receiving_image_archive import source_digest
            day=date.fromisoformat(upload['day'])
            def imported(name, failure):
                if failure is None:
                    self._event('import_image_done',f'Đã đưa ảnh {name} vào kho.',file=name)
                    return
                reason = ('Windows đang chặn ghi hoặc tệp đang được mở.'
                          if isinstance(failure, PermissionError)
                          else 'Không tạo được bản lưu của ảnh. Kiểm tra tệp ảnh rồi thử lại.')
                message = f'Ảnh {name}: {reason}'
                self._update(lastImportError=message)
                self._event('import_image_error',message,file=name)

            import_images(self.profile,day,upload['paths'],self.store,
                          progress=lambda s:self._update(message=s),image_result=imported)
            self._event('import_done','Đã đưa ảnh vào kho riêng.')
            _,report=paths(self.profile,day,self.store)
            self._update(stage='prepare')
            self._event('prepare','Đang xác minh nhóm ảnh sẽ đọc.')
            # Include previously imported copies on retries; never read unrelated historical images.
            hashes={hashlib.sha256(p.read_bytes()).hexdigest() for p in upload['paths']}
            selected=[p for p in day_images(report.parent) if source_digest(p) in hashes]
            if len(selected)!=len(hashes):raise ValueError('Không xác minh được đầy đủ ảnh vừa nhập. Chưa chạy Gemini.')
            before={name for name,rows in snapshot(report)[1] if rows}
            self._event('prepare_done','Đã chuẩn bị xong nhóm ảnh.')
            folder=self.root/job_id;folder.mkdir(parents=True,exist_ok=True);quality=folder/'quality.json'
            env=os.environ.copy();env['REC_DATA_DIR']=str(self.profile);env.pop('REC_DEBT_MODE',None)
            env['REC_SELECTED_IMAGE_HASHES']=json.dumps([digest(p) for p in selected])
            args=[sys.executable,'-B','-X','utf8','-u',str(Path(__file__).with_name('ocr_child.py')),'--day',day.isoformat(),'--store',str(self.store),'--profile',str(self.profile),'--quality-report',str(quality)]
            if enhanced:args.append('--enhanced')
            self._update(status='running',message=f'Gemini đang đọc {len(selected)} ảnh đã chọn…')
            self._update(stage='read');self._event('read','Bắt đầu đọc các ảnh chưa lưu; kết quả từng ảnh được giữ để tiếp tục nếu gián đoạn.')
            proc=subprocess.Popen(args,cwd=str(APP),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with self.guard:
                job = self.current
                job['preview'] = dict(status='running', total=len(selected), processed=0,
                                      cropped=0, straightened=0, original=0, failed=0, file='')
                self._persist(job)
            threading.Thread(target=self._build_previews, args=(job, selected), daemon=False).start()
            # Whole-job watchdog: each OCR call already has its original finite timeout.
            watchdog=threading.Timer(min(86400,max(1800,len(selected)*600)),proc.kill);watchdog.daemon=True;watchdog.start()
            try:
                for line in proc.stdout:self._log(line)
                code=proc.wait()
            finally:watchdog.cancel()
            warnings=json.loads(quality.read_text(encoding='utf-8')) if quality.exists() else []
            self._update(warnings=warnings)
            if code:
                self._update(hasReport=report.is_file())
                raise ValueError('Nhóm chưa hoàn tất. Các phiếu đã lưu và cache được giữ. Xem ảnh lỗi trong chi tiết; đọc lại cùng nhóm chỉ tiếp tục phần chưa lưu.')
            _,data=snapshot(report);actual=[(name,rows) for name,rows in data if rows]
            new=[(n,rs) for n,rs in actual if n not in before]
            orders=self.current.get('ordersRead',0)
            message=f'Hoàn tất · {len(new)} phiếu giao mới · {orders} chứng từ PR/PO trong thư viện.'
            self._update(status='complete',message=message,receipts=len(actual),rows=sum(len(rs) for _,rs in actual),newReceipts=len(new),hasReport=report.is_file() and bool(actual),warnings=warnings,finishedAt=time.time())
            self._event('complete',message)
            self._persist()
        except Exception as exc:
            technical=self._redact(str(exc));self._log(technical)
            if self.current.get('lastImportError'):
                message=self.current['lastImportError']
            elif isinstance(exc,PermissionError):
                message='Không lưu được ảnh vào kho riêng: Windows đang chặn ghi hoặc tệp đang bị chương trình khác giữ. Ảnh chưa được gửi để đọc. Đóng chương trình đang mở thư mục/tệp rồi thử lại.' if self.current.get('stage') in ('import','prepare') else 'Không lưu được kết quả vào báo cáo riêng. Đóng báo cáo trong Excel/WPS rồi thử lại; các phần đã lưu vẫn được giữ.'
            elif self.current.get('stage')=='import':
                message='Chưa đưa được ảnh vào kho riêng. '+technical
            else:message=self.current.get('lastInvoiceIssue') or self.current.get('lastReadingError') or 'Nhóm ảnh chưa xử lý xong. Các phiếu đã lưu vẫn được giữ; hãy xem phần cần kiểm tra rồi thử lại phần chưa hoàn tất.'
            self._update(status='error',message=message,finishedAt=time.time());self._event('error',message);self._persist()
    def _persist(self, job=None):
        with self.guard:
            try:
                from receiving_service import atomic_json
                job = self.current if job is None else job
                atomic_json(self.root/job['id']/'status.json',job)
            except OSError:
                pass
