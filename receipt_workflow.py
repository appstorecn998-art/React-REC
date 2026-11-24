"""Receipt review and export adapters for the independent web project."""
import hashlib
import json
import threading
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from multi_delivery import output_lock
from receiving_service import snapshot, sheet_signature, digest, day_images, invoice_images, atomic_json, accounting_root
from receiving_image_archive import image_name, source_digest

guard = threading.RLock()


def reviews(report):
    path = Path(report).parent/'.receiving/reviewed.json'
    result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(result, dict):
        raise ValueError('Dữ liệu xác nhận kiểm tra không hợp lệ.')
    return result


def reviewed(report, sheets):
    saved = reviews(report)
    source_path=Path(report).parent/'.receiving/reviewed-sources.json'
    sources=json.loads(source_path.read_text(encoding='utf-8')) if source_path.exists() else {}
    result={}
    images=None
    for name,rows in sheets:
        if not rows:continue
        signature=sheet_signature(name,rows)
        if saved.get(name)!=signature:
            result[name]=False
            continue
        try:
            if images is None:images=day_images(Path(report).parent)
            current=source_identity(report,name,rows,images)
        except (OSError,ValueError):current=None
        observation=sources.get(name) or {}
        result[name]=current is not None and observation.get('signature')==signature and observation.get('images')==current
    return result


def source_identity(report,sheet,rows,images=None):
    if images is None:images=day_images(Path(report).parent)
    require_sources(report,sheet,rows,images)
    refs=invoice_images(sheet,rows)
    return sorted([[image_name(p),digest(p),source_digest(p)] for p in images if image_name(p) in refs])


def review_token(report,sheet,rows,images=None):
    try:
        value=[sheet_signature(sheet,rows),source_identity(report,sheet,rows,images)]
        return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
    except (OSError,ValueError):return None


def require_sources(report, sheet, rows,images=None):
    refs = invoice_images(sheet, rows)
    available = set()
    for path in day_images(Path(report).parent) if images is None else images:
        if image_name(path) in refs:
            source_digest(path)
            available.add(image_name(path))
    explicit = any(v.get('Ảnh nguồn') or v.get('Các ảnh cùng phiếu') for _, v in rows)
    if not available or explicit and refs-available:
        raise ValueError('Thiếu ảnh nguồn của phiếu '+sheet+'. Khôi phục đúng ảnh trước khi xác nhận.')


def review(report, payload, *, store=None):
    if type(payload.get('reviewed')) is not bool or type(payload.get('expectedReviewed')) is not bool:
        raise ValueError('Trạng thái xác nhận không hợp lệ.')
    with guard, output_lock(report):
        version, sheets = snapshot(report)
        if version != payload.get('version'):
            raise ValueError('Báo cáo đã đổi. Tải lại trước khi xác nhận.')
        sheet = payload.get('sheet')
        rows = dict(sheets).get(sheet)
        if not rows:
            raise ValueError('Phiếu không còn trong báo cáo.')
        saved = reviews(report)
        signature = sheet_signature(sheet, rows)
        if reviewed(report,[(sheet,rows)])[sheet] != payload['expectedReviewed']:
            raise ValueError('Trạng thái kiểm tra đã đổi. Tải lại phiếu.')
        source_path=Path(report).parent/'.receiving/reviewed-sources.json'
        sources=json.loads(source_path.read_text(encoding='utf-8')) if source_path.exists() else {}
        if payload['reviewed']:
            from rec_department_guard import require_departments
            require_departments(rows)
            require_sources(report, sheet, rows)
            observed_sources=source_identity(report,sheet,rows)
            expected_token=hashlib.sha256(json.dumps([signature,observed_sources],sort_keys=True).encode()).hexdigest()
            if not payload.get('sourceToken') or payload['sourceToken']!=expected_token:
                raise ValueError('Ảnh nguồn đã đổi kể từ khi mở phiếu. Tải lại ảnh trước khi xác nhận.')
            from receipt_actions import pr_state, compare_with_lot_review
            from rec_pr_review import blocking_details
            pr=pr_state(store if store is not None else accounting_root(report.parent), report, sheet, version)
            if pr['status']=='review':
                raise ValueError(pr['message'])
            if pr['status']=='ready':
                results,_=compare_with_lot_review(pr['items'],rows,pr['links'],pr['conversions'])
                blockers=blocking_details(results)
                if blockers:raise ValueError('Chưa thể xác nhận đã kiểm. '+' | '.join(blockers))
            saved[sheet] = signature
            sources[sheet]=dict(signature=signature,images=observed_sources,reviewedAt=datetime.now().astimezone().isoformat())
        else:
            saved.pop(sheet, None)
            sources.pop(sheet,None)
        path = Path(report).parent/'.receiving/reviewed.json'
        if path.exists():
            backup = path.parent/'review-backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f.json')
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(path.read_bytes())
        atomic_json(source_path,sources)
        atomic_json(path, saved)
        return {'saved': True, 'reviewed': payload['reviewed']}


