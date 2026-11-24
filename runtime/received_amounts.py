"""Cột tiền của báo cáo nhiều phiếu tính từ số thực nhận, giữ giá trị cũ riêng."""
from copy import copy
import os
from pathlib import Path
import tempfile

from openpyxl import load_workbook
from openpyxl.styles import Alignment,Font,PatternFill
from openpyxl.utils import get_column_letter

ORIGINAL_AMOUNT_HEADER='Thành tiền gốc (trước công thức)'
DELIVERED_AMOUNT_HEADER='Thành tiền trên phiếu'
DELIVERED_TOTAL_HEADER='Tổng tiền trên phiếu (Số lượng × Đơn giá)'


def apply_delivered_total(sheet):
    headers={str(c.value or '').strip():c.column for c in sheet[1]}
    if DELIVERED_AMOUNT_HEADER not in headers:
        raise ValueError(f'Sheet {sheet.title} chưa có cột {DELIVERED_AMOUNT_HEADER}.')
    changed=False
    column=headers.get(DELIVERED_TOTAL_HEADER)
    if column is None:
        column=sheet.max_column+1
        cell=sheet.cell(1,column,DELIVERED_TOTAL_HEADER)
        cell._style=copy(sheet.cell(1,headers[DELIVERED_AMOUNT_HEADER])._style)
        cell.alignment=Alignment(wrap_text=True,vertical='top')
        sheet.column_dimensions[get_column_letter(column)].width=40
        changed=True
    last=max((r for r in range(2,sheet.max_row+1)
              if sheet.cell(r,headers['Tên hàng trên phiếu (Ảnh)']).value),default=1)
    # Tổng chỉ nằm hàng 2; xóa tổng trang cũ được nối xuống khi gộp sheet.
    for r in range(3,sheet.max_row+1):
        if sheet.cell(r,column).value is not None:
            sheet.cell(r,column).value=None
            changed=True
    if last>1:
        amount=get_column_letter(headers[DELIVERED_AMOUNT_HEADER])
        name=get_column_letter(headers['Tên hàng trên phiếu (Ảnh)'])
        values=f'{amount}2:{amount}{last}'
        names=f'{name}2:{name}{last}'
        formula=f'=IF(COUNT({values})<>COUNTA({names}),"CHƯA ĐỦ DỮ LIỆU",SUM({values}))'
        cell=sheet.cell(2,column)
        if cell.value!=formula or cell.data_type!='f':
            cell.value=formula
            cell.font=Font(name='Calibri',size=12,bold=True,color='17365D')
            cell.fill=PatternFill('solid',fgColor='E2F0D9')
            cell.number_format='#,##0.##'
            cell.alignment=Alignment(wrap_text=True,vertical='top')
            changed=True
    if changed:sheet.auto_filter.ref=sheet.dimensions
    return changed


def apply_received_amounts(sheet):
    headers={str(cell.value or '').strip():cell.column for cell in sheet[1]}
    required={'Tên hàng trên phiếu (Ảnh)','Số lượng','Thực nhận','Đơn giá','Thành tiền'}
    if not required<=headers.keys():raise ValueError(f'Sheet {sheet.title} thiếu cột để tính tiền thực nhận.')
    changed=False
    original=headers.get(ORIGINAL_AMOUNT_HEADER)
    if original is None:
        original=sheet.max_column+1
        cell=sheet.cell(1,original,ORIGINAL_AMOUNT_HEADER)
        cell._style=copy(sheet.cell(1,headers['Thành tiền'])._style)
        cell.alignment=Alignment(wrap_text=True,vertical='top')
        sheet.column_dimensions[get_column_letter(original)].width=36
        changed=True
        new_original=True
    else:new_original=False
    delivered=headers.get(DELIVERED_AMOUNT_HEADER)
    if delivered is None:
        delivered=sheet.max_column+1
        cell=sheet.cell(1,delivered,DELIVERED_AMOUNT_HEADER)
        cell._style=copy(sheet.cell(1,headers['Thành tiền'])._style)
        cell.alignment=Alignment(wrap_text=True,vertical='top')
        sheet.column_dimensions[get_column_letter(delivered)].width=32
        changed=True
    quantity=get_column_letter(headers['Số lượng'])
    received=get_column_letter(headers['Thực nhận'])
    price=get_column_letter(headers['Đơn giá'])
    for row in range(2,sheet.max_row+1):
        if not sheet.cell(row,headers['Tên hàng trên phiếu (Ảnh)']).value:continue
        amount=sheet.cell(row,headers['Thành tiền'])
        formula=f'=IF(COUNT({received}{row},{price}{row})=2,{received}{row}*{price}{row},"CHƯA RÕ")'
        if new_original or (sheet.cell(row,original).value is None and amount.value!=formula):
            old=sheet.cell(row,original)
            old.value=amount.value
            old.data_type=amount.data_type
            old._style=copy(amount._style)
            # Không gọi công thức cũ là số OCR; giữ nguyên nó để truy vết.
        if amount.data_type!='f':
            amount.value=formula
            amount.number_format='#,##0.##'
            changed=True
        printed=sheet.cell(row,delivered)
        delivered_formula=f'=IF(COUNT({quantity}{row},{price}{row})=2,{quantity}{row}*{price}{row},"CHƯA RÕ")'
        if printed.value!=delivered_formula or printed.data_type!='f':
            printed.value=delivered_formula
            printed.number_format='#,##0.##'
            changed=True
    changed=apply_delivered_total(sheet) or changed
    if changed:
        sheet.auto_filter.ref=sheet.dimensions
    return changed


def upgrade_received_amounts(report):
    import AutoWatcher as aw
    report=Path(report)
    if not report.is_file():return 0
    digest=aw.delivery_report_digest(report)
    workbook=load_workbook(report)
    temporary=None
    try:
        updated=0
        for sheet in workbook:
            if apply_received_amounts(sheet):
                if 'Tổng tiền phiếu (cộng Thành tiền)' not in [cell.value for cell in sheet[1]]:
                    aw.add_invoice_total(sheet)
                updated+=1
        if not updated:return 0
        workbook.calculation.calcMode='auto'
        workbook.calculation.fullCalcOnLoad=True
        workbook.calculation.forceFullCalc=True
        with tempfile.NamedTemporaryFile(dir=report.parent,suffix='.xlsx',delete=False) as handle:temporary=Path(handle.name)
        workbook.save(temporary);workbook.close()
        if aw.delivery_report_digest(report)!=digest:raise ValueError('TongHop vừa thay đổi; chưa ghi đè. Đóng Excel/WPS rồi thử lại.')
        backup=report.parent/'.autowatcher-backups'/('received-amounts-'+aw.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))/report.name
        aw.atomic_copy_file(report,backup)
        os.replace(temporary,report)
        print(f'Đã cập nhật {updated} sheet: tiền thực nhận và tiền trên phiếu (Số lượng × Đơn giá). Backup: {backup}')
        return updated
    finally:
        workbook.close()
        if temporary is not None:temporary.unlink(missing_ok=True)
