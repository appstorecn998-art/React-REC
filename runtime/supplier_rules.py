"""Quy tắc do người dùng xác nhận, tách khỏi các đề xuất của AI."""
import json
from pathlib import Path
import re
import unicodedata


def normalize_name(value):
    folded = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return " ".join(re.findall(r"[a-z]+|\d+", folded))


def read_rules(path, catalog, catalog_groups):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return validate_rules(data, catalog, catalog_groups)


def validate_rules(data, catalog, catalog_groups):
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("suppliers"), list)):
        raise ValueError("NhaCungCap.json cần version=1 và danh sách suppliers.")
    known_groups = {group[0] for group in catalog_groups.values() if group[0]}
    seen_aliases, seen_ids = set(), set()
    for supplier in data["suppliers"]:
        if not isinstance(supplier, dict):
            raise ValueError("Mỗi nhà cung cấp phải là một đối tượng JSON.")
        for field in ["id", "name"]:
            if not isinstance(supplier.get(field), str) or not supplier[field].strip():
                raise ValueError(f"Nhà cung cấp thiếu {field}.")
        if supplier["id"] in seen_ids:
            raise ValueError("Trùng id nhà cung cấp trong NhaCungCap.json.")
        seen_ids.add(supplier["id"])
        aliases, groups, items = (supplier.get(key) for key in
                                 ["aliases", "allowed_group_ids", "confirmed_items"])
        if (not isinstance(aliases, list) or not aliases
                or any(not isinstance(alias, str) or not normalize_name(alias) for alias in aliases)):
            raise ValueError(f"Nhà cung cấp {supplier['name']} cần aliases là danh sách tên.")
        normalized = {normalize_name(alias) for alias in aliases + [supplier["name"]]}
        if normalized & seen_aliases:
            raise ValueError("Một tên nhà cung cấp đang được gán cho nhiều nhà cung cấp.")
        seen_aliases.update(normalized)
        policy = supplier.get("group_policy", "restricted")
        if policy not in {"restricted", "by_item", "outside_catalog"}:
            raise ValueError("group_policy không hợp lệ.")
        if (not isinstance(groups, list) or (policy == "restricted" and not groups)
                or (policy != "restricted" and groups)
                or any(not isinstance(group, str) or group not in known_groups for group in groups)):
            raise ValueError(f"Nhóm của {supplier['name']} không tồn tại trong DanhMucGoc.")
        if not isinstance(items, list):
            raise ValueError("confirmed_items phải là danh sách (có thể rỗng).")
        seen_items = set()
        for item in items:
            if (not isinstance(item, dict) or not isinstance(item.get("invoice_name"), str)
                    or not normalize_name(item["invoice_name"])
                    or not isinstance(item.get("catalog_code"), str)):
                raise ValueError("Quy đổi tên hàng thiếu invoice_name hoặc catalog_code.")
            alias, code = normalize_name(item["invoice_name"]), item["catalog_code"]
            if alias in seen_items:
                raise ValueError(f"Trùng tên hàng đã xác nhận của {supplier['name']}.")
            seen_items.add(alias)
            if code not in catalog:
                raise ValueError(f"Mã xác nhận {code} không tồn tại trong DanhMucGoc.")
    warehouse_rules = data.get('warehouse_rules', [])
    if not isinstance(warehouse_rules, list):
        raise ValueError('warehouse_rules phải là danh sách.')
    for rule in warehouse_rules:
        if (not isinstance(rule, dict) or ('supplier_id' in rule and rule['supplier_id'] not in seen_ids)
                or (not rule.get('requester_based') and (not isinstance(rule.get('warehouse_code'), str) or not rule['warehouse_code'].isdigit()))
                or not isinstance(rule.get('item_terms'), list) or not rule['item_terms']
                or not isinstance(rule.get('exclude_terms', []), list)
                or any(not isinstance(term, str) or not normalize_name(term)
                       for term in rule['item_terms'] + rule.get('exclude_terms', []))):
            raise ValueError('Quy tắc NCC/mặt hàng/kho không hợp lệ.')
    routing = data.get('requester_warehouses', {})
    if (not isinstance(routing, dict) or any(not isinstance(name, str) or not normalize_name(name)
            or not isinstance(code, str) or not code.isdigit() for name, code in routing.items())
            or len({normalize_name(name) for name in routing}) != len(routing)):
        raise ValueError('Quy tắc người đề nghị/kho không hợp lệ.')
    return data