def preview(store, report):
    from receiving_provisional_export import pending
    from receiving_export_pr_notes import collect
    report = Path(report)
    version, sheets = snapshot(report)
    sheets = [(name, rows) for name, rows in sheets if rows]
    if not sheets:
        raise ValueError('Ngày này chưa có dữ liệu để xuất.')
    states = reviewed(report, sheets)
    ledger = accounting_root(store)/'.receiving/receiving-ledger.sqlite'
    context = SimpleNamespace(data=sheets, report=report, folder=report.parent/'.receiving',
                              images=day_images(report.parent), approved=lambda name: states[name],
                              ledger_path=lambda: ledger)
    from receipt_actions import local_ledger_validator
    pr_photos=[p for p in (accounting_root(store)/'.receiving/pr-library').rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.heic','.heif')]
    context.validate_ledger=local_ledger_validator(store,pr_photos)
    def resolve_report(path):
        parts=Path(path).parts
        month=next((i for i,v in enumerate(parts) if v.startswith('Thang ')),None)
        return accounting_root(store).joinpath(*parts[month:]) if month is not None else Path(path)
    context.resolve_report=resolve_report
    issues = pending(context)
    missing = []
    for name, rows in sheets:
        try:
            require_sources(report, name, rows)
        except ValueError as exc:
            missing.append(str(exc))
    files = [context.folder/'reviewed.json', ledger, Path(str(ledger)+'-wal')]
    files += sorted(context.folder.glob('.receiving/manual-pr-links/*.json'))
    files += [context.folder/'reviewed-sources.json']
    files += sorted(context.folder.glob('pending-replacement-pr/*.json'))
    files += sorted(context.folder.glob('.receiving/no-po/*.json'))
    identity = [(str(p), digest(p) if p.is_file() else None) for p in files]
    identity += [(str(p), digest(p)) for p in context.images]
    notes = collect(report)
    token = hashlib.sha256(json.dumps([version, issues, missing, notes, identity], sort_keys=True, default=str).encode()).hexdigest()
    return dict(version=version, token=token, receiptCount=len(sheets), reviewedCount=sum(states.values()),
                pending=[dict(sheet=name, reason=reason) for name, reason in issues],
                blockers=missing, notes=notes, provisional=bool(issues))


def export(store, profile, report, payload):
    from receiving_service import close_day
    from receiving_provisional_export import export as temporary
    from receiving_export_distribution import distribute, destinations
    report, store, profile = Path(report), Path(store), Path(profile)
    day = date.fromisoformat(payload['day'])
    with guard:
        state = preview(store, report)
        if payload.get('previewToken') != state['token'] or payload.get('version') != state['version']:
            raise ValueError('Nguồn hoặc trạng thái đã đổi. Mở lại xem trước khi xuất.')
        if state['blockers']:
            raise ValueError('\n'.join(state['blockers']))
        if state['provisional'] and payload.get('provisionalConsent') is not True:
            raise ValueError('Còn phiếu chưa hoàn tất. Cần xác nhận xuất BẢN TẠM.')
        # Distribution is isolated from the old REC's Desktop and shared folders.
        output_root = store.parent/'exports'
        def validate():
            if preview(store,report)['token'] != state['token']:
                raise ValueError('Nguồn hoặc trạng thái vừa đổi. Mở lại xem trước.')
        if state['provisional']:
            folder = temporary(profile, day, store, report, desktop=output_root,validate=validate)
        else:
            def distributed(folder):
                validate()
                distribute(folder,day,desktop=output_root)
            folder = close_day(profile, day, store, None, report,validate=validate,on_published=distributed,strict_existing=True)
        suffix = ' - BẢN TẠM' if state['provisional'] else ''
        invoice = Path(folder)/f'Phieu giao hang {day.day}-{day.month}-{day.year}{suffix}.xlsx'
        manager, archive = destinations(day, output_root, state['provisional'])
        files = [invoice, manager, archive]
        if not all(p.is_file() for p in files):
            raise ValueError('Chưa tạo đủ ba đầu ra. Kiểm tra nơi lưu rồi xuất lại.')
        result = dict(day=day.isoformat(), provisional=state['provisional'],
                      files=[dict(name=p.name, path=str(p.resolve()), sha256=digest(p)) for p in files])
        atomic_json(report.parent/'.receiving/web-export.json', result)
        return result


def download(store, report, index):
    record = json.loads((Path(report).parent/'.receiving/web-export.json').read_text(encoding='utf-8'))
    if type(index) is not int or not 0 <= index < len(record['files']):
        raise ValueError('File xuất không hợp lệ.')
    entry = record['files'][index]
    path = Path(entry['path']).resolve()
    allowed = (Path(store).resolve(), (Path(store).parent/'exports').resolve())
    if not any(path.is_relative_to(root) for root in allowed) or path.suffix not in ('.xlsx', '.zip'):
        raise ValueError('Đường dẫn file xuất không hợp lệ.')
    if not path.is_file() or digest(path) != entry['sha256']:
        raise ValueError('File xuất đã đổi hoặc bị mất. Xuất lại trước khi tải.')
    return path
