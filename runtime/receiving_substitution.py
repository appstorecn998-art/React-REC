"""Explicit, receipt-specific approval of a substitute; no catalog learning."""
import hashlib,json,uuid
from datetime import datetime,date

def signature(row,item,delivery,entry):
    return hashlib.sha256(json.dumps([row,item,delivery,{k:entry.get(k) for k in ('factor','scope')}],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def approve(row,item,delivery,entry,department,purchase,day,reason):
    if not all(str(v or '').strip() for v in (department,purchase,reason)):raise ValueError('Nhập bộ phận/người duyệt, Purchase duyệt và căn cứ đổi hàng.')
    date.fromisoformat(day)
    event=dict(id=uuid.uuid4().hex,action='approve',time=datetime.now().astimezone().isoformat(),signature=signature(row,item,delivery,entry),department=department.strip(),purchase=purchase.strip(),date=day,reason=reason.strip(),original_item=item.get('item_name'),substitute_item=delivery.get('Tên hàng trên phiếu (Ảnh)'),supplier=delivery.get('Nhà cung cấp'))
    return dict(event,history=[*(entry.get('substitution_approval') or {}).get('history',[]),event])

def effective(row,item,delivery,entry):
    rule=(entry or {}).get('substitution_approval')
    if not rule or rule.get('action')=='revoke':return None
    if rule.get('signature')!=signature(row,item,delivery,entry):raise ValueError('Duyệt hàng thay thế đã cũ; nguồn PR/phiếu/quy đổi đã đổi. Cần xác nhận lại.')
    if not all(rule.get(k) for k in ('department','purchase','date','reason')):raise ValueError('Duyệt hàng thay thế thiếu căn cứ.')
    return rule

def revoke(entry):
    old=entry.get('substitution_approval')
    if not old:raise ValueError('Chưa có duyệt hàng thay thế.')
    event={k:v for k,v in old.items() if k!='history'}
    event.update(id=uuid.uuid4().hex,action='revoke',time=datetime.now().astimezone().isoformat())
    return dict(event,history=[*old.get('history',[]),event])
