"""OCR consumes saved preview pixels; never changes source images or business rules."""
import hashlib,io,logging
from pathlib import Path
from PIL import Image
from contextvars import ContextVar

_prepared_key=ContextVar('rec_prepared_key',default=None)

VERSION='rec-react-ocr-quality-v13-shared-row-locations'

def prepare(path,source_bytes=None,*,enhanced=True,processed=False):
    """Return the canonical prepared JPEG verbatim by default.

    processed is a legacy alias: both values now use the shared artifact, never
    a second straighten. source_bytes, if supplied, must be original source bytes.
    Reduced mode only downsizes to 2400px; normalized coordinates still refer to
    the canonical build() width/height, with no additional crop or rotation.
    """
    import preview_cache
    prepared=preview_cache.build(path,source_bytes=source_bytes)
    _prepared_key.set(prepared['cache_key'])
    data=(preview_cache.ROOT/prepared['file']).read_bytes()
    if enhanced:return data
    with Image.open(io.BytesIO(data)) as source:
        if max(source.size)<=2400:return data
        image=source.convert('RGB')
    image.thumbnail((2400,2400),Image.Resampling.LANCZOS)
    out=io.BytesIO();image.save(out,'JPEG',quality=92)
    logging.info('Chuẩn bị OCR %s: %sx%s -> %sx%s; %s; ảnh màu, không thay ảnh gốc.',Path(path).name,prepared['width'],prepared['height'],*image.size,prepared['method'])
    return out.getvalue()

