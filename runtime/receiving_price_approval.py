"""Explicit Purchase price approval with append-only event history."""
import json,hashlib,uuid
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from receiving_service import atomic_json

def signature(row,pr,delivery,entry):
    values=[row,pr,delivery.get('Nhà cung cấp'),delivery.get('Tên hàng trên phiếu (Ảnh)'),delivery.get('Mã vật tư'),delivery.get('Đơn vị tính'),delivery.get('Đơn giá'),delivery.get('SHA-256 ảnh nguồn'),entry.get('factor'),entry.get('scope')]
    return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def approve(row,pr,delivery,entry,new_price,person,date,reason):
    from receiving_units import positive,exact_text
    from datetime import date as Date
    price=positive(new_price)
    if not str(person).strip() or not str(reason).strip():raise ValueError('Nhập người Purchase xác nhận và căn cứ thay đổi.')
    try:Date.fromisoformat(date)
    except (ValueError,TypeError):raise ValueError('Ngày xác nhận theo YYYY-MM-DD.')
    old=(entry.get('price_approval') or {}).get('price') or str(pr.get('unit_price',''))
    event=dict(id=uuid.uuid4().hex,action='approve',time=datetime.now().astimezone().isoformat(),original_price=pr.get('unit_price'),previous_price=old,price=exact_text(price),unit=pr.get('unit'),person=str(person).strip(),date=date,reason=str(reason).strip(),supplier=delivery.get('Nhà cung cấp'),item=pr.get('item_name'),signature=signature(row,pr,delivery,entry))
    return dict(event,history=[*(entry.get('price_approval') or {}).get('history',[]),event])

def effective(row,pr,delivery,entry):
    saved=(entry or {}).get('price_approval')
    if not saved or saved.get('action')=='revoke':return None
    if saved.get('signature')!=signature(row,pr,delivery,entry):raise ValueError('Duyệt giá đã cũ do PR/NCC/đơn vị/giá phiếu đổi. Purchase cần xác nhận lại.')
    return saved

def revoke(entry):
    old=entry.get('price_approval')
    if not old:raise ValueError('Chưa có duyệt giá để bỏ.')
    event=dict(old);event.pop('history',None);event.update(id=uuid.uuid4().hex,action='revoke',time=datetime.now().astimezone().isoformat())
    return dict(event,history=[*old.get('history',[]),event])

def audit(path,conversions):
    from multi_delivery import output_lock
    path=Path(path);journal=path.with_suffix('.price-history.json')
    with output_lock(journal):
        stored=json.loads(journal.read_text(encoding='utf-8')) if journal.exists() else {'version':1,'events':[]}
        ids={e['id'] for e in stored['events']}
        for index,entry in (conversions or {}).items():
            for event in (entry.get('price_approval') or {}).get('history',[]):
                if event['id'] not in ids:stored['events'].append(dict(event,pr_index=int(index)));ids.add(event['id'])
        if stored['events']:atomic_json(journal,stored)
