from receiving_image_archive import image_name, source_digest
"""Explicit no-PO reporting mode; never invents ordered/shortage quantities."""
import json,hashlib
from pathlib import Path
from datetime import datetime
from receiving_service import invoice_images,digest,sheet_signature,atomic_json

def path_for(folder,sheet,rows,images):
    refs=invoice_images(sheet,rows);source=[p for p in images if image_name(p) in refs]
    if not source or {image_name(p) for p in source}!=refs:raise ValueError('Thiếu ảnh nguồn của phiếu.')
    key=hashlib.sha256(json.dumps(sorted((image_name(p),digest(p)) for p in source)).encode()).hexdigest()
    return Path(folder)/'.receiving/no-po'/(key+'.json')

def active(folder,sheet,rows,images):
    try:
        data=json.loads(path_for(folder,sheet,rows,images).read_text(encoding='utf-8'))
        return data.get('active') is True and data.get('signature')==sheet_signature(sheet,rows)
    except (OSError,ValueError,TypeError):return False

def set_mode(folder,sheet,rows,images,enabled):
    path=path_for(folder,sheet,rows,images)
    previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    event={'active':bool(enabled),'signature':sheet_signature(sheet,rows),'time':datetime.now().astimezone().isoformat(),'sheet':sheet}
    atomic_json(path,dict(event,history=[*previous.get('history',[]),event]))
