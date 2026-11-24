"""Explicit per-comparison conversion; never a global unit synonym table."""
from decimal import Decimal,InvalidOperation
from fractions import Fraction
import hashlib,json
from receiving_review import normalized

def source_delivery(delivery):
    value=dict(delivery)
    if value.get('Đơn vị trên phiếu'):value['Đơn vị tính']=value['Đơn vị trên phiếu']
    return value

def scope(row,pr,delivery):
    delivery=source_delivery(delivery)
    fields=[row,pr.get('item_name'),pr.get('unit'),pr.get('specification'),
            delivery.get('Tên hàng trên phiếu (Ảnh)'),delivery.get('Mã vật tư'),delivery.get('Đơn vị tính')]
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,default=str).encode()).hexdigest()

def positive(value):
    try:factor=Fraction(str(value).strip().replace(',','.').replace(' ',''))
    except (ValueError,ZeroDivisionError,OverflowError):raise ValueError('Nhập số hoặc phân số, ví dụ 24, 0,05 hoặc 1/20.')
    if not 0<factor<=1000000:
        raise ValueError('Hệ số quy đổi phải lớn hơn 0 và không vượt quá một triệu.')
    return factor

def exact_text(value):
    value=Fraction(value);den=value.denominator
    for divisor in (2,5):
        while den%divisor==0:den//=divisor
    if den!=1:return str(value)
    text=format(Decimal(value.numerator)/Decimal(value.denominator),'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text

def converted(value,factor,inverse=False):
    value=Fraction(str(value))/factor if inverse else Fraction(str(value))*factor
    return Decimal(value.numerator)/Decimal(value.denominator)

def conversion(row,pr,delivery,value,reason):
    delivery=source_delivery(delivery)
    factor=positive(value)
    if not str(reason).strip():raise ValueError('Ghi rõ căn cứ: quy cách trên phiếu hoặc xác nhận đã kiểm tra.')
    missing=[]
    if not normalized(delivery.get('Đơn vị tính')):missing.append('ĐVT giao trên phiếu đang trống. Vào Phiếu giao → Sửa dòng, bổ sung đơn vị đúng trên ảnh.')
    if not normalized(pr.get('unit')):missing.append('ĐVT trên PR đang trống. Kiểm tra và bổ sung đơn vị của dòng PR.')
    if missing:raise ValueError('Chưa thể quy đổi: '+ ' '.join(missing))
    return {'row':row,'scope':scope(row,pr,delivery),'factor':exact_text(factor),'reason':str(reason).strip(),
            'pr_unit':pr['unit'],'delivery_unit':delivery['Đơn vị tính']}

def factor_for(conversions,index,row,pr,delivery):
    delivery=source_delivery(delivery)
    default=(Fraction(1),'') if normalized(pr.get('unit')) and normalized(pr.get('unit'))==normalized(delivery.get('Đơn vị tính')) else (None,'')
    rule=(conversions or {}).get(index,(conversions or {}).get(str(index)))
    if not isinstance(rule,dict) or (not rule.get('factor') and not rule.get('receipt_correction')):
        from receiving_spec_memory import remembered_conversion
        remembered=remembered_conversion(row,pr,delivery)
        if remembered:rule=remembered
    if not isinstance(rule,dict) or rule.get('scope')!=scope(row,pr,delivery) or rule.get('row')!=row:return default
    if rule.get('receipt_correction') and not rule.get('factor'):return default
    factor=positive(rule.get('factor'))
    if not rule.get('reason'):return None,''
    return factor,f"Quy đổi đã xác nhận: 1 {rule['delivery_unit']} = {exact_text(factor)} {rule['pr_unit']} · {rule['reason']}"

def approved_conversion(rules,supplier,row,pr,delivery):
    for rule in rules.get('unit_conversions',[]):
        tests=[(supplier,rule.get('supplier_name')),(pr.get('item_name'),rule.get('pr_item_name')),
               (delivery.get('Tên hàng trên phiếu (Ảnh)'),rule.get('delivery_item_name')),
               (pr.get('unit'),rule.get('pr_unit')),(delivery.get('Đơn vị tính'),rule.get('delivery_unit'))]
        if all(normalized(a) and normalized(a)==normalized(b) for a,b in tests) and str(delivery.get('Mã vật tư'))==str(rule.get('catalog_code')):
            result=conversion(row,pr,delivery,rule['factor'],rule['basis']);result['rule_source']='NhaCungCap.json';return result
    return None
