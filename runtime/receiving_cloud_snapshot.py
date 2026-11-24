"""Allowlisted, read-only publication of REC data. Never exports a raw database/profile."""
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile

ROW_FIELDS = ('Tên hàng trên phiếu (Ảnh)', 'Tên chuẩn hệ thống', 'Mã vật tư', 'Đơn vị tính',
              'Đơn vị trên phiếu', 'Số lượng', 'Thực nhận', 'Đơn giá', 'Nhà cung cấp',
              'Ngày giao hàng', 'Ngày nhận hàng xác nhận', 'Mã kho', 'Tên kho', 'Bộ phận')
ITEM_FIELDS = ('item_name', 'catalog_code', 'quantity', 'unit_price', 'unit', 'specification')
SUMMARY_FIELDS = ('order_id', 'index', 'name', 'code', 'unit', 'ordered', 'requested', 'price',
                  'received', 'recorded_received', 'remaining', 'cancelled', 'reason', 'status',
                  'opening_received', 'opening_before', 'source_unverified', 'item_stopped',
                  'physical_remaining', 'stop_reason', 'stop_time')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def scalar(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, Decimal)):
        return str(value) if Decimal(str(value)).is_finite() else None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def select(record, fields):
    return {key: scalar(record[key]) for key in fields if key in record}


