"""Mẫu phiếu một sheet, ánh xạ theo tên cột để không lệch sau khi thêm cột."""
from copy import copy
from datetime import datetime, date
from math import ceil
import re
import unicodedata

from openpyxl.utils import get_column_letter
from supplier_rules import normalize_name

LAYOUT_VERSION = "flat-supplier-warehouse-v6-aligned"
VIETNAMESE_DATE_FORMAT = "[$-042A]dd/mm/yyyy"
DELIVERY_DATE_PROMPT = """
Đọc ngày giao hàng trên CHÍNH phiếu giao vào delivery_date, dạng YYYY-MM-DD.
Không dùng ngày yêu cầu trên PR, ngày hiện tại, ngày gửi ảnh hoặc ngày ký khác.
Nếu không đọc đủ ngày/tháng/năm, để delivery_date="", không đoán phần còn thiếu.
"""
HEADERS = ["STT", "Mã nhà cung cấp", "Tên nhà cung cấp", "Ngày giao hàng", "Mã hàng",
           "Tên mặt hàng", "Đvt", "Mã kho", "Số lượng", "Giá", "Tiền hàng", "Tk nợ",
           "Vụ việc", "Bộ phận", "Lsx", "Sản phẩm", "Hợp đồng", "Phí", "Khế ước"]


def vietnamese_item_name(value):
    """Bỏ dấu nhưng giữ nguyên tên/quy cách; dấu / không chứng minh ranh giới ngôn ngữ."""
    raw=str(value or '').strip()
    raw=raw.replace('đ','d').replace('Đ','D')
    return ''.join(c for c in unicodedata.normalize('NFD',raw) if unicodedata.category(c)!='Mn')


def parse_delivery_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Ngày giao hàng không hợp lệ: {raw}. Cần đủ ngày/tháng/năm trên phiếu.")


def columns(sheet):
    mapping = {}
    for cell in sheet[1]:
        key = normalize_name(str(cell.value or ""))
        if key:
            if key in mapping:
                raise ValueError(f"Mẫu có cột trùng: {cell.value}")
            mapping[key] = cell.column
    required = {normalize_name(h) for h in [*HEADERS[:11], "Bộ phận"]}
    missing = required - mapping.keys()
    if missing or "thuc nhan" in mapping:
        raise ValueError("Mẫu phiếu cần có STT, Mã/Tên NCC, Ngày giao hàng, Số lượng, Giá, Tiền hàng "
                         "và bỏ cột Thực nhận. Lưu mẫu mới rồi chạy lại.")
    return mapping


