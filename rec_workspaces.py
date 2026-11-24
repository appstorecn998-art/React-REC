"""React entry points for the desktop REC business services."""
import json
import re
from datetime import date
from pathlib import Path
from threading import RLock

from receiving_service import accounting_root

mutation_lock = RLock()


def ledger_path(store):
    return accounting_root(store)/'.receiving'/'receiving-ledger.sqlite'


def ledger_source(store, library=None):
    from receipt_actions import local_ledger_source, pr_library
    from receiving_pr_library import load, images_for

    if library is None:
        library = load(pr_library(store))
    photos = []
    for record in library.values():
        try:
            photos.extend(images_for(record))
        except (OSError, ValueError):
            continue
    return local_ledger_source(store, photos)


def ledger_snapshot(store):
    from receipt_actions import pr_library
    from receiving_ledger import summary
    from receiving_pr_library import load
    from receiving_validation import check

    library = load(pr_library(store))
    resolve = ledger_source(store, library)
    cache = {}
    validate = lambda record: check(resolve(record),cache)
    return (*summary(ledger_path(store), validate), library)


def ledger_view(store, *, reports=None):
    from receiving_register import collect
    from receiving_item_closure import line_key

    lines, records, _ = ledger_snapshot(store)
    portable = []
    selected_days = set(reports) if reports is not None else None
    for record in records:
        if selected_days is not None and record['day'] not in selected_days:
            continue
        source = Path(record['report'])
        start = next((i for i, part in enumerate(source.parts) if part.startswith('Thang ')), None)
        if start is not None:
            local = Path(store).joinpath(*source.parts[start:])
            if not local.is_file() and start and source.parts[start-1].isdigit():
                local = Path(store).joinpath(*source.parts[start-1:])
            if local.is_file():
                record = dict(record, report=str(local))
        portable.append(record)
    entries = collect(store, portable, reports=reports.values() if reports is not None else None)
    receipts = []
    for entry in entries:
        record = entry['record'] or {}
        receipts.append({key: entry[key] for key in ('day', 'sheet', 'supplier', 'count', 'status')} |
                        {key: record.get(key) for key in ('receipt_id', 'revision')})
    return dict(receipts=receipts, lines=[dict(row,version=line_key(row)) for row in lines])