def build_snapshot(root, destination, start, end, staging, evidence=None):
    """Return (public dataset, local hash->file map). Files stay local until explicit publish."""
    from receiving_service import paths, snapshot, day_images, invoice_images, digest, accounting_root, sheet_signature
    from receiving_image_archive import image_name, source_digest, archive_image
    from receiving_price_pr import receipt_pr_numbers
    from receiving_pr_library import load, library_path, images_for
    import receiving_ledger as ledger
    from receiving_validation import check
    from rec_department_guard import missing_departments

    if not isinstance(start, date) or not isinstance(end, date) or start > end or (end-start).days > 365:
        raise ValueError('Chọn khoảng ngày hợp lệ, tối đa 366 ngày mỗi lần chia sẻ.')
    destination = Path(destination); staging = Path(staging); staging.mkdir(parents=True, exist_ok=True)
    path = accounting_root(destination)/'.receiving'/'receiving-ledger.sqlite'
    directory = library_path(path); index = directory/'index.json'
    observed = {}; warnings = []; assets = {}; local_files = {}; compressed = {}

    def observe(file):
        file = Path(file)
        signature = digest(file) if file.is_file() else None
        if file in observed and observed[file] != signature:
            raise ValueError('Nguồn vừa đổi khi chuẩn bị chia sẻ. Tải lại rồi thử lại.')
        observed[file] = signature
        return signature

    if index.exists():
        observe(index)
    try:
        records = load(directory)
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('Chưa đọc được thư viện PR. Sửa thư viện trước khi chia sẻ.') from None

    # Reuse an existing compressed representation of the same source across PR/day references.
    for manifest in (accounting_root(destination)/'AnhPhieu').rglob('image-manifest.json'):
        try:
            for entry in json.loads(manifest.read_text(encoding='utf-8')).get('files', []):
                candidate = manifest.parent/entry['target']
                if candidate.is_file():
                    compressed.setdefault(entry['source_sha256'], candidate)
        except (OSError, ValueError, KeyError, TypeError):
            warnings.append('Có danh sách ảnh lưu trữ chưa đọc được; ảnh liên quan sẽ được kiểm tra riêng.')

    def image_asset(file):
        file = Path(file); source = source_digest(file)
        candidate = compressed.get(source, file)
        if source_digest(candidate) != source:
            raise ValueError('Ảnh nén không khớp nguồn.')
        observe(candidate)
        # Existing archived WebP is copied byte-for-byte. Other PR originals are compressed once.
        if candidate.suffix.lower() != '.webp':
            candidate, _ = archive_image(candidate, staging/'encoded'/source)
        compressed[source] = candidate
        content_hash = observe(candidate)
        mime = {'.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}.get(candidate.suffix.lower())
        if not mime or candidate.stat().st_size > 16*1024*1024:
            raise ValueError('Ảnh không thuộc định dạng/dung lượng hỗ trợ.')
        assets[content_hash] = {'mime': mime, 'size': candidate.stat().st_size}
        local_files[content_hash] = candidate
        return content_hash

    def collect_images(files, label):
        found = []
        for file in files:
            try:
                key = image_asset(file)
                if key not in found:
                    found.append(key)
            except (OSError, ValueError, KeyError, TypeError):
                warnings.append(label+': ảnh nguồn thiếu hoặc chưa xác minh được.')
        return found

    summaries = []; history = []; id_map = {}
    if path.exists():
        observe(path); observe(path.with_name(path.name+'-wal'))
        # Summary code may initialize schemas; run it on a disposable consistent SQLite backup.
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as source:
            version = source.execute('PRAGMA data_version').fetchone()[0]
            with tempfile.TemporaryDirectory() as temporary:
                copy = Path(temporary)/'ledger.sqlite'
                with closing(sqlite3.connect(copy)) as target:
                    source.backup(target)
                cache = {}
                def validate(payload):
                    evidence = [payload.get(key) for key in ('report', 'reviews_path', 'pr_link_path')]
                    evidence += list(payload.get('source_images', {}))+list(payload.get('pr_images', {}))
                    for file in evidence:
                        if file: observe(file)
                    return check(payload, cache)
                summaries, history = ledger.summary(copy, validate)
                with closing(sqlite3.connect(copy.resolve().as_uri()+'?mode=ro', uri=True)) as conn:
                    id_map = dict(conn.execute('SELECT alias,order_id FROM order_aliases'))
            if source.execute('PRAGMA data_version').fetchone()[0] != version:
                raise ValueError('Sổ vừa đổi khi chuẩn bị chia sẻ. Thử lại.')
    public_summary = [select(row, SUMMARY_FIELDS) for row in summaries]
    posted = {(str(Path(row.get('report', '')).resolve()), row.get('sheet')): row for row in history if row.get('active')}
    orders = []
    for identity, record in sorted(records.items()):
        try:
            source_images = images_for(record)
        except (OSError, ValueError, KeyError, TypeError):
            source_images = []; warnings.append('PR '+str(record.get('number') or 'chưa rõ số')+': ảnh chưa xác minh được.')
        orders.append(dict(id=identity, order_id=id_map.get(identity, identity), **select(record, ('number', 'supplier', 'date', 'department')),
                           items=[select(item, ITEM_FIELDS) for item in record.get('items', [])],
                           images=collect_images(source_images, 'PR '+str(record.get('number') or 'chưa rõ số'))))
    receipts = []; selected = start
    while selected <= end:
        folder, report = paths(root, selected, destination)
        if report.is_file():
            original, data = snapshot(report)
            if report in observed and observed[report] != original:
                raise ValueError('Phiếu vừa đổi khi chuẩn bị chia sẻ. Thử lại.')
            observed[report] = original
            try:
                images = day_images(report.parent)
            except (OSError, ValueError, KeyError, TypeError):
                images = []; warnings.append(selected.isoformat()+': danh sách ảnh chưa đọc được.')
            review_path = folder/'reviewed.json'
            observe(review_path)
            try: reviews = json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
            except (ValueError, OSError): raise ValueError('Chưa đọc được xác nhận kiểm phiếu.')
            for sheet, rows in data:
                key = hashlib.sha256(canonical([selected.isoformat(), sheet])).hexdigest()
                refs = invoice_images(sheet, rows)
                pr_error = ''
                try:
                    numbers = receipt_pr_numbers(sheet, rows, images, folder, records)
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    numbers = []; pr_error = 'Chưa đọc được PR — cần kiểm tra liên kết'
                saved = posted.get((str(report.resolve()), sheet))
                source_images = [p for p in images if image_name(p) in refs]
                if not source_images:
                    warnings.append(selected.isoformat()+' / '+sheet+': thiếu ảnh nguồn trong bản chia sẻ.')
                receipts.append(dict(id=key, day=selected.isoformat(), label=sheet,
                                     reviewed=reviews.get(sheet) == sheet_signature(sheet, rows) and not missing_departments(rows),
                                     departments=sorted({str(v.get('Bộ phận') or '').strip() for _, v in rows if str(v.get('Bộ phận') or '').strip()}), pr_numbers=numbers, pr_error=pr_error,
                                     posting='verified' if saved and saved.get('valid') else 'needs_review' if saved else 'not_posted',
                                     rows=[dict(row=physical, values=select(values, ROW_FIELDS)) for physical, values in rows],
                                     images=collect_images(source_images, selected.isoformat()+' / '+sheet)))
        selected += timedelta(days=1)
    for file, expected in observed.items():
        if (digest(file) if file.is_file() else None) != expected:
            raise ValueError('Nguồn vừa đổi khi chuẩn bị chia sẻ. Tải lại rồi thử lại.')
    dataset = dict(schema=1, scope={'start': start.isoformat(), 'end': end.isoformat(), 'summary': 'all_posted'},
                   receipts=receipts, orders=orders, summary=public_summary, assets=assets,
                   warnings=list(dict.fromkeys(warnings)))
    dataset['source_revision'] = hashlib.sha256(canonical(dataset)).hexdigest()
    if evidence is not None: evidence.update(observed)
    return dataset, local_files