def fill_flat_delivery(workbook, rows):
    # calcPr is optional in XLSX, including templates exported by other editors.
    # Both single and multi-invoice exporters set these flags after filling.
    if workbook.calculation is None:
        from openpyxl.workbook.properties import CalcProperties
        workbook.calculation=CalcProperties(calcMode='auto',fullCalcOnLoad=True,forceFullCalc=True)
    sheet = workbook.worksheets[0]
    mapping = columns(sheet)
    style_delivery(sheet, mapping)
    sheet.title = "1"
    for other in workbook.worksheets[1:]:
        workbook.remove(other)
    styles = [copy(sheet.cell(2, c)._style) for c in range(1, sheet.max_column + 1)]
    height = sheet.row_dimensions[2].height
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.value = None
    invoice_numbers = {}
    for row_number, item in enumerate(rows, 1):
        # Mỗi sheet TongHop đại diện cho một phiếu. Giữ nguyên số STT cho
        # toàn bộ dòng của phiếu đó, rồi mới tăng ở phiếu kế tiếp.
        invoice_key = item.get("invoice_key") or (
            normalize_name(item.get("supplier_name", "")),
            item.get("delivery_date"),
        )
        if invoice_key not in invoice_numbers:
            invoice_numbers[invoice_key] = len(invoice_numbers) + 1
        number = invoice_numbers[invoice_key]
        r = row_number + 1
        for c, style in enumerate(styles, 1):
            sheet.cell(r, c)._style = copy(style)
        sheet.row_dimensions[r].height = height
        values = {"STT": number, "Mã nhà cung cấp": item["supplier_code"],
                  "Tên nhà cung cấp": item["supplier_name"], "Ngày giao hàng": item["delivery_date"],
                  "Mã hàng": item["code"], "Tên mặt hàng": vietnamese_item_name(item["name"]), "Đvt": str(item["unit"] or "").strip().capitalize(),
                  "Số lượng": item["received"], "Giá": item["unit_price"],
                  "Mã kho": item.get("warehouse_code", ""), "Bộ phận": item.get("department", "")}
        if "ten kho" in mapping:
            values["Tên kho"] = item.get("warehouse_name", "")
        for header, value in values.items():
            cell = sheet.cell(r, mapping[normalize_name(header)])
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
        for header in ("Tên nhà cung cấp", "Tên mặt hàng"):
            c = mapping[normalize_name(header)]
            cell = sheet.cell(r, c)
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            cell.alignment = alignment
            width = sheet.column_dimensions[get_column_letter(c)].width or 13
            lines = max(1, ceil(len(str(cell.value or "")) / max(1, width - 2)))
            sheet.row_dimensions[r].height = max(sheet.row_dimensions[r].height or 15, lines * 16 + 8)
        for header in ("Mã nhà cung cấp", "Mã hàng", "Mã kho"):
            sheet.cell(r, mapping[normalize_name(header)]).number_format = "@"
        sheet.cell(r, mapping["stt"]).number_format = "00"
        sheet.cell(r, mapping["ngay giao hang"]).number_format = VIETNAMESE_DATE_FORMAT
        sheet.cell(r,mapping["so luong"]).number_format=quantity_format(item["received"])
        from decimal import Decimal
        sheet.cell(r,mapping['gia']).number_format=quantity_format(item['unit_price'])
        amount=(Decimal(str(item['received']))*Decimal(str(item['unit_price']))
                if item['received'] is not None and item['unit_price'] is not None else None)
        sheet.cell(r,mapping['tien hang']).number_format=quantity_format(amount)
        qty = get_column_letter(mapping["so luong"])
        price = get_column_letter(mapping["gia"])
        sheet.cell(r, mapping["tien hang"]).value = f"={qty}{r}*{price}{r}"
    if sheet.auto_filter.ref:
        sheet.auto_filter.ref = f"A1:{get_column_letter(sheet.max_column)}{max(1,len(rows)+1)}"
    return sheet


def style_delivery(sheet,mapping):
    """Consistent alignment for both existing templates and newly exported rows."""
    from openpyxl.styles import Alignment,Font,PatternFill,Border,Side
    widths={'stt':7,'ma nha cung cap':16,'ten nha cung cap':32,'ngay giao hang':16,'ma hang':16,'ten mat hang':60,'dvt':10,'ma kho':12,'so luong':14,'gia':16,'tien hang':19,'tk no':12,'vu viec':16,'bo phan':14}
    text_columns={'ten nha cung cap','ten mat hang','ten kho'}
    numeric_columns={'so luong','gia','tien hang'}
    edge=Side(style='thin',color='D8E0E9')
    for name,col in mapping.items():
        # Widths come from the user template; preserve later custom sizing.
        if not sheet.column_dimensions[get_column_letter(col)].width:
            sheet.column_dimensions[get_column_letter(col)].width=widths.get(name,16)
        header=sheet.cell(1,col)  # Keep the user's header font and fill from the template.
        header.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
        header.border=Border(left=edge,right=edge,top=edge,bottom=edge)
        cell=sheet.cell(2,col)
        cell.alignment=Alignment(horizontal='left' if name in text_columns else 'right' if name in numeric_columns else 'center',vertical='center',wrap_text=name in text_columns)
        cell.border=Border(left=edge,right=edge,top=edge,bottom=edge)
    sheet.row_dimensions[1].height=36;sheet.row_dimensions[2].height=30
    sheet.freeze_panes=None


def quantity_format(value):
    from decimal import Decimal,InvalidOperation
    try:
        quantity=Decimal(str(value))
        if not quantity.is_finite():return 'General'
        places=max(0,-quantity.normalize().as_tuple().exponent)
        return '#,##0'+('.'+'0'*places if places else '')
    except (InvalidOperation,TypeError,ValueError):return 'General'
