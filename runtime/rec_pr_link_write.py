"""Explicit PR selection changes with preimage checks and recoverable history."""
import json
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from receiving_service import atomic_json


def write_link(path,value,*,expected=None,action):
    from multi_delivery import output_lock
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with output_lock(path):
        return _write_locked(path,value,expected=expected,action=action)


def _write_locked(path,value,*,expected,action):
    before=path.read_bytes() if path.exists() else None
    if before is not None and json.loads(before)==value:return False
    if before!=expected:
        raise ValueError('Liên kết PR đã có hoặc vừa thay đổi. Mở lại phiếu; cần xác nhận trước khi đổi PR đã gán.')
    event=dict(time=datetime.now(timezone.utc).isoformat(),action=action,path=str(path),
               previous=json.loads(before) if before is not None else None,requested=value)
    # Preserve the previous selection before replacing it; this records intent,
    # while the link file remains authoritative if the final write fails.
    history=path.parent.parent/'pr-link-history'/path.stem/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')+'_'+uuid4().hex+'.json')
    atomic_json(history,event)
    current=path.read_bytes() if path.exists() else None
    if current!=before:raise ValueError('Liên kết PR vừa thay đổi. Chưa ghi đè; mở lại phiếu.')
    atomic_json(path,value)
    return True
