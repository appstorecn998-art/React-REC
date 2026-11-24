"""Receipt-scoped approval, retaining PR quantity and the supplemental PR obligation."""
import hashlib,json,uuid
from datetime import datetime


def signature(row,pr,delivery,entry,ordered,received,previous=0):
    from receiving_units import exact_text
    value=[row,pr,delivery,entry.get('factor'),entry.get('scope'),entry.get('quantity_correction'),
           exact_text(ordered),exact_text(received),exact_text(previous)]
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def approve(row,pr,delivery,entry,ordered,received,person,reason,previous=0):
    from receiving_units import exact_text
    from fractions import Fraction
    previous=Fraction(str(previous));total=Fraction(str(received))+previous if received is not None else None
    if previous<0 or ordered is None or received is None or total<=Fraction(str(ordered)):raise ValueError('Dòng này không có lượng nhận dư.')
    if not str(person).strip() or not str(reason).strip():raise ValueError('Nhập người xác nhận và lý do nhận dư.')
    old=entry.get('overreceipt_approval') or {}
    event=dict(id=uuid.uuid4().hex,time=datetime.now().astimezone().isoformat(),
        person=person.strip(),reason=reason.strip(),ordered=exact_text(ordered),received=exact_text(received),
        previous=exact_text(previous),excess=exact_text(total-Fraction(str(ordered))),status='pending_pr',signature=signature(row,pr,delivery,entry,ordered,received,previous))
    return dict(event,history=[*old.get('history',[]),event])


def effective(row,pr,delivery,entry,ordered,received):
    rule=(entry or {}).get('overreceipt_approval')
    if not rule:return None
    if ordered is None or received is None:raise ValueError('Chưa xác định lượng để kiểm tra duyệt nhận dư.')
    if rule.get('signature')!=signature(row,pr,delivery,entry,ordered,received,rule.get('previous','0')):
        raise ValueError('Duyệt nhận dư đã cũ; xác nhận lại sau khi lượng/PR/phiếu đổi.')
    return rule


def permits(payload,index,line,previous):
    """Only suppress the amount warning covered by a validated receipt decision."""
    from fractions import Fraction
    from pathlib import Path
    try:
        entry=(payload.get('conversions') or {}).get(str(index),(payload.get('conversions') or {}).get(index,{})) or {}
        rule=entry.get('overreceipt_approval')
        if not rule:return False
        if Fraction(rule.get('previous','0'))!=Fraction(previous):return False
        received=Fraction(payload['allocations'][str(index)])
        ordered=Fraction(line['ordered'])
        if received!=Fraction(rule['received']) or ordered!=Fraction(rule['ordered']):return False
        if Fraction(previous)+received-ordered!=Fraction(rule['excess']):return False
        comparison=json.loads(Path(payload['pr_link_path']).with_suffix('.comparison.json').read_text(encoding='utf-8'))
        item=comparison['pr_items'][int(index)]
        source=payload['allocation_rows'][str(index)]
        delivery=dict(payload['source_rows'])[int(source)]
        return bool(effective(source,item,delivery,entry,ordered,received))
    except (OSError,ValueError,TypeError,KeyError,IndexError):return False
