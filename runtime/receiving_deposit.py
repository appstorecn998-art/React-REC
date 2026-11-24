"""Explicit, receipt-local deposit decisions. No supplier-wide inference."""
import hashlib
import json
from datetime import datetime, timezone

def key(row):
    return -int(row)-1

def signature(row, value):
    return hashlib.sha256(json.dumps([row,value],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def approve(row, value, reason):
    if not str(reason).strip():
        raise ValueError('Nhập căn cứ / người xác nhận khoản cọc.')
    return {'deposit':{'signature':signature(row,value),'reason':str(reason).strip(),
                       'confirmed_at':datetime.now(timezone.utc).isoformat(),'kind':'returnable_container_deposit'}}

def effective(row, value, conversions):
    entry=(conversions or {}).get(key(row),(conversions or {}).get(str(key(row)),{}))
    decision=entry.get('deposit') if isinstance(entry,dict) else None
    if not isinstance(decision,dict) or decision.get('kind')!='returnable_container_deposit':return None
    return decision if decision.get('signature')==signature(row,value) and decision.get('reason') else None
