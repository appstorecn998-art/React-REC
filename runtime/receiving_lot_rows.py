"""Explicit same-product lot lines grouped only for PR comparison totals."""
import re
from datetime import datetime

from receiving_review import normalized


LOT_DATES = re.compile(
    r"^(?P<name>.+?)\s+Note:\s*(?P<date1>\d{2}/\d{2}/\d{4})"
    r"\s*_\s*(?P<date2>\d{2}/\d{2}/\d{4})\s*$",
    re.DOTALL | re.IGNORECASE,
)


def product_name(value):
    """Ignore a trailing lot note only when it consists of two valid dates."""
    if not isinstance(value, str):
        return ''
    note = LOT_DATES.fullmatch(value)
    if note:
        try:
            for key in ('date1', 'date2'):
                datetime.strptime(note[key], '%d/%m/%Y')
        except ValueError:
            return value.strip()
        return note['name'].strip()
    return value.strip()


def grouped(rows,links,conversions):
    from decimal import Decimal
    values=dict(rows);removed=set();replacements={};used=set()
    for p,primary in links.items():
        entry=(conversions or {}).get(p,(conversions or {}).get(str(p),{})) or {}
        selected=entry.get('lot_rows')
        if not selected:continue
        if primary!=selected[0] or len(selected)!=len(set(selected)) or len(selected)<2:raise ValueError('Nhóm dòng/lô đã đổi; ghép lại.')
        if any(r not in values or r in used for r in selected):raise ValueError('Dòng/lô bị thiếu hoặc gán lặp.')
        if any(r in links.values() for r in selected[1:]):raise ValueError('Dòng/lô đã gán vào món PR khác.')
        base=values[primary];code=str(base.get('Mã vật tư') or '')
        if not code or normalized(code)=='chua co ma':raise ValueError('Các dòng/lô cần có cùng mã hàng đã xác định.')
        source_name=product_name(base.get('Tên hàng trên phiếu (Ảnh)'))
        if not isinstance(source_name,str) or not source_name.strip():raise ValueError('Tên hàng trên phiếu chưa rõ; không gán nhiều dòng vào cùng món PR.')
        for r in selected:
            v=values[r]
            if product_name(v.get('Tên hàng trên phiếu (Ảnh)'))!=source_name:raise ValueError('Tên hoặc quy cách hàng khác nhau. Chọn lại các dòng cùng mặt hàng.')
            if any(str(v.get(k) or '')!=str(base.get(k) or '') for k in ('Mã vật tư','Đơn vị tính','Đơn vị trên phiếu','Đơn giá','Nhà cung cấp')):raise ValueError('Chỉ ghép nhiều lô khi cùng mã, ĐVT, đơn giá và NCC.')
        result=dict(base)
        for key in ('Số lượng','Thực nhận'):
            parts=[values[r].get(key) for r in selected]
            result[key]=float(sum(Decimal(str(v)) for v in parts)) if all(isinstance(v,(int,float)) and not isinstance(v,bool) and v>=0 for v in parts) else None
        result['Các dòng/lô đã ghép']=selected
        replacements[primary]=result;removed.update(selected[1:]);used.update(selected)
    return [(r,replacements.get(r,v)) for r,v in rows if r not in removed]
