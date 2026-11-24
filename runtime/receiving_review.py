"""Read-only review hints and local image location. Never auto-corrects data."""
import hashlib
import io
from collections import OrderedDict
import json
import math
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageOps


def normalized(text):
    text = unicodedata.normalize('NFD', str(text or '').casefold().replace('đ','d'))
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in text if unicodedata.category(c) != 'Mn')))


def tokens(text):
    return set(normalized(text).split()) - {'kg','g','ml','l','cai','va','the','of','item'}


def has_code(values):
    return normalized(values.get('Mã vật tư')) not in {'', 'chua co ma', 'khong co ma'}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def numeric_issues(rows, catalog=None):
    result = {row: [] for row,_ in rows}
    sequences = {}
    for row, values in rows:
        issues = result[row]
        qty, received, price = (values.get(h) for h in ['Số lượng','Thực nhận','Đơn giá'])
        for header, value in [('SL giao',qty),('SL nhận',received),('Đơn giá',price)]:
            if not number(value) or value < 0: issues.append(header + ' chưa rõ/không hợp lệ')
        if number(qty) and number(received) and qty != received:
            issues.append('SL nhận khác SL giao — đối chiếu số sửa tay')
        printed = values.get('Thành tiền gốc (trước công thức)')
        if number(qty) and number(price) and number(printed) and not math.isclose(qty*price, printed, rel_tol=1e-6, abs_tol=1):
            issues.append('Tiền ghi trên phiếu khác SL giao × đơn giá — kiểm giá/VAT/chiết khấu')
        amount = values.get('Thành tiền')
        if number(received) and number(price) and number(amount) and not math.isclose(received*price,amount,rel_tol=1e-6,abs_tol=1):
            issues.append('Thành tiền khác SL nhận × đơn giá')
        if catalog and has_code(values):
            entry = catalog.get(str(values.get('Mã vật tư')))
            if entry and normalized(entry[1]) != normalized(values.get('Đơn vị tính')):
                issues.append('ĐVT khác danh mục — cần kiểm quy đổi')
        note = normalized(values.get('Ghi chú'))
        if any(s in note for s in ['chu viet tay chua ro','so viet tay chua ro','mo ho','can kiem tra so','stt thieu','stt trung']):
            issues.append('Ghi chú OCR có số/chữ cần kiểm')
        source = Path(str(values.get('Ảnh nguồn') or '')).name.casefold()
        stt = str(values.get('STT trên phiếu') or '').strip()
        if re.fullmatch(r'\d+', stt): sequences.setdefault(source,[]).append((row,int(stt)))
    for source, seq in sequences.items():
        previous=None; seen={}
        for row,stt in seq:
            if stt in seen:
                result[row].append('Trùng STT trên cùng trang'); result[seen[stt]].append('Trùng STT trên cùng trang')
            if previous is not None and stt != previous+1:
                result[row].append('STT không liên tiếp — kiểm có thiếu/trùng dòng')
            previous=stt; seen[stt]=row
    # Only independent numeric totals are compared. Application formulas are
    # calculated from the same rows and cannot independently verify OCR.
    printed_total = [v.get('Tổng tiền trên phiếu (Số lượng × Đơn giá)') for _,v in rows]
    printed_total = [v for v in printed_total if number(v)]
    if printed_total and rows and all(number(v.get('Số lượng')) and number(v.get('Đơn giá')) for _,v in rows):
        subtotal=sum(v['Số lượng']*v['Đơn giá'] for _,v in rows)
        if any(not math.isclose(subtotal,total,rel_tol=1e-6,abs_tol=1) for total in printed_total):
            for row,_ in rows: result[row].append('Tổng trên phiếu khác cộng dòng — kiểm thiếu dòng/VAT/chiết khấu')
    return result


def ranked_codes(query, entries):
    wanted=tokens(query)
    ranked=[]
    for i,(code,name,unit) in enumerate(entries):
        found=tokens(code+' '+name); common=wanted & found
        if not common: continue
        score=len(common)/max(1,len(wanted | found))
        if normalized(query) == normalized(code): score=2
        if score >= .08: ranked.append((score,i))
    return [i for score,i in sorted(ranked,key=lambda pair:(-pair[0],pair[1]))]


