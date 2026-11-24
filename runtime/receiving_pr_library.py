"""Shared, content-identified PR library. No catalog, report or ledger writes."""
import json
import threading
from pathlib import Path
from receiving_service import digest, atomic_json
from receiving_ledger import fingerprint

LOCK = threading.RLock()


def library_path(ledger_path):
    return Path(ledger_path).parent / 'pr-library'


def identity(images,directory=None):
    from receiving_document_identity import library_identity
    return library_identity(images,directory)


def load(directory):
    directory = Path(directory)
    path = directory / 'index.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('orders'), dict):
        raise ValueError('Thư viện PR không hợp lệ; không ghi đè dữ liệu.')
    return data['orders']


def register(directory, images, items):
    directory = Path(directory)
    if not images or not items:
        raise ValueError('PR chưa có ảnh hoặc dòng hàng.')
    if len({p.name for p in images}) != len(images):
        raise ValueError('Các trang PR trùng tên file; cần đặt tên riêng trước khi lưu.')
    key = identity(images,directory)
    with LOCK:
        orders = load(directory)
        stored = orders.get(key)
        if stored:
            # Never replace reviewed metadata or extracted lines on a later receipt.
            return key
        refs = sorted({str(i.get('pr_reference_id') or '').strip() for i in items} - {''})
        if len(refs) > 1:
            raise ValueError('Bộ ảnh có nhiều số PR, cần tách trước khi lưu.')
        def field(name):
            values = sorted({str(i.get(name) or '').strip() for i in items} - {''})
            return ' / '.join(values)
        copies = {}
        for index, source in enumerate(images):
            raw = Path(source).read_bytes()
            target = directory / key / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != raw:
                raise ValueError('Bản ảnh PR đã lưu khác nguồn; cần kiểm tra.')
            if not target.exists():
                from rec_runtime import atomic_bytes
                atomic_bytes(target, raw)
            copies[str(target.resolve())] = digest(target)
        from receiving_document_identity import page_ids
        from receiving_image_archive import atomic_json as archive_json
        pages=page_ids(images)
        if any(digest(p)!=copies[str((directory/key/p.name).resolve())] for p in images):raise ValueError('Ảnh PR thay đổi trong khi lưu; chọn lại.')
        archive_json(directory/key/'image-manifest.json',dict(version=1,files=[dict(original=p.name,target=p.name,source_sha256=pages[__import__('receiving_image_archive').image_name(p)],target_sha256=digest(p)) for p in images]))
        orders[key] = dict(number=refs[0] if refs else '', supplier=field('pr_supplier_name'),
                           date=field('pr_document_date'), department=field('pr_department'),
                           images=copies, items=items, source_ids=pages, identity_version=2)
        if field('order_type')=='po':
            orders[key].update(order_type='po',related_pr_number=field('related_pr_number'),
                               supplier_code=field('supplier_code'),supplier_on_po=field('pr_supplier_name'))
        atomic_json(directory / 'index.json', dict(version=1, orders=orders))
    return key


def images_for(record):
    images = [Path(p) for p in record['images']]
    if not images or any(not p.is_file() or digest(p) != record['images'][str(p)] for p in images):
        raise ValueError('Ảnh PR đã mất hoặc thay đổi; chưa thể chọn PR này.')
    return images


def update_metadata(directory, key, **metadata):
    with LOCK:
        orders = load(directory)
        if key not in orders:
            raise ValueError('Không tìm thấy PR đã chọn.')
        for name in ('number', 'supplier', 'date', 'department'):
            if name in metadata:
                orders[key][name] = str(metadata[name]).strip()[:200]
        atomic_json(Path(directory) / 'index.json', dict(version=1, orders=orders))


def title(record):
    kind = 'PO' if record.get('order_type')=='po' else 'PR'
    number = record.get('number') or 'Chưa rõ số '+kind
    return ' · '.join([number if kind=='PO' and number.upper().startswith('PO') else kind+' '+number,
                       record.get('supplier') or 'Chưa rõ NCC',
                       record.get('date') or 'Chưa rõ ngày PR',
                       record.get('department') or 'Chưa rõ bộ phận'])


def cards(directory, totals=()):
    groups = {}
    for line in totals:
        groups.setdefault(line['order_id'], []).append(line)
    result = []
    for key, record in load(directory).items():
        lines = groups.get(key, [])
        from fractions import Fraction
        unknown = any(r['remaining'] is None for r in lines)
        missing = sum(r['remaining'] is not None and Fraction(r['remaining']) > 0 for r in lines)
        over = sum(r['remaining'] is not None and Fraction(r['remaining']) < 0 for r in lines)
        cancelled = sum(bool(r.get('reason')) for r in lines)
        complete = bool(lines) and not (unknown or missing or over or cancelled)
        status = ('Cần kiểm tra lại nguồn' if unknown else
                  f'Còn thiếu {missing} món · Nhận dư {over} món'+(f' · Đã ngừng {cancelled} món' if cancelled else '') if missing or over else
                  f'Đã ngừng {cancelled} món · Không còn món chờ giao' if cancelled else
                  'Đã nhận đủ' if complete else 'Chưa ghi nhận vào sổ')
        result.append(dict(key=key, has_ledger=bool(lines), record=record, title=title(record), complete=complete,
                           status=status, count=len(record['items']),
                           received=sum(r['remaining'] is not None and Fraction(r['received']) == Fraction(r['ordered']) for r in lines)))
    from receiving_pr_library_dedup import compact_cards
    return sorted(compact_cards(result), key=lambda c: (c['complete'], c['title'], c['key']))
