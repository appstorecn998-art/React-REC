"""Check PO evidence against the current material and supplier directories."""
import re

from supplier_rules import normalize_name

SUPPLIER_PREFIX = re.compile(r'^\s*(\d{6,}(?:\s*-\s*\d{3})?)\s*-\s*(.+)$')


def audit(record, materials, suppliers):
    printed = str(record.get('supplier_on_po') or record.get('supplier') or '').strip()
    code = re.sub(r'\s+', '', str(record.get('supplier_code') or '').strip())
    match = SUPPLIER_PREFIX.fullmatch(printed)
    printed_name = match[2].strip() if match else printed
    if not code and match:
        code = re.sub(r'\s+', '', match[1])
    canonical = suppliers.get(code)
    warnings = []
    if not code:
        warnings.append('Chưa đọc được mã NCC trên PO.')
    elif not canonical:
        warnings.append(f'Mã NCC {code} chưa có trong DanhMucNCC. Tên trên PO · {printed_name}')
    elif normalize_name(printed_name) != normalize_name(canonical):
        warnings.append(f'Mã NCC {code} · PO ghi “{printed_name}”, DanhMucNCC ghi “{canonical}”.')
    for index, item in enumerate(record.get('items', []), 1):
        item_code = str(item.get('catalog_code') or '').strip()
        name = str(item.get('item_name') or '').strip()
        material = materials.get(item_code)
        if not material:
            message = f'Mã {item_code} chưa có trong DanhMucGoc' if item_code else 'Chưa đọc được mã hàng'
            warnings.append(f'Dòng {index} · {message} · {name}')
        elif normalize_name(name) != normalize_name(material[0]):
            warnings.append(f'Dòng {index} · Mã {item_code} · PO ghi “{name}”, DanhMucGoc ghi “{material[0]}”.')
    return dict(supplier_code=code, supplier_on_po=printed, supplier=canonical or printed, warnings=warnings)


def update_library(directory, keys, catalog_path):
    from AutoWatcher import load_catalog_data
    from receiving_pr_library import LOCK, load, atomic_json
    from supplier_directory import load_supplier_directory

    with LOCK:
        orders = load(directory)
        selected = [orders[key] for key in keys if orders.get(key, {}).get('order_type') == 'po']
        if not selected:
            return []
        materials, _ = load_catalog_data(catalog_path)
        suppliers = load_supplier_directory(catalog_path)
        warnings = []
        changed = False
        for record in selected:
            result = audit(record, materials, suppliers)
            changed |= any(record.get(key) != value for key, value in result.items())
            record.update(result)
            warnings.extend(f"{record['number']} · {message}" for message in result['warnings'])
        if changed:
            atomic_json(directory/'index.json', dict(version=1, orders=orders))
        return warnings