def find_supplier(name, rules):
    normalized = normalize_name(name)
    if not normalized:
        return None
    for supplier in rules["suppliers"]:
        aliases = supplier["aliases"] + [supplier["name"]]
        if normalized in {normalize_name(alias) for alias in aliases}:
            return supplier
    return None


def validate_extraction(extracted, catalog_groups):
    if (not isinstance(extracted, dict) or not isinstance(extracted.get("supplier_name"), str)
            or not isinstance(extracted.get("items"), list) or not extracted["items"]):
        raise ValueError("Không đọc được nhà cung cấp/danh sách tên hàng hợp lệ từ ảnh.")
    known_groups = {group[0] for group in catalog_groups.values()} | {""}
    for item in extracted["items"]:
        if (not isinstance(item, dict) or not isinstance(item.get("invoice_name"), str)
                or not item["invoice_name"].strip() or not isinstance(item.get("group_id"), str)
                or item["group_id"] not in known_groups):
            raise ValueError("Dòng đọc từ ảnh thiếu tên hàng hoặc mã nhóm không hợp lệ.")


def build_plans(extracted, catalog, catalog_groups, rules):
    validate_extraction(extracted, catalog_groups)
    supplier = find_supplier(extracted["supplier_name"], rules)
    confirmed = {normalize_name(item["invoice_name"]): item["catalog_code"]
                 for item in supplier["confirmed_items"]} if supplier else {}
    exact_names = {}
    for code, (label, _) in catalog.items():
        exact_names.setdefault(normalize_name(label), []).append(code)
    # Exact printed bilingual component: drop unit suffix only, never sizes/brands.
    component_names={}
    for code,(label,unit) in catalog.items():
        components=str(label).split('/')
        for part in components:
            value=normalize_name(part)
            if value in {'kg','g','gr','pcs','pc','cai','chai','pack','bag',normalize_name(unit)}:continue
            component_names.setdefault(value,set()).add(code)
            # Whole produce versus baby/peeled/sliced remains distinct.
            if len(components)>1 and value.endswith(' nguyen'):
                component_names.setdefault(value[:-7].strip(),set()).add(code)
    plans = []
    for item in extracted["items"]:
        name, suggested_group = item["invoice_name"], item["group_id"]
        exact_codes = exact_names.get(normalize_name(name), [])
        matched_code = exact_codes[0] if len(exact_codes) == 1 else ''
        if not matched_code:
            parts=[normalize_name(v) for v in str(name).split('/')]
            candidates=set()
            for part in parts:candidates.update(component_names.get(part,set()))
            if len(candidates)==1:
                candidate=next(iter(candidates))
                # Honor explicit specifications in the original full name.
                from catalog_recall import product_mismatch
                if not product_mismatch(name,catalog[candidate][0]):matched_code=candidate
        approved_code = '' if matched_code else confirmed.get(normalize_name(name), "")
        note = ""
        if matched_code:
            suggested = {catalog_groups[matched_code][0]}
            note = 'Tên khớp duy nhất trong DanhMucGoc; không dựa vào NCC.'
        elif approved_code:
            suggested = {catalog_groups[approved_code][0]}
            note = f"Quy đổi đã được người dùng xác nhận cho {supplier['name']}."
        else:
            suggested = {suggested_group} if suggested_group else set()
            note = "Đối chiếu DanhMucGoc trước; NCC/nhóm OCR chỉ là ngữ cảnh."
            if not supplier:
                note += " NCC chưa có quy tắc xác nhận." if extracted["supplier_name"] else " Chưa đọc rõ NCC."
        context = {"supplier_name": supplier['name'] if supplier else extracted['supplier_name'],
                   "suggested_group_id": suggested_group,
                   "supplier_group_ids": supplier.get('allowed_group_ids', []) if supplier else [],
                   "supply_description": supplier.get('supply_description', '') if supplier else ''}
        # Supplier classification cannot remove a valid catalog SKU (05/11/2026).
        plans.append({"invoice_name": name, "catalog": catalog, "group_ids": suggested,
                      "approved_code": approved_code, "matched_code": matched_code,
                      "conflict": False, "note": note,
                      "context": context,
                      "supplier_name": supplier["name"] if supplier else extracted["supplier_name"],
                      "supplier_known": supplier is not None})
    return plans
