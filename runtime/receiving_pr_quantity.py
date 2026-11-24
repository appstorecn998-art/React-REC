"""Manual PR quantity correction tied to the original extracted item."""
import hashlib,json,uuid
from datetime import datetime
from decimal import Decimal

def identity(item):return hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def approve(item,entry,quantity,reason):
    from receiving_units import positive,exact_text
    if not reason.strip():raise ValueError('Nhập căn cứ số lượng theo ảnh PR.')
    value=positive(quantity)
    event=dict(id=uuid.uuid4().hex,signature=identity(item),quantity=exact_text(value),original=item.get('quantity'),reason=reason.strip(),time=datetime.now().astimezone().isoformat())
    return dict(event,history=[*(entry.get('pr_quantity') or {}).get('history',[]),event])

def effective(item,entry):
    import AutoWatcher as aw
    rule=(entry or {}).get('pr_quantity')
    if not rule:return aw.parse_simple_quantity(item.get('quantity'))
    if rule.get('signature')!=identity(item):raise ValueError('Số lượng PR nhập tay đã cũ. Kiểm ảnh PR và nhập lại.')
    from receiving_units import positive
    q=positive(rule['quantity'])
    return Decimal(q.numerator)/Decimal(q.denominator)