def choose_region(words, item_name, image_size, with_anchor=False):
    """Match item text, reject competing matches; return a full-width row strip."""
    wanted=tokens(item_name)
    alternatives=[tokens(part) for part in re.split(r'[/|]', str(item_name or ''))]
    alternatives=[part for part in alternatives if part] or [wanted]
    if not wanted: return None
    candidates=[]
    width,height=image_size
    # OCR often splits a single printed name into several boxes on one line.
    # Combine boxes with substantial vertical overlap, without joining rows.
    lines=[]
    for word in sorted(words,key=lambda w:w['box'][1]):
        if word.get('confidence',0)<.25:continue
        box=word['box']; target=None
        for line in lines:
            b=line['box'];overlap=min(b[3],box[3])-max(b[1],box[1])
            if overlap >= .6*min(b[3]-b[1],box[3]-box[1]):target=line;break
        if target is None:lines.append({'box':list(box),'parts':[word]})
        else:
            target['parts'].append(word);b=target['box']
            target['box']=[min(b[0],box[0]),min(b[1],box[1]),max(b[2],box[2]),max(b[3],box[3])]
    combined=[{'text':' '.join(w['text'] for w in sorted(line['parts'],key=lambda w:w['box'][0])),
               'box':line['box'],'confidence':min(w.get('confidence',0) for w in line['parts'])} for line in lines if len(line['parts'])>1]
    for word in [*words,*combined]:
        found=tokens(word['text']); common=wanted & found
        if not common or word.get('confidence',0) < .25: continue
        score=max(len(part & found)/max(1,len(part)) for part in [wanted,*alternatives])
        if score < .65 or (len(common)<2 and not any(part==found for part in alternatives)): continue
        x0,y0,x1,y1=word['box']
        if y0 < height*.12: continue  # supplier/header is not an item row
        candidates.append((score,y0,y1,word['text'],word['box']))
    candidates.sort(reverse=True)
    if not candidates: return None
    best=candidates[0]
    # Same text on two separate rows cannot be assigned safely.
    if any(abs(other[1]-best[1]) > max(16,best[2]-best[1])*1.5 and other[0] >= best[0]-.12 for other in candidates[1:]): return None
    # Small margin for glyphs; the old 65% padding included adjacent items.
    pad=max(2,min(8,(best[2]-best[1])*.18))
    top,bottom=best[1]-pad,best[2]+pad
    ax0,ay0,ax1,ay1=best[4]
    for line in lines:
        lx0,ly0,lx1,ly1=line['box']
        if min(ax1,lx1)<=max(ax0,lx0):continue
        if ly1<=best[1]:top=max(top,(ly1+best[1])/2)
        if ly0>=best[2]:bottom=min(bottom,(best[2]+ly0)/2)
    box=(0,max(0,int(math.floor(top))),width,min(height,int(math.ceil(bottom))))
    return {'box':box,'anchor':best[4],'text':best[3]} if with_anchor else box


_reader=None
def locate_page(path, cache_dir):
    """Local CPU OCR for positions only; no network/download and no number updates."""
    global _reader
    path=Path(path); content=path.read_bytes(); key=hashlib.sha256(b'local-locator-v1'+content).hexdigest()
    cache=Path(cache_dir)/(key+'.json')
    if cache.exists():
        try:
            data=json.loads(cache.read_text(encoding='utf-8'))
            if data.get('version')==1 and isinstance(data.get('words'),list): return data
        except (ValueError,OSError): pass
    import numpy as np
    import torch
    import easyocr
    torch.set_num_threads(2)
    if _reader is None: _reader=easyocr.Reader(['vi','en'],gpu=False,download_enabled=False,verbose=False,model_storage_directory=str(__import__('rec_runtime').user_root()/'models'))
    with Image.open(path) as source: image=ImageOps.exif_transpose(source).convert('RGB')
    size=image.size; image.thumbnail((1800,1800))
    sx,sy=size[0]/image.width,size[1]/image.height
    output=_reader.readtext(np.asarray(image),detail=1,paragraph=False,batch_size=1,workers=0)
    words=[]
    for points,text,confidence in output:
        xs=[p[0]*sx for p in points]; ys=[p[1]*sy for p in points]
        words.append({'text':str(text),'confidence':float(confidence),'box':[min(xs),min(ys),max(xs),max(ys)]})
    data={'version':1,'size':size,'words':words}
    # Image may have changed during OCR; never attach old coordinates to it.
    if hashlib.sha256(b'local-locator-v1'+path.read_bytes()).hexdigest()!=key:
        raise ValueError('Ảnh thay đổi trong lúc định vị; chọn lại dòng để thử.')
    from receiving_service import atomic_json
    atomic_json(cache,data)
    return data


def row_slope(image, box):
    """Estimate local table tilt from agreeing long rules, never from text alone."""
    import cv2
    cv2.setNumThreads(2)
    import numpy as np
    x0,y0,x1,y1=box
    margin=max(60,int((y1-y0)*2))
    band=image.crop((0,max(0,int(y0-margin)),image.width,min(image.height,int(y1+margin))))
    scale=min(1,1400/band.width)
    if scale<1:band=band.resize((1400,max(1,round(band.height*scale))))
    gray=cv2.cvtColor(np.asarray(band),cv2.COLOR_RGB2GRAY)
    edges=cv2.Canny(gray,50,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/1800,threshold=70,
                         minLineLength=max(80,int(band.width*.3)),maxLineGap=18)
    if lines is None:return 0.
    slopes=[(y2-y1)/(x2-x1) for x1,y1,x2,y2 in lines.reshape(-1,4)
            if x2!=x1 and abs((y2-y1)/(x2-x1))<.18]
    if len(slopes)<2:return 0.
    median=float(np.median(slopes))
    agreeing=[s for s in slopes if abs(s-median)<.012]
    if len(agreeing)<2 or len(agreeing)<len(slopes)*.6:return 0.
    return float(np.median(agreeing))


