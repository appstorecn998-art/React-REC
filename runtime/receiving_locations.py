"""Coordinates from the original extraction, bound to the exact source bytes."""
import hashlib
import json
from pathlib import Path
from receiving_service import atomic_json
from receiving_review import normalized

def save_verified_region(path, folder, values, match, size):
    path=Path(path);key=hashlib.sha256(path.read_bytes()).hexdigest()
    target=Path(folder)/'verified-row-locations'/(key+'.json')
    try:data=json.loads(target.read_text(encoding='utf-8'))
    except (OSError,ValueError):data={'version':2,'sha256':key,'rows':{}}
    identity=normalized(values.get('Tên hàng trên phiếu (Ảnh)'))+'|'+str(values.get('STT trên phiếu') or '').strip()
    if data.get('version')!=2:data={'version':2,'sha256':key,'rows':{}}
    data['rows'][identity]={'box':list(match['box']),'anchor':list(match['anchor']),'text':match['text'],'size':list(size)}
    atomic_json(target,data)

def verified_region(path, folder, values):
    key=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    try:
        data=json.loads((Path(folder)/'verified-row-locations'/(key+'.json')).read_text(encoding='utf-8'))
        identity=normalized(values.get('Tên hàng trên phiếu (Ảnh)'))+'|'+str(values.get('STT trên phiếu') or '').strip()
        if data.get('sha256')!=key or data.get('version')!=2:return None
        match=data['rows'].get(identity)
        if not match:return None
        x0,y0,x1,y1=match['box'];w,h=match['size']
        if not (0<=x0<x1<=w and 0<=y0<y1<=h):return None
        return match
    except (OSError,ValueError,KeyError,TypeError):return None

def initial_region(path, folder, values):
    # Generative coordinates are only hints. Never illuminate an unverified box.
    return verified_region(path,folder,values)

