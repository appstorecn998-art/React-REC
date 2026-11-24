"""Read-only date-range receipt lookup using the existing REC matcher."""
from datetime import date
from zipfile import BadZipFile
import json
from receiving_service import snapshot
from receiving_preferences import nickname
from rec_receipt_search import matches


def linked_order_refs(report, sheet):
    """Recover PO/PR numbers saved by the existing PR comparison cache."""
    root = report.parent / '.receiving'
    for link in root.rglob('manual-pr-links/*.json') if root.exists() else ():
        if link.name.endswith('.comparison.json') or link.name.endswith('.comparison.review.json'):
            continue
        try:
            selected = json.loads(link.read_text(encoding='utf-8'))
            if selected.get('sheet') != sheet:
                continue
            comparison = link.with_name(link.stem + '.comparison.json')
            payload = json.loads(comparison.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            continue
        po_numbers = {str(item.get('pr_reference_id') or '').strip() for item in payload.get('pr_items', [])
                      if item.get('order_type') == 'po' and str(item.get('pr_reference_id') or '').strip()}
        pr_numbers = {str(item.get('related_pr_number') or '').strip() for item in payload.get('pr_items', [])
                      if str(item.get('related_pr_number') or '').strip()}
        if not pr_numbers:
            pr_numbers = {str(item.get('pr_reference_id') or '').strip() for item in payload.get('pr_items', [])
                          if item.get('order_type') != 'po' and str(item.get('pr_reference_id') or '').strip()}
        return sorted(po_numbers), sorted(pr_numbers)
    return [], []


def search(days, profile, start, end, query):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise ValueError('Chọn ngày bắt đầu và kết thúc hợp lệ.') from None
    if first > last or (last-first).days > 365:
        raise ValueError('Từ ngày phải trước hoặc bằng đến ngày, tối đa 366 ngày.')
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError('Từ khóa tối đa 200 ký tự.')
    results, errors = [], []
    for day, report in sorted(days.items(), reverse=True):
        if not start <= day <= end:
            continue
        try:
            version, sheets = snapshot(report)
            if version is None:raise ValueError("Báo cáo không còn tồn tại")
            for sheet, rows in sheets:
                if not rows:
                    continue
                supplier = ' / '.join(dict.fromkeys(str(v.get('Nhà cung cấp') or '').strip()
                                                   for _, v in rows if v.get('Nhà cung cấp'))) or 'NCC chưa rõ'
                label = nickname(profile, supplier) or supplier
                po_numbers = sorted({str(v.get('Số PO') or '').strip() for _, v in rows if str(v.get('Số PO') or '').strip()})
                pr_numbers = sorted({str(v.get('Số PR') or '').strip() for _, v in rows if str(v.get('Số PR') or '').strip()})
                linked_po, linked_pr = linked_order_refs(report, sheet)
                po_numbers = sorted(set(po_numbers) | set(linked_po))
                pr_numbers = sorted(set(pr_numbers) | set(linked_pr))
                references = {value.casefold() for value in po_numbers + pr_numbers}
                reference_terms = [term.casefold() for term in query.split()
                                   if term.upper().startswith(('PO', 'PR'))]
                if any(term not in references for term in reference_terms):
                    continue
                search_label = label + ' ' + ' '.join(po_numbers + pr_numbers)
                if matches(query, sheet, rows, search_label):
                    products = list(dict.fromkeys(str(v.get('Tên hàng trên phiếu (Ảnh)') or v.get('Tên chuẩn hệ thống') or '')
                                                  for _, v in rows))
                    results.append(dict(day=day, sheet=sheet, supplier=supplier, label=label,
                                        products=[v for v in products if v], count=len(rows), version=version,
                                        po_numbers=po_numbers, pr_numbers=pr_numbers))
        except Exception:
            # One unreadable workbook must not discard healthy days.
            errors.append(dict(day=day, message='Không đọc được báo cáo ngày này; kết quả chưa đầy đủ.'))
    return dict(items=results, errors=errors, start=start, end=end)
