"""Shared prepared pixels for previews and OCR; source images are never changed."""
import hashlib,io,json,logging,tempfile,os,threading
from pathlib import Path

ROOT=Path(__file__).parent/'output'/'straightened'
PREPARED_VERSION='prepared-jpeg-v1-3200-q94'
_locks={}
_locks_guard=threading.Lock()

def _content_digest(path):
    # Always hash bytes: Windows creation/mtime can survive same-size replacement.
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def content_identity(path,source_bytes=None):
    """SHA256 of source bytes, independent of filename, folder and timestamps."""
    if source_bytes is not None:return hashlib.sha256(source_bytes).hexdigest()
    return _content_digest(str(Path(path).resolve()))

def _identity(image_id):
    from straightening import VERSION
    return hashlib.sha256(f'{PREPARED_VERSION}:{VERSION}:{image_id}'.encode()).hexdigest()

def identity(path):
    """Content + preparation version identity (rotation variants share this base)."""
    return _identity(content_identity(path))

def _image_lock(image_id):
    with _locks_guard:return _locks.setdefault(image_id,threading.RLock())

def _read_metadata(path):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def _atomic_write(destination,write):
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=destination.parent,suffix='.tmp');os.close(fd);temporary=Path(name)
    try:write(temporary);temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)

def _save_rotation(image_id,rotation):
    target=ROOT/(image_id+'.orientation.json')
    if _read_metadata(target).get('rotation')!=rotation:
        _atomic_write(target,lambda p:p.write_text(json.dumps({'rotation':rotation}),encoding='utf-8'))

def _saved_rotation(path,image_id):
    value=_read_metadata(ROOT/(image_id+'.orientation.json')).get('rotation')
    if value in (0,90,180,270):return value
    try:
        # Read the old path/stat orientation and migrate it while that path exists.
        path=Path(path);st=path.stat();source=f'{path.resolve()}:{st.st_size}:{st.st_mtime_ns}'
        if content_identity(path)!=image_id:return 0
        from straightening import VERSION
        keys=[hashlib.sha256(source.encode()).hexdigest()+'.orientation']
        keys += [hashlib.sha256(f'{v}:{source}'.encode()).hexdigest() for v in
                 (VERSION,'paper-boundary-v7-visible-side','grid-full-frame-v3-paper-padding','paper-boundary-v4-crop-first')]
        for key in keys:
            value=_read_metadata(ROOT/(key+'.json')).get('rotation')
            if value in ((0,90,180,270) if key.endswith('.orientation') else (90,180,270)):
                _save_rotation(image_id,value)
                return value
    except (OSError,ValueError):pass
    return 0

def saved_rotation(path):
    """Content-based review, with lazy migration of legacy path/stat metadata."""
    try:
        image_id=content_identity(path)
        with _image_lock(image_id):return _saved_rotation(path,image_id)
    except (OSError,ValueError):return 0

def build(path,rotation=None,*,source_bytes=None):
    """Persist one canonical JPEG per content/version/rotation, at most 3200px.

    Returns the legacy file/method/rotation fields plus width, height, image_id
    (source SHA256), cache_key (prepared variant), and processing versions.
    source_bytes optionally supplies the caller's original source snapshot.
    """
    from PIL import Image,ImageOps
    from straightening import straighten,VERSION
    path=Path(path);image_id=content_identity(path,source_bytes)
    with _image_lock(image_id):
        if rotation is None:rotation=_saved_rotation(path,image_id)
        if rotation not in (0,90,180,270):raise ValueError('Invalid page rotation')
        key=f'{_identity(image_id)}-{rotation}'
        target=ROOT/(key+'.jpg');metadata=ROOT/(key+'.json')
        expected=dict(file=target.name,rotation=rotation,image_id=image_id,cache_key=key,
                      version=VERSION,prepared_version=PREPARED_VERSION)
        cached=_read_metadata(metadata)
        if (target.is_file() and all(cached.get(k)==v for k,v in expected.items())
                and isinstance(cached.get('method'),str)
                and all(isinstance(cached.get(k),int) and cached[k]>0 for k in ('width','height'))):
            _save_rotation(image_id,rotation)
            return cached
        if path.suffix.lower() in {'.heic','.heif'}:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        raw=source_bytes if source_bytes is not None else path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=image_id:raise ValueError('Source image changed during preparation')
        with Image.open(io.BytesIO(raw)) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
        image=image.rotate(rotation,expand=True);image.thumbnail((3200,3200),Image.Resampling.LANCZOS)
        result,method=straighten(image)
        result.thumbnail((3200,3200),Image.Resampling.LANCZOS)
        _atomic_write(target,lambda p:result.save(p,'JPEG',quality=94))
        data=dict(expected,method=method,width=result.width,height=result.height)
        _atomic_write(metadata,lambda p:p.write_text(json.dumps(data),encoding='utf-8'))
        _save_rotation(image_id,rotation)
        return data

def attach_lazy(paths,allowed):
    """Register preview URLs without decoding or straightening any image."""
    urls=[]
    for path in paths:
        token=f'preview-{identity(path)}-{saved_rotation(path)}'
        allowed[token]=path
        urls.append('/api/preview/'+token)
    return urls or None


def resolve_preview(path):
    """Build only the requested page; a bad image falls back to its source."""
    try:
        return ROOT/build(path)['file']
    except (OSError,ValueError):
        logging.warning('Chưa căn được ảnh %s; giữ ảnh gốc để kiểm phiếu.',path.name)
        return path


def attach(paths,allowed):
    urls=[]
    for path in paths:
        try:
            cached=build(path)
            target=ROOT/cached['file'];token=target.stem
        except (OSError,ValueError):
            logging.warning('Chưa căn được ảnh %s; giữ ảnh gốc để kiểm phiếu.',path.name)
            target=path;token=identity(path)+'-original'
        allowed[token]=target;urls.append('/api/image/'+token)
    return urls or None

if __name__=='__main__':
    import server,time
    start=time.perf_counter()
    from concurrent.futures import ThreadPoolExecutor
    from collections import Counter
    import cv2
    cv2.setNumThreads(1)
    reports=list(server.available_days().values())
    sources={p.resolve() for report in reports for p in server.day_images(report.parent)}
    sources.update(p.resolve() for p in (server.STORE/'AnhPhieu').rglob('*') if p.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.heic','.heif'})
    paths=sorted(sources);originals=paths+reports
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    def process(path):
        try:return dict(source=str(path),**build(path),ok=True)
        except Exception as exc:return dict(source=str(path),ok=False,error=type(exc).__name__)
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i,item in enumerate(pool.map(process,paths),1):
            results.append(item)
            if i%20==0 or i==len(paths):print('prepared',i,'/',len(paths),flush=True)
    unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==before[str(p)] for p in originals)
    summary=dict(count=len(paths),reports=len(reports),seconds=round(time.perf_counter()-start,3),unchanged=unchanged,methods=dict(Counter(r.get('method','error') for r in results)),results=results)
    (ROOT/'all-images-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in summary.items() if k!='results'},flush=True)
    assert unchanged,'Source files changed during image processing'
    assert all(r['ok'] for r in results),'Some images need review; see all-images-summary.json'