def safe_page_crop(image):
    """Only warp a complete, unoccluded paper quadrilateral with an image margin.

    Clipped corners, stacked pages, strongly folded pages and uncertain contours stay unchanged.
    """
    try:
        import cv2,numpy as np
    except ImportError:return image,False
    scale=min(1,1000/max(image.size));sample=np.asarray(image.resize((round(image.width*scale),round(image.height*scale))))
    gray=cv2.cvtColor(sample,cv2.COLOR_RGB2GRAY);blur=cv2.GaussianBlur(gray,(5,5),0)
    edges=cv2.Canny(blur,40,120);edges=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    contours,_=cv2.findContours(edges,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    h,w=gray.shape;valid=[]
    for contour in sorted(contours,key=cv2.contourArea,reverse=True)[:12]:
        area=cv2.contourArea(contour)/(h*w)
        if not .50<=area<=.94:continue
        poly=cv2.approxPolyDP(contour,.015*cv2.arcLength(contour,True),True)
        if len(poly)!=4 or not cv2.isContourConvex(poly):continue
        pts=poly[:,0,:].astype('float32')
        if np.any(pts[:,0]<w*.015) or np.any(pts[:,0]>w*.985) or np.any(pts[:,1]<h*.015) or np.any(pts[:,1]>h*.985):continue
        ordered=np.zeros((4,2),np.float32);s=pts.sum(1);dif=np.diff(pts,axis=1).reshape(-1)
        ordered[0]=pts[s.argmin()];ordered[2]=pts[s.argmax()];ordered[1]=pts[dif.argmin()];ordered[3]=pts[dif.argmax()]
        if len(np.unique(ordered,axis=0))!=4:continue
        lengths=[np.linalg.norm(ordered[(i+1)%4]-ordered[i]) for i in range(4)]
        ratio=max(lengths)/min(lengths)
        if ratio>2.4:continue
        # Reject extreme perspective and dark objects mistaken for a white document.
        region=np.zeros((h,w),np.uint8);cv2.fillConvexPoly(region,ordered.astype('int32'),255)
        if np.median(gray[region>0])<145:continue
        valid.append(ordered)
    if len(valid)!=1:return image,False
    quad=valid[0]/scale
    # Small safety margin expands the quadrilateral rather than trimming handwriting.
    center=quad.mean(0);quad=center+(quad-center)*1.015
    quad[:,0]=np.clip(quad[:,0],0,image.width-1);quad[:,1]=np.clip(quad[:,1],0,image.height-1)
    tw=round(max(np.linalg.norm(quad[1]-quad[0]),np.linalg.norm(quad[2]-quad[3])))
    th=round(max(np.linalg.norm(quad[3]-quad[0]),np.linalg.norm(quad[2]-quad[1])))
    matrix=cv2.getPerspectiveTransform(quad,np.array([[0,0],[tw-1,0],[tw-1,th-1],[0,th-1]],np.float32))
    result=cv2.warpPerspective(np.asarray(image),matrix,(tw,th),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(result),True

def audit(document):
    """Flag inconsistency for humans; do not invent, delete, merge or correct OCR rows."""
    if document.get('document_type')!='delivery':return []
    warnings=[];seen=set();numbers=[]
    for i,item in enumerate(document.get('items',[]),1):
        stt=str(item.get('source_stt','')).strip()
        if stt.isdigit():
            n=int(stt);numbers.append(n)
            if n in seen:warnings.append(f'Dòng {i}: STT {n} lặp, kiểm lại ảnh (không tự gộp).')
            seen.add(n)
        if item.get('receipt_needs_review') or item.get('receipt_mark')=='unclear':warnings.append(f'Dòng {i}: thực nhận hoặc dấu viết tay chưa rõ.')
        if item.get('receipt_mark') in {'cross_without_number','cross_with_number'}:
            warnings.append(f'Dòng {i}: có dấu gạch; cần rà vị trí dấu và số sửa trên ảnh gốc.')
        for field,label in [('unit_price','đơn giá'),('quantity','lượng giao')]:
            if not str(item.get(field,'')).strip():warnings.append(f'Dòng {i}: thiếu {label}, cần kiểm ảnh.')
    if numbers and any(b!=a+1 for a,b in zip(numbers,numbers[1:])):warnings.append('STT không liên tục: có thể thiếu/sai thứ tự; không tự thêm hàng.')
    return warnings

def install(report_file,*,enhanced=True):
    """Install only inside the web OCR child; desktop REC code stays unchanged."""
    import AutoWatcher as aw
    # Optional evidence rides on the existing document OCR response; no extra call.
    import copy
    aw.BATCH_DOCUMENT_SCHEMA=copy.deepcopy(aw.BATCH_DOCUMENT_SCHEMA)
    aw.BATCH_DOCUMENT_SCHEMA['properties']['items']['items']['properties']['row_box']={
        'type':'string','description':'Top,left,bottom,right on full prepared target page, 0..1000; empty if uncertain.'}
    aw.FULL_NAME_PROMPT+='''\nVới mỗi dòng hàng, row_box là vùng của chính dòng trên ẢNH TOÀN TRANG mục tiêu đã chuẩn bị,
không phải trên ảnh ví dụ hoặc dải chi tiết. Ghi top,left,bottom,right theo thang 0–1000.
Bao trọn dòng hàng từ tên tới các cột lượng/giá, không gồm dòng trước/sau.
Không xác định chắc thì để row_box rỗng. Không suy tọa độ bằng chia đều số dòng.\n'''
    original_fingerprint=aw.receipt_rules_fingerprint
    from ocr_details import INSTRUCTION
    from preview_cache import PREPARED_VERSION
    from straightening import VERSION as STRAIGHTENING_VERSION
    aw.receipt_rules_fingerprint=lambda:hashlib.sha256(original_fingerprint()+f'{VERSION}:{PREPARED_VERSION}:{STRAIGHTENING_VERSION}:{enhanced}:{INSTRUCTION}'.encode()).digest()
    from functools import partial
    aw.prepare_image=partial(prepare,enhanced=enhanced)
    if enhanced:
        from ocr_details import install as install_details
        install_details(aw)
    original_request=aw.request_batch_document
    def request(*args,**kwargs):
        key=_prepared_key.get()
        document=original_request(*args,**kwargs)
        if key is not None:document['_rec_prepared_key']=key
        else:document.pop('_rec_prepared_key',None)
        return document
    aw.request_batch_document=request
    original_extract=aw.extract_batch_document
    import threading
    warning_lock=threading.Lock()
    original_cache_path=aw.batch_document_cache_path
    def cache_path(path,*args,**kwargs):
        from preview_cache import saved_rotation
        target=original_cache_path(path,*args,**kwargs)
        return target.with_name(target.stem+f'-rotation{saved_rotation(path)}'+target.suffix)
    aw.batch_document_cache_path=cache_path
    def extract(*args,**kwargs):
        from ocr_events import emit
        image=Path(args[0]) if args and args[0] is not None else None
        emit('image_start','Đang đọc ảnh.',file=image.name if image else '')
        prepared_token=_prepared_key.set(None)
        try:result=original_extract(*args,**kwargs)
        except Exception as exc:
            emit('image_error','Ảnh chưa đọc xong.',file=image.name if image else '',exception=type(exc).__name__,error_message=str(exc),http_status=getattr(exc,'status_code',None) or getattr(exc,'code',None))
            raise
        finally:_prepared_key.reset(prepared_token)
        document=result['document']
        if image is not None:
            try:
                from row_locations import record_document
                record_document(image,document)
            except (OSError,ValueError) as exc:
                logging.warning('Chưa lưu được vị trí dòng ảnh %s: %s',image.name,type(exc).__name__)
        if document['document_type'] == 'delivery':
            for item in document['items']:
                if (item.get('receipt_mark') in {'cross_without_number', 'cross_with_number'}
                        and item.get('receipt_mark_location') != 'quantity'):
                    item['receipt_mark'] = 'unclear'
                    from receipt_rules import apply_receipt_rules
                    apply_receipt_rules(item, aw.parse_simple_quantity)
        emit('image_done','Đã đọc và kiểm nội dung ảnh.',file=Path(result['path']).name,rows=len(document.get('items',[])),document_type=document.get('document_type'))
        warnings=audit(document)
        if warnings:
            import json
            path=Path(report_file)
            with warning_lock:
                previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
                previous.append({'reference':Path(result['path']).name+' · '+document.get('reference_id',''),'warnings':warnings})
                aw.atomic_cache_json(path,previous)
            for warning in warnings[:8]:logging.warning('Cần rà OCR: %s',warning)
        return result
    aw.extract_batch_document=extract
