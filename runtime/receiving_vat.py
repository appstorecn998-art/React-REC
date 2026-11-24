"""Shared VAT conversion; original gross price remains auditable."""
from datetime import datetime

def convert_row(sheet,headers,row,vat_rate):
    from decimal import Decimal
    import json
    if vat_rate not in (0,8,10):raise ValueError('Chọn VAT 8%, 10% hoặc bỏ quy đổi VAT.')
    for field in ('Giá NCC gồm VAT gốc','Thuế suất VAT đã tách','Ghi nhận tách VAT'):
        if field not in headers:
            col=sheet.max_column+1;sheet.cell(1,col,field);headers[field]=col
    price_cell=sheet.cell(row,headers['Đơn giá'])
    raw=sheet.cell(row,headers['Giá NCC gồm VAT gốc']).value
    old_rate=sheet.cell(row,headers['Thuế suất VAT đã tách']).value
    gross=Decimal(str(raw if old_rate else price_cell.value))
    if not gross.is_finite() or gross<0:raise ValueError('Đơn giá NCC không hợp lệ.')
    if old_rate:
        computed=Decimal(str(raw))/(1+Decimal(str(old_rate))/100)
        if abs(Decimal(str(price_cell.value))-computed)>Decimal('0.000001'):raise ValueError('Đơn giá đã được sửa sau khi tách VAT; cần rà lại giá NCC gốc.')
    net=gross/(1+Decimal(vat_rate)/100)
    price_cell.value=float(net)
    sheet.cell(row,headers['Giá NCC gồm VAT gốc'],str(gross))
    sheet.cell(row,headers['Thuế suất VAT đã tách'],vat_rate)
    journal=sheet.cell(row,headers['Ghi nhận tách VAT'])
    events=json.loads(journal.value or '[]');events.append(dict(time=datetime.now().astimezone().isoformat(),rate=vat_rate,gross=str(gross),net=str(net)))
    journal.value=json.dumps(events,ensure_ascii=False);journal.data_type='s'
