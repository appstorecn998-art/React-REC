"""Explicit deferred PR replacement; never grants posting permission."""
import hashlib,json
from pathlib import Path
from datetime import datetime
from receiving_service import atomic_json,sheet_signature,digest,invoice_images
from receiving_image_archive import image_name,source_digest


def evidence(folder,sheet,rows,images):
    refs=invoice_images(sheet,rows);sources=[p for p in images if image_name(p) in refs]
    if not sources or {image_name(p) for p in sources}!=refs:raise ValueError('Thiếu ảnh nguồn phiếu')
    keys=[]
    for hashfn in (source_digest,digest):
        key=hashlib.sha256(json.dumps(sorted((image_name(p),hashfn(p)) for p in sources)).encode()).hexdigest()
        path=Path(folder)/'.receiving/manual-pr-links'/(key+'.json')
        if path.exists():keys.append([path.name,digest(path)])
    return {'receipt':sheet_signature(sheet,rows),'sources':sorted([image_name(p),source_digest(p)] for p in sources),'pr_links':keys}


def mark_path(folder,sheet):return Path(folder)/'pending-replacement-pr'/(hashlib.sha256(sheet.encode()).hexdigest()+'.json')


def read(folder,sheet,rows,images):
    path=mark_path(folder,sheet)
    if not path.exists():return None
    value=json.loads(path.read_text(encoding='utf-8'))
    return value if value.get('active') and value.get('evidence')==evidence(folder,sheet,rows,images) else None


def set_pending(folder,sheet,rows,images,reason,enabled=True):
    if enabled and not str(reason).strip():raise ValueError('Nhập lý do chờ thay PR')
    path=mark_path(folder,sheet);old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    event=dict(active=enabled,sheet=sheet,reason=str(reason).strip(),time=datetime.now().astimezone().isoformat(),evidence=evidence(folder,sheet,rows,images))
    atomic_json(path,dict(event,history=[*old.get('history',[]),event]))
