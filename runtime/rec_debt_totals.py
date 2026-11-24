"""Debt totals from actual received quantities and stored prices, without guessing blanks."""
from decimal import Decimal,InvalidOperation

def amount(value):
    if value is None or isinstance(value,bool) or isinstance(value,str):return None
    try:
        n=Decimal(str(value));return n if n.is_finite() and n>=0 else None
    except InvalidOperation:return None

def summarize(data):
    totals={}
    for name,rows in data:
        for row,value in rows:
            supplier=str(value.get('Nhà cung cấp') or '').strip() or 'Chưa rõ NCC'
            entry=totals.setdefault(supplier,dict(total=Decimal(0),missing=0,rows=0,receipts=set()))
            entry['rows']+=1;entry['receipts'].add(name)
            qty,price=amount(value.get('Thực nhận')),amount(value.get('Đơn giá'))
            if qty is None or price is None:entry['missing']+=1
            else:entry['total']+=qty*price
    return totals

def money(value):return format(value,',.2f').rstrip('0').rstrip('.')+' đ'

def label(entry):
    if entry['missing']:return 'Chưa đủ dữ liệu · '+money(entry['total'])+' đã biết · thiếu '+str(entry['missing'])+' dòng'
    return money(entry['total'])