def complete_row_bounds(image, box, anchor, slope):
    """Find enclosing table rules at the anchor, or retain extra context."""
    import cv2
    cv2.setNumThreads(2)
    import numpy as np
    x0,y0,x1,y1=box
    ax0,ay0,ax1,ay1=anchor or box
    cx=(ax0+ax1)/2
    glyph=max(12,ay1-ay0)
    start=max(0,int(ay0-glyph*2))
    end=min(image.height,int(ay1+glyph*3))
    band=image.crop((0,start,image.width,end))
    scale=min(1,1600/band.width)
    if scale<1:band=band.resize((1600,max(1,round(band.height*scale))))
    gray=cv2.cvtColor(np.asarray(band),cv2.COLOR_RGB2GRAY)
    edges=cv2.Canny(gray,50,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/1800,threshold=65,
                         minLineLength=max(70,int(band.width*.35)),maxLineGap=20)
    levels=[]
    if lines is not None:
        for lx0,ly0,lx1,ly1 in lines.reshape(-1,4):
            if lx1==lx0:continue
            tilt=(ly1-ly0)/(lx1-lx0)
            if abs(tilt-slope)>.025:continue
            levels.append(start+(ly0+tilt*(cx*scale-lx0))/scale)
    # Rules must enclose the text, not slice through its center.
    above=[y for y in levels if ay0-glyph*2<=y<=ay0+glyph*.12]
    below=[y for y in levels if ay1-glyph*.12<=y<=ay1+glyph*2.5]
    if above and below:
        top,bottom=max(above),min(below)
        if bottom-top>=glyph*.85:
            return max(0,top-5),min(image.height,bottom+5)
    return max(0,min(y0,ay0-glyph*.65)),min(image.height,max(y1,ay1+glyph*1.4))


_crop_cache=OrderedDict()
_CROP_CACHE_BYTES=16*1024*1024
_decoded_page=None


def crop_region(path, box, anchor=None):
    global _decoded_page
    content=Path(path).read_bytes()
    content_hash=hashlib.sha256(content).digest()
    key=(content_hash,tuple(box),tuple(anchor) if anchor else None)
    cached=_crop_cache.get(key)
    if cached is not None:
        _crop_cache.move_to_end(key)
        return cached.copy()
    if _decoded_page is not None and _decoded_page[0]==content_hash:
        image=_decoded_page[1]
    else:
        with Image.open(io.BytesIO(content)) as source:image=ImageOps.exif_transpose(source).convert('RGB')
        _decoded_page=(content_hash,image) if image.width*image.height*3<=48*1024*1024 else None
    try:slope=row_slope(image,box)
    except (ImportError,ValueError):slope=0.
    x0,y0,x1,y1=box
    try:y0,y1=complete_row_bounds(image,box,anchor,slope)
    except (ImportError,ValueError):
        margin=max(12,(box[3]-box[1])*.7)
        y0,y1=max(0,y0-margin),min(image.height,y1+margin)
    center_x=(anchor[0]+anchor[2])/2 if anchor else (x0+x1)/2
    width,height=round(x1-x0),max(1,round(y1-y0))
    offset=y0+slope*(x0-center_x)
    image=image.transform((width,height),Image.Transform.AFFINE,
                          (1,0,x0,slope,1,offset),Image.Resampling.BICUBIC,fillcolor='white')
    if anchor:
        from PIL import ImageDraw
        ax0,ay0,ax1,ay1=anchor
        rect=(max(0,ax0-x0-4),max(0,ay0-y0-4),
              min(width-1,ax1-x0+4),min(height-1,ay1-y0+4))
        ImageDraw.Draw(image).rectangle(rect,outline='#2563eb',width=3)
    cost=image.width*image.height*3
    if cost<=_CROP_CACHE_BYTES:
        _crop_cache[key]=image.copy()
        while len(_crop_cache)>8 or sum(im.width*im.height*3 for im in _crop_cache.values())>_CROP_CACHE_BYTES:
            _crop_cache.popitem(last=False)
    return image


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('image'); parser.add_argument('cache')
    args=parser.parse_args()
    try:
        print(json.dumps(locate_page(args.image,args.cache),ensure_ascii=False))
    except Exception:
        raise SystemExit(1)

