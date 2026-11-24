"""Paired OCR audit of the 12 day-20 photos; writes only isolated benchmark output."""
import concurrent.futures, hashlib, inspect, io, json, os, sys, time
from pathlib import Path
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server
import AutoWatcher as aw
from ocr_quality import prepare
from preview_cache import saved_rotation, build

OUT=ROOT/'output'/'ocr-benchmark-day20'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    snapshot=server.load('2026-11-20')
    paths=list(dict.fromkeys(server.allowed_images[u.split('/')[-1]] for d in snapshot['receipts'] for u in d['pages']))
    assert len(paths)==12, len(paths)
    reports=list(server.STORE.glob('Thang */Ngay */TongHopPhieuNgay_*.xlsx'))
    protected=paths+reports
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    profile=server.ocr_jobs.profile
    key=server.ocr_jobs._secrets()[0]
    _,groups=aw.load_catalog_data(profile/'DanhMuc.xlsm')
    manifest={'model':aw.MODEL,'day':'2026-11-20','pairs':[],'baseline':'Original with reviewed rotation, same 3200px limit and JPEG94; no crop/deskew','reference_note':'Saved report is a comparison reference, not independently verified ground truth.'}
    tasks=[]
    for p in paths:
        row={'source':str(p),'sha256':before[str(p)],'method':build(p)['method'],'rotation':saved_rotation(p)}
        manifest['pairs'].append(row)
        with Image.open(p) as src: im=ImageOps.exif_transpose(src).convert('RGB')
        im=im.rotate(saved_rotation(p),expand=True);im.thumbnail((3200,3200),Image.Resampling.LANCZOS)
        buf=io.BytesIO();im.save(buf,'JPEG',quality=94)
        for mode,data in [('original',buf.getvalue()),('processed',prepare(p,processed=True))]:
            target=OUT/(p.name+'.'+mode+'.jpg');target.write_bytes(data)
            tasks.append((p.name,mode,data))
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'saved-reference.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    def run(task):
        name,mode,data=task;target=OUT/(name+'.'+mode+'.json')
        fingerprint=hashlib.sha256(data+aw.MODEL.encode()+json.dumps(groups,sort_keys=True,ensure_ascii=False).encode()+aw.receipt_rules_fingerprint()+inspect.getsource(aw.request_batch_document).encode()).hexdigest()
        if target.exists():
            cached=json.loads(target.read_text(encoding='utf-8'))
            if cached.get('fingerprint')==fingerprint:return name,mode,'cached'
        started=time.monotonic()
        try:
            document=aw.request_batch_document(key,aw.MODEL,data,groups,120)
            aw.atomic_cache_json(target,{'document':document,'seconds':round(time.monotonic()-started,2),'fingerprint':fingerprint})
            return name,mode,'ok'
        except Exception as exc:
            # Do not log SDK exception text: it can contain request credentials.
            return name,mode,type(exc).__name__
    # Fail fast on connectivity/auth; avoid scheduling a whole blocked batch.
    first=run(tasks[0]);print(first,flush=True)
    if first[2] not in ('ok','cached'):
        (OUT/'blocked.json').write_text(json.dumps({'first_request':first}),encoding='utf-8')
        return 2
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run,tasks[1:]):print(result,flush=True)
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert before==after,'Source/report changed during benchmark'
    (OUT/'integrity.json').write_text(json.dumps({'unchanged':True,'images':len(paths),'reports':len(reports)}),encoding='utf-8')
    return 0

if __name__=='__main__':raise SystemExit(main())
