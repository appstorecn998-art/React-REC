"""Đối chiếu danh tính NCC; không suy diễn nhóm hàng hay tự xác nhận mã hàng."""
import re

from openpyxl import load_workbook

from supplier_rules import normalize_name


def load_supplier_directory(path, *, include_tax=False):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = [s for s in workbook if normalize_name(s.title).replace(" ", "") == "danhmucncc"]
        if len(sheets) != 1:
            raise ValueError("DanhMuc.xlsm cần sheet DanhMucNCC để đối chiếu nhà cung cấp.")
        sheet = sheets[0]
        headers = [normalize_name(str(c.value or "")) for c in next(sheet.iter_rows(min_row=1, max_row=1))]
        try:
            code_index, name_index = headers.index("ma nha cung cap"), headers.index("ten nha cung cap")
        except ValueError as exc:
            raise ValueError("DanhMucNCC cần cột Mã nhà cung cấp và Tên nhà cung cấp.") from exc
        result = {}
        taxes = {}
        tax_index = headers.index("ma so thue") if "ma so thue" in headers else None
        for row in sheet.iter_rows(min_row=2):
            cell = row[code_index]
            code = str(cell.value or "").strip()
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                code = str(int(cell.value)) if float(cell.value).is_integer() else code
                if re.fullmatch(r"0+", cell.number_format):
                    code = code.zfill(len(cell.number_format))
            name = str(row[name_index].value or "").strip()
            if not code and not name:
                continue
            if not code or not name or (code in result and result[code] != name):
                raise ValueError("DanhMucNCC có dòng thiếu mã/tên hoặc cùng mã nhưng khác tên.")
            result[code] = name
            if include_tax and tax_index is not None:
                tax_cell = row[tax_index]
                value = tax_cell.value
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if not float(value).is_integer():
                        continue
                    value = str(int(value))
                    if re.fullmatch(r"0+", tax_cell.number_format):
                        value = value.zfill(len(tax_cell.number_format))
                value = str(value or '').strip()
                if value and code in taxes and taxes[code] != value:
                    raise ValueError("DanhMucNCC có mã nhà cung cấp gắn với nhiều mã số thuế.")
                if value:
                    taxes[code] = value
        if not result:
            raise ValueError("DanhMucNCC chưa có nhà cung cấp hợp lệ.")
        return (result, taxes) if include_tax else result
    finally:
        workbook.close()


def supplier_aliases(rules, directory):
    aliases = {}
    entries = rules.get("supplier_aliases", [])
    if not isinstance(entries, list):
        raise ValueError("supplier_aliases phải là danh sách quy đổi NCC đã xác nhận.")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("supplier_aliases phải chứa tên trên phiếu và mã NCC đã xác nhận.")
        name, code = entry.get("invoice_name"), entry.get("supplier_code")
        if not isinstance(name, str) or not normalize_name(name) or not isinstance(code, str) or code not in directory:
            raise ValueError("Quy đổi tên NCC đã xác nhận thiếu tên hoặc mã không có trong DanhMucNCC.")
        key = normalize_name(name)
        if key in aliases and aliases[key] != code:
            raise ValueError("Một tên NCC đang được xác nhận cho nhiều mã.")
        aliases[key] = code
    return aliases


def supplier_core(name):
    core = normalize_name(name)
    for phrase in ("cong ty", "co phan", "san xuat", "thuong mai", "dich vu", "mot thanh vien",
                   "tnhh", "tmdv", "mtv", "tm", "cp"):
        core = re.sub(r"\b" + phrase + r"\b", " ", core)
    return " ".join(core.split())


def resolve_supplier(name, directory, aliases):
    name = str(name or "").strip()
    normalized = normalize_name(name)
    if normalized in aliases:
        code = aliases[normalized]
        return code, directory[code]
    exact = [code for code, full_name in directory.items() if normalize_name(full_name) == normalized]
    if len(exact) == 1:
        return exact[0], directory[exact[0]]
    # Chỉ khớp toàn bộ tên sau bỏ cụm pháp lý, không chọn theo chuỗi con.
    core = supplier_core(name)
    if len(core.split()) >= 2:
        matches = [code for code, full_name in directory.items()
                   if supplier_core(full_name) == core]
        if len(matches) == 1:
            return matches[0], directory[matches[0]]
    return "", name if normalized not in {"", "chua ro"} else ""
