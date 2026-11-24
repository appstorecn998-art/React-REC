"""Explicit actual receipt evidence; never rewrite a vendor or PR quantity."""
import hashlib,json
from fractions import Fraction
from receiving_units import scope,positive,exact_text
from receiving_review import normalized

def signature(row,pr,delivery):
    return hashlib.sha256(json.dumps([scope(row,pr,delivery),pr,delivery.get('Nhà cung cấp'),*[str(delivery.get(k,'')) for k in ['Số lượng','Thực nhận','Đơn giá','Thành tiền gốc (trước công thức)','SHA-256 ảnh nguồn']]],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def correction(row,pr,delivery,count,weight,reason):
    packs=positive(count);grams=positive(weight)
    if packs.denominator!=1:raise ValueError('Số gói thực nhận phải là số nguyên.')
    if not str(reason).strip():raise ValueError('Ghi căn cứ kiểm đếm và xác nhận NCC ghi sai.')
    unit=normalized(pr.get('unit'))
    if unit not in {'kg','g','gr'}:raise ValueError('Chỉ xác nhận khối lượng khi PR dùng Kg hoặc G; kiểm lại đơn vị PR.')
    received=packs*grams/(1000 if unit=='kg' else 1)
    return dict(signature=signature(row,pr,delivery),row=row,packs=exact_text(packs),grams=exact_text(grams),received=exact_text(received),unit=pr['unit'],reason=str(reason).strip())

def actual(conversions,index,row,pr,delivery):
    entry=(conversions or {}).get(index,(conversions or {}).get(str(index),{}))
    saved=entry.get('receipt_correction') if isinstance(entry,dict) else None
    if not saved:return None
    expected=correction(row,pr,delivery,saved.get('packs'),saved.get('grams'),saved.get('reason'))
    from receiving_evidence import strip
    if strip(saved)!=expected:raise ValueError('Xác nhận lượng thực nhận đã cũ; nguồn/PR đã đổi. Xác nhận lại trước khi ghi sổ.')
    return saved
