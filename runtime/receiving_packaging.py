"""Explicit purchase approvals: original PR remains unchanged."""
import hashlib,json
from fractions import Fraction
from receiving_units import exact_text,positive


def identity(item,supplier,entry=None):
    fields={k:item.get(k) for k in ('item_name','catalog_code','specification','unit','quantity','unit_price')}
    if (entry or {}).get('pr_quantity'):
        from receiving_pr_quantity import effective as manual_ordered
        fields['effective_quantity']=str(manual_ordered(item,entry))
    return hashlib.sha256(json.dumps([supplier,fields],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def approval(item,supplier,pack_size,reason,entry=None):
    import AutoWatcher as aw
    from receiving_pr_quantity import effective as manual_ordered
    requested=manual_ordered(item,entry or {})
    if requested is None or requested<=0:raise ValueError('Lượng PR phải rõ và lớn hơn0.')
    if not str(supplier).strip() or supplier=='Chưa rõ':raise ValueError('Chưa rõ NCC.')
    if not str(reason).strip():raise ValueError('Ghi căn cứ đóng gói và lý do duyệt.')
    pack=positive(pack_size);quantity=Fraction(str(requested))
    count=-(-quantity//pack);approved=count*pack
    return dict(version=1,scope=identity(item,supplier,entry),supplier=supplier,pack_size=exact_text(pack),
                requested=exact_text(quantity),approved=exact_text(approved),reason=reason.strip())


def effective(item,entry,supplier=None):
    import AutoWatcher as aw
    from receiving_pr_quantity import effective as manual_ordered
    requested=manual_ordered(item,entry or {});rule=(entry or {}).get('purchase_approval')
    if not isinstance(rule,dict):return requested,None
    supplier=rule.get('supplier') if supplier is None else supplier
    if rule.get('scope')!=identity(item,supplier,entry):return requested,None
    try:
        verified=approval(item,supplier,rule['pack_size'],rule['reason'],entry)
        from receiving_evidence import strip
        if verified!=strip(rule):return requested,None
    except (ValueError,KeyError,TypeError):return requested,None
    from decimal import Decimal
    q=Fraction(rule['approved'])
    return Decimal(q.numerator)/Decimal(q.denominator),rule
