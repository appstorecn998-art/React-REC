"""Cached local page preparation and name-anchored coordinates for saved REC rows."""
import hashlib,json,re,time,unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from PIL import Image,ImageOps
import numpy as np
from ocr_quality import safe_page_crop

ROOT=Path(__file__).parent/'output'/'page-geometry'
VERSION='v1'

def norm(text):
    text=unicodedata.normalize('NFD',str(text).lower().replace('đ','d'))
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).strip()

def signature(paths,rows):
    return hashlib.sha256(json.dumps([VERSION,[(str(p.resolve()),p.stat().st_size,p.stat().st_mtime_ns) for p in paths],rows],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def candidates(ocr,w,h):
    boxes=[]
    for poly,text,confidence in ocr:
        a=np.array(poly);x,y=a.min(0);xx,yy=a.max(0)
        if confidence<.12:continue
        boxes.append(dict(text=text,x=float(x),y=float(y),right=float(xx),bottom=float(yy),confidence=float(confidence)))
    result=[]
    for b in boxes:
        group=[b]
        # Join wrapped product names; never join the adjacent numeric columns.
        below=sorted([c for c in boxes if c['y']>=b['bottom']-3 and c['y']-b['bottom']<min(h*.012,(b['bottom']-b['y'])*.8) and abs(c['x']-b['x'])<w*.035],key=lambda c:c['y'])
        for c in [None]+below[:2]:
            if c:group.append(c)
            result.append(dict(text=' '.join(x['text'] for x in group),x=min(x['x'] for x in group)/w,y=min(x['y'] for x in group)/h,right=max(x['right'] for x in group)/w,bottom=max(x['bottom'] for x in group)/h,confidence=min(x['confidence'] for x in group)))
    return result

def similarity(target,text):
    a=norm(target.split('Note:')[0]);b=norm(text)
    if not a or not b:return 0
    if len(a)<9:return 1.0 if a==b else 0
    # Partial name anchors must retain enough of the actual product name.
    return SequenceMatcher(None,a,b).ratio()

def match_rows(rows,pages):
    regions=[];pending=[]
    for row in rows:
        target=row['Tên hàng trên phiếu (Ảnh)']
        ranked=sorted([(similarity(target,c['text']),i,c) for i,p in enumerate(pages) for c in p['candidates']],key=lambda x:x[0],reverse=True)
        if not ranked or ranked[0][0]<.70:
            pending.append(row['sourceRow']);continue
        score,page,c=ranked[0]
        others=[s for s,p,b in ranked[1:] if p!=page or abs(b['y']-c['y'])>.025]
        if others and score-others[0]<.09:
            pending.append(row['sourceRow']);continue
        regions.append(dict(sourceRow=row['sourceRow'],page=page,x=.005,y=max(0,c['y']-.004),width=.99,height=min(1,c['bottom']+.004)-max(0,c['y']-.004),score=round(score,3),anchor=c['text'],method='local-name'))
    # One image location cannot silently stand for two different saved rows.
    conflicts=set()
    for a in regions:
        for b in regions:
            if a is not b and a['page']==b['page']:
                overlap=min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y'])
                if overlap>min(a['height'],b['height'])*.3:conflicts.update([a['sourceRow'],b['sourceRow']])
    pending+=sorted(conflicts)
    return [r for r in regions if r['sourceRow'] not in conflicts],sorted(set(pending))

def process(paths,rows,reader):
    key=signature(paths,rows);folder=ROOT/key;manifest=folder/'result.json'
    if manifest.exists():return json.loads(manifest.read_text(encoding='utf-8'))
    folder.mkdir(parents=True,exist_ok=True);started=time.perf_counter();pages=[]
    for index,path in enumerate(paths):
        with Image.open(path) as source:original=ImageOps.exif_transpose(source).convert('RGB')
        prepared,cropped=safe_page_crop(original)
        best=None
        for angle in [0,90,270]:
            image=prepared.rotate(angle,expand=True)
            image.thumbnail((1800,1800),Image.Resampling.LANCZOS)
            ocr=reader.readtext(np.array(image),batch_size=8,workers=0)
            cs=candidates(ocr,*image.size)
            score=sum(max((similarity(r['Tên hàng trên phiếu (Ảnh)'],c['text']) for c in cs),default=0) for r in rows)
            if best is None or score>best[0]:best=(score,image,cs,angle)
            # Only sideways/illegible pages need additional orientation passes.
            if angle==0 and any(similarity(r['Tên hàng trên phiếu (Ảnh)'],c['text'])>=.70 for r in rows for c in cs):break
        _,image,cs,angle=best
        name=f'page-{index}.jpg';image.save(folder/name,quality=94)
        pages.append(dict(file=name,cropped=cropped,rotation=angle,width=image.width,height=image.height,candidates=cs))
        print(path.name,'crop',cropped,'rotation',angle,flush=True)
    regions,pending=match_rows(rows,pages)
    result=dict(key=key,pages=pages,regions=regions,pending=pending,seconds=round(time.perf_counter()-started,2))
    tmp=manifest.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');tmp.replace(manifest)
    return result

def attach(paths,rows,allowed):
    key=signature(paths,rows);manifest=ROOT/key/'result.json'
    if not manifest.exists():return None
    data=json.loads(manifest.read_text(encoding='utf-8'));urls=[]
    for p in data['pages']:
        path=ROOT/key/p['file'];token=hashlib.sha256(str(path).encode()).hexdigest()[:24];allowed[token]=path;urls.append('/api/image/'+token)
    return dict(pages=urls,regions=data['regions'],pending=data['pending'],cropped=[p['cropped'] for p in data['pages']])

if __name__=='__main__':
    import server,torch,easyocr
    torch.set_num_threads(4)
    from local_runtime import PROFILE
    reader=easyocr.Reader(['vi','en'],gpu=False,model_storage_directory=str(PROFILE/'models'),download_enabled=False,verbose=False)
    day='2026-11-20';data=server.load(day);summary=[]
    report=server.available_days()[day];before=hashlib.sha256(report.read_bytes()).hexdigest()
    for doc in data['receipts']:
        paths=[server.allowed_images[p.split('/')[-1]] for p in doc['pages']]
        hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        result=process(paths,doc['rows'],reader)
        assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        summary.append(dict(file=doc['file'],rows=len(doc['rows']),mapped=len(result['regions']),pending=result['pending'],seconds=result['seconds'],key=result['key']))
        print(summary[-1],flush=True)
    assert before==hashlib.sha256(report.read_bytes()).hexdigest()
    (ROOT/'day20-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