def overview(store, reports, day):
    from receipt_actions import local_ledger_source, pr_library, pr_paths
    from rec_sync_results_page import read_events
    from receiving_service import day_images, sheet_signature
    from receiving_ledger import summary
    from receiving_pr_library import load
    from receiving_register import collect
    from receiving_validation import check

    _, history = summary(ledger_path(store))
    records = [record for record in history if record['active'] and record['day']==day]
    if records:
        library = load(pr_library(store))
        photos = [Path(name) for record in library.values() for name in record.get('images', {})]
        resolve = local_ledger_source(store, photos)
        cache = {}
        records = [resolve(record) for record in records]
        for record in records:
            record['valid'] = bool(check(record, cache))
    selected_reports = [reports[day]] if day in reports else []
    receipts = collect(store, records, reports=selected_reports)
    counts = {status:sum(row['status']==status for row in receipts) for status in
              ('Đã ghi sổ','Chưa ghi sổ','Cần kiểm tra lại','Không có PR/PO')}
    attention = {}
    activity = []
    if selected_reports:
        report = selected_reports[0]
        images = day_images(report.parent)
        for receipt in receipts:
            sheet, rows = receipt['sheet'], receipt['rows']
            if not rows or Path(receipt['report']).resolve() != report.resolve():
                continue
            if receipt['status']=='Cần kiểm tra lại':
                attention[sheet]='Cần rà lại nguồn đã ghi sổ'
                continue
            if receipt['status']!='Chưa ghi sổ':
                continue
            try:
                paths = pr_paths(report,sheet,rows,images)
                if not paths:
                    attention[sheet]='Thiếu ảnh nguồn'
                    continue
                link = next((path for path in paths if path.is_file()),None)
                if link is None or json.loads(link.read_text(encoding='utf-8')).get('source')=='unlinked':
                    attention[sheet]='Chưa ghép PR/PO'
                    continue
                comparison = link.with_suffix('.comparison.json')
                if comparison.is_file():
                    saved = json.loads(comparison.read_text(encoding='utf-8'))
                    if saved.get('signature')!=sheet_signature(sheet,rows):
                        attention[sheet]='Phiếu đã đổi sau khi đối chiếu PR'
                    elif any('specification' in row.get('alerts',[]) for row in saved.get('results',[])):
                        attention[sheet]='Đối chiếu đã lưu có cảnh báo quy cách'
            except (OSError, ValueError, TypeError, AttributeError):
                attention[sheet]='Cần rà dữ liệu đối chiếu PR'
        try:
            reviewed = json.loads((report.parent/'.receiving/reviewed-sources.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            reviewed = {}
        if isinstance(reviewed,dict):
            activity.extend(dict(kind='review',sheet=sheet,time=entry['reviewedAt'])
                            for sheet,entry in reviewed.items() if isinstance(entry,dict) and
                            isinstance(entry.get('reviewedAt'),str))
    revisions = {(record['receipt_id'],record['revision']) for record in records}
    openable_sheets = {receipt['sheet'] for receipt in receipts if receipt['rows']}
    if revisions:
        for event in read_events(ledger_path(store)):
            if (event['receipt_id'],event['revision']) in revisions:
                activity.append(dict(kind='ledger',sheet=event['sheet'],time=event['time'],
                                     sync=event['state'],retry=bool(event['error'])))
    return dict(day=day,total=len(receipts),counts=counts,attention=attention,
                activity=[event for event in activity if event['sheet'] in openable_sheets])


def library_view(store):
    from receipt_actions import pr_library
    from receiving_pr_library import cards
    from receiving_ledger import fingerprint

    lines, _, _ = ledger_snapshot(store)
    return dict(items=[
        {key: card[key] for key in ('key', 'title', 'status', 'count')} |
        {key: card['record'].get(key, '') for key in ('number','supplier','date','department','items','supplier_code','related_pr_number','order_type')} |
        {'warnings': card['record'].get('warnings', [])} |
        {'version': fingerprint(card['record'])}
        for card in cards(pr_library(store), lines)
    ])


def update_pr(store, payload):
    from receipt_actions import pr_library
    from receiving_ledger import fingerprint
    from receiving_pr_library import LOCK, load, update_metadata

    key = payload.get('key')
    changes = payload.get('changes')
    fields = {'number','supplier','date','department'}
    if (not isinstance(key,str) or not isinstance(changes,dict) or not changes
            or changes.keys()-fields or any(not isinstance(value,str) or len(value)>200 for value in changes.values())):
        raise ValueError('Thông tin PR không hợp lệ.')
    library = pr_library(store)
    with mutation_lock, LOCK:
        record = load(library).get(key)
        if record is None or fingerprint(record) != payload.get('version'):
            raise ValueError('PR đã đổi. Tải lại thư viện trước khi lưu.')
        if record.get('order_type') == 'po' and 'supplier' in changes:
            raise ValueError('Tên NCC trên PO được quản lý theo mã NCC.')
        update_metadata(library,key,**changes)
    return {'saved':True}


def update_ledger(store, payload):
    from receiving_ledger import revoke_receipt

    action = payload.get('action')
    path = ledger_path(store)
    with mutation_lock:
        if action == 'revoke':
            receipt, revision, reason = (payload.get(key) for key in ('receipt','revision','reason'))
            if not path.is_file() or not isinstance(receipt,str) or type(revision) is not int or not isinstance(reason,str) or not 1<=len(reason.strip())<=500:
                raise ValueError('Chọn lần nhận và nhập lý do thu hồi.')
            revoke_receipt(path,receipt,revision,reason.strip())
            return {'saved':True}
        if action in ('stop_item','reopen_item'):
            from receiving_item_closure import line_key, set_items

            order, index, reason = (payload.get(key) for key in ('order','index','reason'))
            if (not isinstance(order,str) or type(index) is not int
                    or not isinstance(reason,str) or not 1<=len(reason.strip())<=500):
                raise ValueError('Chọn mặt hàng và nhập lý do.')
            lines, _, _ = ledger_snapshot(store)
            row = next((item for item in lines if item['order_id']==order and item['index']==index),None)
            if row is None or line_key(row)!=payload.get('version'):
                raise ValueError('Mặt hàng đã thay đổi. Tải lại sổ nhận hàng.')
            if action=='stop_item' and (row['remaining'] is None or row['status']!='Còn thiếu'):
                raise ValueError('Chỉ ngừng giao bù cho mặt hàng xác định còn thiếu.')
            set_items(path,order,[index],reason.strip(),reopen=action=='reopen_item',
                      expected={str(index):payload['version']})
            return {'saved':True}
        raise ValueError('Thao tác sổ không hợp lệ.')


def post_day(store, reports, payload):
    from receipt_actions import pr_library
    from receiving_bulk_ledger import prepare, apply
    from receipt_workflow import guard, reviewed
    from rec_pr_review import token
    from receiving_service import day_images, snapshot

    day = payload.get('day')
    report = reports.get(day) if isinstance(day,str) else None
    if report is None:
        raise ValueError('Chọn ngày có báo cáo REC.')
    folder = report.parent/'.receiving'
    directory = pr_library(store)
    if not (directory/'index.json').is_file():
        raise ValueError('Chưa có PR trong thư viện.')
    with guard, mutation_lock:
        version, rows = snapshot(report)
        if not any(items for _,items in rows):
            raise ValueError('Ngày này chưa có phiếu.')
        def receipt_reviewed(sheet, items):
            return reviewed(report, [(sheet, items)])[sheet]

        plan = prepare(folder,report,rows,day_images(report.parent),directory,ledger_path(store),day,
                       receipt_reviewed=receipt_reviewed)
        entries = [{key: entry[key] for key in ('sheet','status','reason')} for entry in plan['entries']]
        ready = [e for e in plan['entries'] if e['status']=='Sẵn sàng ghi sổ']
        signature = token([version,plan['library_hash'],entries,[
            (e['payload'],e['expected_revision'],e['candidate']['before'].hex() if e['candidate']['before'] is not None else None)
            for e in ready
        ]])
        if 'token' in payload:
            if payload['token'] != signature:
                raise ValueError('Kết quả ghi sổ đã thay đổi. Xem trước lại.')
            return {'results':apply(plan)}
        return dict(entries=entries, ready=len(ready), token=signature)


def directory(profile):
    from AutoWatcher import load_catalog_data
    from supplier_directory import load_supplier_directory
    from warehouse_directory import load_warehouse_directory

    book = profile/'DanhMuc.xlsm'
    catalog, _ = load_catalog_data(book)
    return dict(
        items=[dict(code=code, name=name, unit=unit) for code, (name, unit) in catalog.items()],
        warehouses=[dict(code=code, name=name, department=department)
                    for code, (name, department) in load_warehouse_directory(book, required=False).items()],
        suppliers=[dict(code=code, name=name) for code, name in load_supplier_directory(book).items()],
    )


def prices(profile, store, month):
    from receiving_monthly_prices import scan

    try:
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            raise ValueError
        day = date.fromisoformat(month + '-01')
    except ValueError:
        raise ValueError('Chọn tháng theo dõi hợp lệ.') from None
    result = scan(profile, store, day)
    result.pop('stamp', None)
    return result


def settings(profile):
    from rec_runtime import config_check

    result = config_check(profile)
    return dict(checks=result['checks'])


def update_settings(profile, payload):
    import base64
    import json
    import tempfile
    from rec_runtime import atomic_bytes

    upload = payload.get('file')
    kind = payload.get('kind')
    if upload is not None:
        if kind not in ('catalog','google') or not isinstance(upload,str) or len(upload)>40_000_000:
            raise ValueError('Tệp cấu hình không hợp lệ.')
        try:
            content = base64.b64decode(upload,validate=True)
            if kind == 'google':
                from google.oauth2.service_account import Credentials
                configuration = json.loads(content.decode('utf-8-sig'))
                if (configuration.get('type') != 'service_account'
                        or configuration.get('token_uri') != 'https://oauth2.googleapis.com/token'):
                    raise ValueError
                Credentials.from_service_account_info(configuration)
                destination = profile/'google-sheets-key.json'
            else:
                from AutoWatcher import load_catalog_data
                from supplier_directory import load_supplier_directory
                from warehouse_directory import load_warehouse_directory
                with tempfile.TemporaryDirectory() as scratch:
                    source = Path(scratch)/'DanhMuc.xlsm'
                    source.write_bytes(content)
                    catalog, _ = load_catalog_data(source)
                    if not catalog:
                        raise ValueError
                    load_supplier_directory(source)
                    load_warehouse_directory(source)
                destination = profile/'DanhMuc.xlsm'
        except Exception:
            raise ValueError('Không đọc được tệp cấu hình. Chọn đúng tệp của REC.') from None
        with mutation_lock:
            if destination.exists():
                from datetime import datetime
                backup = profile/'.receiving'/'settings-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                atomic_bytes(backup/destination.name, destination.read_bytes())
            atomic_bytes(destination, content)
        return {'saved':True}

    key, sheet = payload.get('gemini', ''), payload.get('sheetId', '')
    if not isinstance(key, str) or not isinstance(sheet, str):
        raise ValueError('Cấu hình không hợp lệ.')
    key, sheet = key.strip(), sheet.strip()
    if key and not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', key):
        raise ValueError('Khóa Gemini không hợp lệ.')
    if sheet and not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', sheet):
        raise ValueError('Mã Google Sheets không hợp lệ.')
    if bool(key) == bool(sheet):
        raise ValueError('Chọn đúng một mục cấu hình để lưu.')
    with mutation_lock:
        if sheet:
            path = profile/'.receiving'/'runtime.json'
            existing = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
            atomic_bytes(path, json.dumps(dict(existing, sheet_id=sheet), ensure_ascii=False).encode())
        else:
            atomic_bytes(profile/'gemini_api_key.txt', key.encode())
    return {'saved': True}


def sheets(profile, store, token=None, *, automatic=False):
    from receiving_department_sheets import apply_preview, preview
    from receiving_sheets import SheetsClient, fingerprint

    with mutation_lock:
        lines, records, library = ledger_snapshot(store)
        suppliers = {}
        for record in records:
            if record['active'] and record['valid'] and record.get('supplier_name'):
                suppliers.setdefault(record['order_id'],set()).add(record['supplier_name'])
        suppliers = {key:' / '.join(sorted(names)) for key,names in suppliers.items()}
        for key,value in library.items():
            if value.get('supplier'):
                suppliers.setdefault(key,value['supplier'])
        client = SheetsClient(profile)
        plan = preview(client, lines, records, suppliers, library)
        signature = fingerprint([client.base, lines, records, plan])
        if automatic or token is not None:
            if not automatic and token != signature:
                raise ValueError('Sổ hoặc Google Sheets đã đổi. Xem trước lại.')
            latest, latest_records, latest_library = ledger_snapshot(store)
            if fingerprint([latest, latest_records, latest_library]) != fingerprint([lines, records, library]):
                raise ValueError('Nguồn phiếu đã đổi. Xem trước lại.')
            from receiving_ledger import sync_result
            from rec_sync_results_page import read_events
            path = ledger_path(store)
            revisions = {r['receipt_id']:r['revision'] for r in records if r['active'] and r['valid']}
            ids = [e['id'] for e in read_events(path) if e['state']!='synced'
                   and e['receipt_id'] in revisions and e['revision']<=revisions[e['receipt_id']]]
            count = apply_preview(client, plan)
            if ids:
                message = f"Còn {plan['skipped']} dòng cần rà trong bản đồng bộ." if plan['skipped'] else None
                sync_result(path, ids, message)
            return dict(updated=count, skipped=plan['skipped'])
    return dict(token=signature, skipped=plan['skipped'], historyReview=bool(plan['history_review']),
                departmentIssues=plan['department_issues'],
                changeCount=len(plan['changes']), newTabs=[part['tab'] for part in plan['parts'] if part['create']],
                changes=[dict(tab=row['tab'], supplier=row['supplier'], name=row['name'], action=row['action'],
                              old=row['old'], values=row['values'], delete=bool(row.get('delete'))) for row in plan['changes']])


def sync_history(store):
    from rec_sync_results_page import read_events

    return dict(events=read_events(ledger_path(store)))
