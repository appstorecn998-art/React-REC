"""Web actions reuse the local receiving workbook and PR rules."""
import hashlib
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from AutoWatcher import load_catalog_data
from manual_invoice_links import merge_saved_invoices
from multi_delivery import output_lock
from receiving_image_archive import image_name, source_digest
from receiving_no_po import active, set_mode
from receiving_preferences import set_nickname
from receiving_pr import compare
from receiving_pr_image_identity import pr_images_match
from receiving_pr_library import load, title
from receiving_service import accounting_root, day_images, digest, invoice_images, mutate_invoice, sheet_signature, snapshot
from supplier_rules import normalize_name


def catalog_search(profile, query):
    terms = normalize_name(query[:200]).split()
    if not terms:
        return []
    catalog, _ = load_catalog_data(profile/'DanhMuc.xlsm')
    matches = [(code, name, unit) for code, (name, unit) in catalog.items()
               if all(term in normalize_name(f'{code} {name} {unit}') for term in terms)]
    matches.sort(key=lambda item: (item[0] != query.strip(), item[1].casefold()))
    return [dict(code=c, name=n, unit=u) for c,n,u in matches[:40]]


@lru_cache(maxsize=4)
def _report_rows(report, version):
    current, data = snapshot(report)
    if current != version:
        raise ValueError('Báo cáo đã đổi. Tải lại trước khi tiếp tục.')
    return data


def get_rows(report, sheet, version):
    if not isinstance(sheet, str):
        raise ValueError('Chọn phiếu trước.')
    if digest(report) != version:
        raise ValueError('Phiếu đã thay đổi. Tải lại trước khi tiếp tục.')
    # Cache parsed Excel only; callers still verify current bytes and get private rows.
    data = dict(deepcopy(_report_rows(Path(report), version)))
    if not data.get(sheet):
        raise ValueError('Phiếu không còn trong báo cáo.')
    return data


def pr_paths(report, sheet, rows, images):
    names = invoice_images(sheet, rows)
    sources = [p for p in images if image_name(p) in names]
    if not sources or {image_name(p) for p in sources} != names:
        return []
    folder = report.parent/'.receiving'/'.receiving'/'manual-pr-links'
    return [folder/(hashlib.sha256(json.dumps(sorted(
        (image_name(p), identify(p)) for p in sources)).encode()).hexdigest()+'.json')
        for identify in (source_digest, digest)]


def pr_library(store):
    return accounting_root(store)/'.receiving'/'pr-library'


def library_photos(library, key, record):
    if not re.fullmatch(r'[a-f0-9]{64}',key):
        raise ValueError('Mã thư viện PR không hợp lệ.')
    photos = [library/key/Path(old).name for old in record['images']]
    if not photos or any(not p.is_file() or digest(p)!=sha
                         for p,sha in zip(photos,record['images'].values())):
        raise ValueError('Ảnh PR đã mất hoặc thay đổi.')
    return photos


def pr_token(path):
    if path is None:
        return None
    files = [path, path.with_suffix('.comparison.json')]
    return hashlib.sha256(json.dumps([digest(p) if p.exists() else None for p in files]).encode()).hexdigest()


def pr_state(store, report, sheet, version):
    rows = get_rows(report, sheet, version)[sheet]
    images = day_images(report.parent)
    candidates = pr_paths(report,sheet,rows,images)
    link_path = next((p for p in candidates if p.is_file()), candidates[0] if candidates else None)
    info = dict(token=pr_token(link_path), canChoose=link_path is not None, linked=False)
    if active(report.parent/'.receiving', sheet, rows, images):
        return dict(info,status='no_po',message='Không có PR/PO. Phiếu được theo dõi thủ công.')
    if link_path is None or not link_path.exists():
        return dict(info,status='unlinked', message='Phiếu này chưa ghép PR.')
    link = json.loads(link_path.read_text(encoding='utf-8'))
    if link.get('source') == 'unlinked':
        return dict(info,status='unlinked', message='Phiếu này chưa ghép PR.')
    info['linked'] = True
    items = []
    label = 'PR đã ghép'
    if link.get('source') == 'pr-library':
        library = pr_library(store)
        key = link.get('library_key')
        record = load(library).get(key)
        if not record or record['images'] != link.get('paths'):
            raise ValueError('Liên kết thư viện PR đã thay đổi. Cần ghép lại.')
        selected = library_photos(library,key,record)
        items, label = record.get('items', []), title(record)
    else:
        selected = [p for p in images if any(image_name(p)==image_name(name) and
                    sha in (source_digest(p),digest(p)) for name,sha in link.get('images',{}).items())]
        if not pr_images_match(link.get('images'), selected):
            raise ValueError('Ảnh PR đã mất hoặc thay đổi.')
    info['images'] = selected
    saved_path = link_path.with_suffix('.comparison.json')
    links, conversions = {}, {}
    if saved_path.exists():
        saved = json.loads(saved_path.read_text(encoding='utf-8'))
        if saved.get('version') == 1 and pr_images_match(saved.get('images'), selected):
            items = saved.get('pr_items') or items
            if saved.get('signature') == sheet_signature(sheet, rows):
                links = {int(k):v for k,v in saved.get('links',{}).items()}
                conversions = {int(k):v for k,v in saved.get('conversions',{}).items()}
            elif saved.get('links') or saved.get('conversions'):
                return dict(info,status='review',message='Phiếu đã thay đổi. Xác nhận lại bản đối chiếu trên dữ liệu mới.', stale=True)
    if not items:
        return dict(info,status='review',message='Đã ghép ảnh PR nhưng chưa có dữ liệu dòng hàng. Đọc PR trong REC rồi mở lại.')
    return dict(info,status='ready',message=label,items=items,links=links,conversions=conversions,
                rows=rows,path=link_path,receiptImages=[
                    p for p in images if image_name(p) in invoice_images(sheet,rows)
                ])


def relocated_pr_link_hash(original, current, expected_hash, previous_root, root):
    from hashlib import sha256

    raw = original.read_bytes()
    if sha256(raw).hexdigest() != expected_hash:
        return None
    previous = json.loads(raw)
    current_raw = current.read_bytes()
    latest = json.loads(current_raw)
    if previous.get('source') != 'pr-library' or not isinstance(previous.get('paths'), dict):
        return None
    # Compare the original link after changing only the PR library root.
    library = previous_root / '.receiving' / 'pr-library'
    paths = {}
    for name, checksum in previous['paths'].items():
        path = Path(name)
        if not path.is_relative_to(library):
            return None
        paths[str(root / path.relative_to(previous_root))] = checksum
    if paths and {**previous, 'paths': paths} == latest:
        return sha256(current_raw).hexdigest()
    return None


def local_ledger_source(store, order_images):
    root = accounting_root(store)
    def resolve(record):
        record = dict(record)
        source = Path(record['report'])
        if source.resolve().is_relative_to(root.resolve()) and all(
            Path(value).resolve().is_relative_to(root.resolve())
            for value in (record['reviews_path'],record['pr_link_path'],*record['source_images'],*record['pr_images'])
        ):
            return record
        parts = source.parts
        month = next((i for i,x in enumerate(parts) if x.startswith('Thang ')),None)
        if month is None:
            return record
        previous_root = Path(*parts[:month])
        relative = source.relative_to(previous_root)
        local = root/relative
        if not local.is_file() and month and parts[month-1].isdigit():
            year_root = Path(*parts[:month-1])
            yearly = root/source.relative_to(year_root)
            if yearly.is_file():
                previous_root,local=year_root,yearly
        if not local.is_file():
            return {**record,'report':str(local)}
        record['report']=str(local)
        original_link=Path(record['pr_link_path'])
        for key in ('reviews_path','pr_link_path'):
            old=Path(record[key])
            if old.is_relative_to(previous_root):
                record[key]=str(root/old.relative_to(previous_root))
        # Imported path-only JSON rewrites retain the exact old and new hashes.
        try:
            proofs=json.loads((root/'.receiving/import-path-hashes.json').read_text(encoding='utf-8'))
            entry=proofs.get(str(Path(record['pr_link_path']).resolve()))
            if entry and record['pr_link_hash']==entry['source_sha256'] and digest(record['pr_link_path'])==entry['local_sha256']:
                record['pr_link_hash']=entry['local_sha256']
        except (OSError,ValueError,KeyError,TypeError):pass
        current_link=Path(record['pr_link_path'])
        if original_link!=current_link:
            try:
                if digest(current_link)!=record['pr_link_hash']:
                    matched_hash=relocated_pr_link_hash(original_link,current_link,record['pr_link_hash'],previous_root,root)
                    if matched_hash:record['pr_link_hash']=matched_hash
            except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
        try:
            candidates = day_images(local.parent)
        except (OSError, ValueError, KeyError, TypeError):
            return {**record,'source_images':{str(local):''}}
        for key in ('source_images','pr_images'):
            paths={}
            for old,sha in record[key].items():
                old_path=Path(old)
                copied=root/old_path.relative_to(previous_root) if old_path.is_relative_to(previous_root) else None
                originals=candidates if key=='source_images' else [*order_images,*candidates]
                if copied is not None and copied.is_file():originals=[copied,*originals]
                matches=[p for p in dict.fromkeys(originals) if image_name(p)==image_name(old)
                         and digest(p)==sha]
                paths[str(matches[0] if matches else local.parent/Path(old).name)]=sha
            record[key]=paths
        return record
    return resolve


def local_ledger_validator(store, order_images):
    from receiving_validation import check

    resolve = local_ledger_source(store, order_images)
    cache = {}
    return lambda record: check(resolve(record), cache)


def compare_with_lot_review(items, rows, links, conversions):
    from collections import Counter
    from receiving_lot_rows import grouped

    lots = {index: entry['lot_rows'] for index, entry in conversions.items()
            if entry.get('lot_rows')}
    claims = Counter(row for group in lots.values() for row in group)
    claims.update(row for index, row in links.items() if index not in lots and row is not None)
    row_ids = set(dict(rows))
    issues = {}
    for index, group in lots.items():
        try:
            if index not in links or any(claims[row] > 1 for row in group):
                raise ValueError('Dòng giao thiếu gán chính hoặc đang thuộc nhiều nhóm.')
            grouped(rows,{index:links[index]},{index:conversions[index]})
        except ValueError as error:
            owned = set(group) & row_ids
            if links.get(index) in row_ids:
                owned.add(links[index])
            issues[index] = dict(rows=sorted(owned), message=str(error))
    if not issues:
        return compare(items,rows,links,conversions),issues

    blocked = {row for issue in issues.values() for row in issue['rows']}
    safe_links = {index: None if index in issues or row in blocked else row
                  for index,row in links.items()}
    safe_links.update({index:None for index in issues})
    safe_conversions = {index:rule for index,rule in conversions.items() if index not in issues}
    results = compare(items,[(row,value) for row,value in rows if row not in blocked],
                      safe_links,safe_conversions)
    for result in results:
        index = result.get('pr_index')
        if index in issues or links.get(index) in blocked:
            result.update(remaining=None, alerts=['lot_review'],
                          status='Cần rà nhóm lô trước khi tính đủ hoặc thiếu.')
    return results,issues


def pr_result(store, report, sheet, version, *, photos=None):
    try:
        state = pr_state(store,report,sheet,version)
    except (OSError,ValueError,TypeError,KeyError) as error:
        rows = get_rows(report,sheet,version)[sheet]
        paths = pr_paths(report,sheet,rows,day_images(report.parent))
        path = next((p for p in paths if p.exists()),None)
        return dict(status='review',message=str(error),token=pr_token(path or (paths[0] if paths else None)),
                    canChoose=bool(paths),linked=bool(path))
    if photos is not None:
        photos.extend(state.get('images', []))
    if state['status'] != 'ready':
        state.pop('images', None)
        return state
    from receiving_cumulative import context,apply
    from receiving_document_identity import receipt_identity,library_identity
    from receiving_ledger import receipt_revision
    from sqlite3 import Error as LedgerError
    items,rows,links,conversions=(state[k] for k in ('items','rows','links','conversions'))
    label=state['message']
    from receiving_spec_memory import packaging
    from rec_runtime import user_root
    options=[dict(packaging=packaging(item,dict(rows).get(links.get(i),{})),index=i,name=item.get('item_name',''),code=item.get('catalog_code',''),
                  unit=item.get('unit',''),row=links.get(i),lotRows=conversions.get(i,{}).get('lot_rows',[]))
             for i,item in enumerate(items)]
    shared={k:state[k] for k in ('token','linked','canChoose')}
    shared['prItems']=options
    from receiving_link_memory import for_suppliers
    shared['pairRules']=for_suppliers(rows)
    from pr_opening import public as opening_public
    shared['opening']=opening_public(store,state,pr_library(store))
    try:
        results,lot_issues = compare_with_lot_review(items,rows,links,conversions)
        from rec_pr_review import blocking_details
        shared['reviewBlockers']=blocking_details(results)
        for result in results:
            p,r=result.get('pr_index'),result.get('row')
            if p is not None and r in dict(rows):
                options[p]['packaging']=packaging(items[p],dict(rows)[r])
    except ValueError as error:
        return dict(shared,status='review',message=str(error),repair=True)
    current_status={entry.get('pr_index'):entry['status'] for entry in results}
    ledger=accounting_root(store)/'.receiving'/'receiving-ledger.sqlite'
    posted=None
    try:
        receipt_id=receipt_identity(state['receiptImages'],ledger)
        posted=bool(receipt_revision(ledger,receipt_id,active_only=True))
        totals,uncertain,prior_count=context(
            ledger,library_identity(state['images'],pr_library(store)),
            receipt_id,local_ledger_validator(store,state['images']))
        results=apply(results,totals,uncertain,prior_count)
        for result in results:
            if 'lot_review' in result['alerts']:
                result['remaining']=None
        ledger_issue=''
    except (ValueError,OSError,KeyError,TypeError,LedgerError) as error:
        prior_count=0
        ledger_issue='Chưa xác minh được sổ nhận hàng. '+str(error)
        for result in results:
            result['remaining']=None
            result['alerts'].append('previous_receipt_invalid')
    for entry in results:
        p=entry.get('pr_index')
        if p is not None:
            options[p]['suggestedRow']=entry.get('row') or entry.get('suggested_row')
    from rec_pr_outcome import review_outcome, outcome_color
    counts = {}
    for result in results:
        row = result.get('row')
        counts[row] = counts.get(row,0)+1
    mapped = {}
    for result in results:
        row = result.get('row')
        if row is None:
            continue
        duplicate = counts[row] > 1
        ordered, remaining = result.get('ordered'), result.get('remaining')
        pr_index = result.get('pr_index')
        blocker = duplicate or bool(set(result['alerts']) & {
            'unit', 'code', 'specification', 'unknown_quantity', 'receipt_correction', 'substitution_stale', 'previous_receipt_invalid'
        })
        delta = None if remaining is None or blocker else float(-remaining) if remaining else 0
        item = items[pr_index] if pr_index is not None else {}
        method = ('unmatched' if pr_index is None else 'manual' if pr_index in links else
                  'code' if result.get('match_reason') == 'Cùng mã hàng' else
                  'remembered' if result.get('match_reason', '').startswith('Theo cặp tên bạn đã gán') else 'suggested')
        flags = set(result['alerts'])
        if 'previous_receipt_invalid' in flags:
            outcome,color = 'Cần rà lần nhận trước','#b7791f'
        elif blocker and not flags.intersection({'unit', 'duplicate_link', 'unknown_quantity'}):
            reasons = [label for flag,label in (('specification','Rà quy cách'), ('code','Khác mã'), ('receipt_correction','Xác minh số thực nhận'), ('substitution_stale','Rà hàng thay thế')) if flag in flags]
            outcome,color = 'Cần rà'+(' · '+', '.join(reasons) if reasons else ''), '#b7791f'
        else:
            outcome,color = review_outcome(result,prior_count),outcome_color(result,prior_count)
        mapped[row] = dict(
            outcome=outcome, outcomeColor=color,
            ordered=float(ordered) if ordered is not None and not duplicate else None,
            delta=delta, unit=result.get('unit') if not duplicate else '',
            status='Trùng ghép dòng PR' if duplicate else result['status'],
            method='conflict' if blocker else method,
            prName=None if duplicate else item.get('item_name'),
            prCode=None if duplicate else item.get('catalog_code'),
            prLine=None if duplicate else item.get('source_line'),
            reason='' if duplicate else result.get('match_reason', ''),
            received=float(result['received']) if result.get('received') is not None and not blocker else None,
            previous=float(result.get('previous_received',0)) if pr_index is not None and result.get('previous_received',0) is not None and not ledger_issue else None,
            remaining=float(remaining) if delta is not None else None,
            attention=bool(result['alerts']) or method in ('suggested','unmatched') or duplicate,
            prIndex=pr_index,
            topupAction=('reopen_topup' if result.get('no_topup') and result['no_topup'].get('action')!='reopen'
                         else 'stop_topup' if remaining is not None and remaining>0 and not duplicate
                         and not (flags-{'short'}) else None),

        )
        for lot in result.get('lot_rows', [])[1:]:
            mapped[lot] = dict(ordered=None, delta=None, method='lot',prIndex=pr_index,attention=False,
                               outcome='Đã cộng theo lô', outcomeColor='#65785d',
                               status='Lô đã cộng vào dòng '+str(row))
    for index,issue in lot_issues.items():
        for row in issue['rows']:
            mapped.setdefault(row,dict(prIndex=index,prName=items[index].get('item_name'),
                                       outcome='Cần rà nhóm lô',outcomeColor='#b7791f',
                                       attention=True,method='conflict',status=issue['message']))
    unmatched = [dict(name=entry['name'], status=entry['status'], index=entry['pr_index'],
                      confirmed=entry['pr_index'] in links and 'lot_review' not in entry['alerts'])
                 for entry in results if entry.get('row') is None]
    def quantity(value):
        return float(value) if value is not None else None

    shared['deliveryItems']=[]
    for entry in results:
        index=entry.get('pr_index')
        if index is None:
            continue
        row=entry.get('row')
        confirmed_missing=index in links and links[index] is None
        comparison=mapped.get(row,{}) if row is not None else {}
        received=comparison.get('received') if row is not None else 0 if confirmed_missing else None
        state=('received' if received>0 else 'not_delivered') if received is not None else 'review'
        shared['deliveryItems'].append(dict(
            index=index, name=items[index].get('item_name',''), row=row, unit=entry.get('unit',''),
            state=state, ordered=quantity(entry.get('ordered')), received=received,
            previous=quantity(entry.get('previous_received',0)) if not ledger_issue else None,
            reported=quantity(entry.get('original_received')) if state=='review' and row is not None else None,
            reportedUnit=dict(rows).get(row,{}).get('Đơn vị tính','') if state=='review' else '',
            remaining=quantity(entry.get('remaining')) if state!='review' else None,
            status=current_status[index] if state=='review' or set(entry['alerts'])-{'short'} else ''))
    if label == 'PR đã ghép':
        references = sorted({str(item.get('pr_reference_id') or '').strip() for item in items} - {''})
        if references:
            label = 'PR '+', '.join(references)
    if lot_issues:
        label += f' · {len(lot_issues)} nhóm lô cần rà'
    try:
        pending=pending_unreceived(items,rows,links,conversions)
        shared['pendingUnreceived']=[dict(index=r['pr_index'],name=items[r['pr_index']].get('item_name','')) for r in pending]
        shared['unreceivedBlocked']=''
    except ValueError as exc:
        shared['pendingUnreceived']=[];shared['unreceivedBlocked']=str(exc)
    return dict(shared,status='ready', message=label, rows=mapped, priorCount=prior_count, posted=posted, ledgerIssue=ledger_issue,
                unmatched=len(unmatched), unmatchedItems=unmatched)


def list_pr(store, query, *, rows=None, supplier_aliases=()):
    terms=normalize_name(query[:200]).split()
    entries=[]
    for key,record in load(pr_library(store)).items():
        label=title(record)
        searchable = normalize_name(f"{label} {record.get('related_pr_number','')}")
        if all(term in searchable for term in terms) and record.get('items'):
            entries.append(dict(key=key,title=label,record=record,complete=False))
    if rows:
        from receiving_pr_number_identity import rank_suggestions
        entries=rank_suggestions(entries,{},rows,supplier_aliases=supplier_aliases)
        seen=set()
        for entry in entries:
            if entry['suggestion_score'] < 3 or entry['title'] in seen:
                entry['suggestion_reason']=''
            if entry['suggestion_reason']:
                seen.add(entry['title'])
    return [dict(key=entry['key'], label=entry['title'], count=len(entry['record']['items']),
                 sample=[item.get('item_name','') for item in entry['record']['items'][:3]],
                 suggestion=entry.get('suggestion_reason','').replace(
                     'Có mặt hàng phù hợp','Tên hàng có từ trùng'))
            for entry in entries[:40]]


def pending_unreceived(items,rows,links,conversions):
    from rec_pr_review import outside_rows
    results,issues=compare_with_lot_review(items,rows,links,conversions)
    if issues:raise ValueError('Rà nhóm lô trước khi xác nhận các món còn lại.')
    if outside_rows(results):raise ValueError('Còn dòng trên phiếu giao chưa ghép PR. Ghép các món đã giao trước.')
    return [r for r in results if r.get('pr_index') is not None and r.get('row') is None and r['pr_index'] not in links]


def save_pr(store,report,payload):
    from receiving_service import atomic_json
    from rec_pr_link_write import write_link
    sheet,version,action=(payload.get(k) for k in ('sheet','version','action'))
    with output_lock(report):
        rows=get_rows(report,sheet,version)[sheet]
        images=day_images(report.parent)
        if active(report.parent/'.receiving',sheet,rows,images):
            raise ValueError('Phiếu đang theo dõi không PR/PO. Đổi trạng thái trước.')
        candidates=pr_paths(report,sheet,rows,images)
        if not candidates:
            raise ValueError('Phiếu thiếu ảnh nguồn.')
        path=next((p for p in candidates if p.exists()),candidates[0])
        if pr_token(path)!=payload.get('token'):
            raise ValueError('Liên kết hoặc bản nháp đã đổi. Mở lại đối chiếu PR.')
        if action in ('choose','unlink'):
            from receiving_document_identity import receipt_identity
            from receiving_ledger import summary
            ledger=accounting_root(store)/'.receiving'/'receiving-ledger.sqlite'
            refs=invoice_images(sheet,rows)
            receipt_id=receipt_identity([p for p in images if image_name(p) in refs],ledger)
            if any(r['receipt_id']==receipt_id and r['active'] for r in summary(ledger)[1]):
                raise ValueError('Phiếu đã ghi sổ. Gỡ lần nhận trong REC trước khi đổi PR.')
            value=dict(version=2,source='unlinked',sheet=sheet)
            if action=='choose':
                library=pr_library(store)
                key=payload.get('key')
                record=load(library).get(key) if isinstance(key,str) else None
                if not record or not record.get('items'):
                    raise ValueError('PR đã chọn không có dữ liệu dòng hàng.')
                photos=library_photos(library,key,record)
                value=dict(version=2,source='pr-library',sheet=sheet,library_key=key,
                           paths=record['images'],images={p.name:digest(p) for p in photos})
            before=path.read_bytes() if path.exists() else None
            write_link(path,value,expected=before,action='web-'+action)
            return
        state=pr_state(store,report,sheet,version)
        if action=='reset' and state.get('stale'):
            cached=path.with_suffix('.comparison.json')
            saved=json.loads(cached.read_text(encoding='utf-8'))
            from uuid import uuid4
            atomic_json(path.parent.parent/'pr-link-history'/path.stem/(uuid4().hex+'.comparison.json'),saved)
            saved.update(signature=sheet_signature(sheet,rows),links={},conversions={},results=[])
            atomic_json(cached,saved)
            return
        if action=='pair_rule' and state['status']=='ready':
            from receiving_link_memory import set_active
            from rec_runtime import user_root
            set_active(user_root(),rows,payload.get('rule'),payload.get('active'),payload.get('reason'))
            return {'updated':True}
        if action=='mark_unreceived' and state['status']=='ready':
            items,links,conversions=(state[k] for k in ('items','links','conversions'))
            pending=pending_unreceived(items,rows,links,conversions)
            expected=[r['pr_index'] for r in pending]
            if not expected:raise ValueError('Không còn món cần xác nhận chưa giao.')
            if payload.get('indices')!=expected:raise ValueError('Danh sách món còn lại đã thay đổi. Mở lại trước khi xác nhận.')
            for index in expected:
                links[index]=None
                conversions.pop(index,None)
            results,issues=compare_with_lot_review(items,rows,links,conversions)
            saved=dict(version=1,signature=sheet_signature(sheet,rows),images={image_name(p):source_digest(p) for p in state['images']},links=links,conversions=conversions,pr_items=items,results=results)
            atomic_json(path.with_suffix('.comparison.json'),json.loads(json.dumps(saved,default=str)))
            return {'marked':len(expected)}
        if action=='row_action' and state['status']=='ready':
            index,row=payload.get('index'),payload.get('row')
            if type(row) is not int or row not in dict(rows) or (payload.get('kind')!='deposit' and (type(index) is not int or not 0<=index<len(state['items']))):
                raise ValueError('Chọn dòng PR và dòng giao hợp lệ.')
            item,delivery=(state['items'][index] if type(index) is int and 0<=index<len(state['items']) else {}),dict(rows)[row]
            kind,fields=payload.get('kind'),payload.get('fields')
            if not isinstance(fields,dict) or any(not isinstance(v,str) for v in fields.values()):raise ValueError('Dữ liệu xác nhận không hợp lệ.')
            if kind=='opening':
                from pr_opening import commit
                commit(store,state,pr_library(store),fields)
                return {'saved':True}
            links,conversions=state['links'],state['conversions']
            if kind=='spec':
                from receiving_spec_equivalence import remember
                from rec_runtime import user_root
                from receiving_spec_memory import key_for,read
                key_for(item,delivery,read())
                remember(user_root(),item,delivery,fields.get('reason',''))
                return {'remembered':True}
            if kind=='deposit':
                from receiving_deposit import approve,key,effective
                if effective(row,delivery,conversions):conversions.pop(key(row),None)
                else:
                    if any(r.get('row')==row and r.get('pr_index') is not None for r in compare(state['items'],rows,links,conversions)):raise ValueError('Bỏ gán dòng hàng PR trước khi xác nhận cọc ngoài PR.')
                    conversions[key(row)]=approve(row,delivery,fields.get('reason',''))
            else:
                from pr_row_actions import apply
                resolved=compare(state['items'],rows,links,conversions)
                paired=next((r for r in resolved if r.get('pr_index')==index),{})
                if paired.get('row')!=row or (paired.get('lot_rows') and kind not in ('stop_topup','reopen_topup')):
                    raise ValueError('Ghép đúng một dòng giao trước khi thực hiện thao tác này.')
                entry=dict(conversions.get(index) or {})
                if not entry.get('factor') and not entry.get('receipt_correction'):
                    from receiving_spec_memory import remembered_conversion
                    remembered=remembered_conversion(row,item,delivery)
                    if remembered:entry.update(remembered)
                if kind=='packaging' and payload.get('preview') is True:
                    from pr_row_actions import package_preview
                    return {'preview':package_preview(item,delivery,row,entry,fields)}
                previous=0
                if kind in ('overreceipt','stop_topup'):
                    from receiving_cumulative import apply as cumulative, context
                    from receiving_document_identity import library_identity,receipt_identity
                    ledger=accounting_root(store)/'.receiving'/'receiving-ledger.sqlite'
                    totals,uncertain,count=context(ledger,library_identity(state['images'],pr_library(store)),receipt_identity(state['receiptImages'],ledger),local_ledger_validator(store,state['images']))
                    if index in uncertain:raise ValueError('Chưa xác minh được các lần nhận trước.')
                    previous=totals.get(index,0)
                    if kind=='stop_topup':
                        cumulative([paired],totals,uncertain,count)
                        if paired.get('remaining') is None or paired['remaining']<=0 or set(paired['alerts'])-{'short'}:
                            raise ValueError('Chỉ ngừng giao bù khi món còn thiếu và đã đối chiếu xong.')
                if kind in ('stop_topup','reopen_topup'):
                    from receiving_no_topup import decision, valid
                    saved_stop=entry.get('no_topup')
                    stopped=valid(item,saved_stop) and saved_stop.get('action')!='reopen'
                    if stopped!=(kind=='reopen_topup'):
                        raise ValueError('Trạng thái giao bù đã đổi. Mở lại đối chiếu.')
                    entry['no_topup']=decision(item,fields.get('reason',''))
                    if kind=='reopen_topup':
                        entry['no_topup']['action']='reopen'
                    conversions[index]=entry
                else:
                    conversions[index]=apply(kind,item,delivery,row,entry,fields,previous)
            results,issues=compare_with_lot_review(state['items'],rows,links,conversions)
            if issues:raise ValueError('Rà nhóm lô trước khi lưu xác nhận.')
            saved=dict(version=1,signature=sheet_signature(sheet,rows),images={image_name(p):source_digest(p) for p in state['images']},links=links,conversions=conversions,pr_items=state['items'],results=results)
            atomic_json(path.with_suffix('.comparison.json'),json.loads(json.dumps(saved,default=str)))
            if kind in ('conversion','packaging') and fields.get('remember')=='yes':
                from receiving_spec_memory import remember
                from rec_runtime import user_root
                try:remember(user_root(),item,delivery,kind,fields.get('value'),fields.get('reason'))
                except (OSError,ValueError) as exc:return {'warning':'Đã lưu cho phiếu này, chưa ghi nhớ được quy cách: '+str(exc)}
            if kind=='price':
                from receiving_price_approval import audit
                audit(path,conversions)
            return {'saved':True}
        if action=='remember_spec' and state['status']=='ready':
            index,row=payload.get('index'),payload.get('row')
            if type(index) is not int or not 0<=index<len(state['items']) or type(row) is not int or row not in dict(rows):
                raise ValueError('Chọn một mặt hàng PR và một dòng giao hợp lệ.')
            from receiving_spec_memory import remember
            from rec_runtime import user_root
            remember(user_root(),state['items'][index],dict(rows)[row],payload.get('kind'),payload.get('value'),payload.get('reason'))
            return {'remembered':True}
        if action!='assign' or state['status']!='ready' or 'target' not in payload:
            raise ValueError('Mở đối chiếu của phiếu đã ghép trước.')
        items,links,conversions=(state[k] for k in ('items','links','conversions'))
        index,target=payload.get('index'),payload.get('target')
        if type(index) is not int or not 0<=index<len(items):
            raise ValueError('Chọn dòng PR hợp lệ.')
        if target is None:
            links[index]=None
        elif target=='auto':
            links.pop(index,None)
        else:
            lot=target if isinstance(target,list) else [target]
            if not lot or any(type(row) is not int or row not in dict(rows) for row in lot) or len(set(lot))!=len(lot):
                raise ValueError('Chọn các dòng giao hợp lệ.')
            occupied={row for p,row in links.items() if p!=index}
            occupied.update(row for p,c in conversions.items() if p!=index for row in c.get('lot_rows',[]))
            if occupied.intersection(lot):
                raise ValueError('Dòng giao đã được gán cho món PR khác. Bỏ gán món đó trước.')
            links[index]=lot[0]
        conversions.pop(index,None)
        if isinstance(target,list) and len(target)>1:
            conversions[index]={'lot_rows':target}
        results,issues=compare_with_lot_review(items,rows,links,conversions)
        if index in issues:
            raise ValueError(issues[index]['message'])
        should_remember = payload.get('remember') is True
        if should_remember:
            from receiving_link_memory import reusable_pair
            if not isinstance(target,list) or len(target)!=1:
                raise ValueError('Chỉ ghi nhớ khi chọn đúng một dòng giao.')
            try:
                reusable_pair(items[index],dict(rows)[target[0]])
            except ValueError as error:
                should_remember=False
                warning='Đã lưu ghép cho phiếu này. '+str(error)
            else:
                warning=''
        saved=dict(version=1,signature=sheet_signature(sheet,rows),
                   images={image_name(p):source_digest(p) for p in state['images']},
                   links=links,conversions=conversions,pr_items=items,results=results)
        atomic_json(path.with_suffix('.comparison.json'),json.loads(json.dumps(saved,default=str)))
        if payload.get('remember') is True and not should_remember:
            return {'warning':warning}

        if should_remember:
            from receiving_link_memory import remember
            from rec_runtime import user_root
            try:
                remember(user_root(),items,rows,{index:target[0]},source='Xác nhận ghi nhớ trong React REC')
            except (OSError,ValueError) as error:
                return {'warning':'Đã lưu ghép cho phiếu. Chưa lưu được quy tắc dùng lại. '+str(error)}
            return {'remembered':True}


def save_vat(profile,report,payload):
    from receiving_service import edit_row,atomic_json
    sheet,version,row,rate=(payload.get(k) for k in ('sheet','version','row','rate'))
    if type(row) is not int or type(rate) is not int or rate not in (0,8,10):raise ValueError('Chọn dòng và VAT 8%, 10% hoặc khôi phục.')
    rows=get_rows(report,sheet,version)[sheet]
    if row not in dict(rows):raise ValueError('Dòng hàng không còn trong phiếu.')
    drafts=[]
    for path in pr_paths(report,sheet,rows,day_images(report.parent)):
        path=path.with_suffix('.comparison.json')
        if not path.is_file():continue
        raw=path.read_bytes();saved=json.loads(raw)
        if saved.get('signature')==sheet_signature(sheet,rows):drafts.append((path,raw,saved))
    warnings=[]
    def keep_draft():
        try:
            _,updated=snapshot(report);new_rows=dict(updated)[sheet]
            for path,raw,saved in drafts:
                if path.read_bytes()!=raw:
                    warnings.append('Bản ghép đã đổi; mở lại đối chiếu để rà.');continue
                saved.update(signature=sheet_signature(sheet,new_rows),results=[])
                atomic_json(path,saved)
        except (OSError,ValueError,KeyError) as exc:warnings.append('Đã lưu giá VAT; cần mở lại đối chiếu: '+str(exc))
    edit_row(report,version,sheet,row,{}, {},vat_rate=rate,on_saved=keep_draft)
    return {'saved':True,**({'warning':' '.join(warnings)} if warnings else {})}


def receipt_action(profile, report, payload, *, store=None):
    sheet, version, action = (payload.get(k) for k in ('sheet','version','action'))
    if action == 'vat':return save_vat(profile,report,payload)
    if action == 'capture_time':
        from rec_bulk_capture_time import apply

        data = get_rows(report, sheet, version)
        selected, value = payload.get('sheets'), payload.get('time')
        if (not isinstance(selected, list) or not selected
                or any(not isinstance(name, str) or not data.get(name) for name in selected)
                or not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value)):
            raise ValueError('Chọn phiếu và nhập giờ chụp HH:mm.')
        apply(report, version, selected, value)
        return {'saved': True}
    if action == 'rotate_source':
        from receiving_service import invoice_pages
        from preview_cache import build, saved_rotation
        from receipt_workflow import review_token

        with output_lock(report):
            rows = get_rows(report, sheet, version)[sheet]
            token = review_token(report, sheet, rows)
            if not token or token != payload.get('sourceToken'):
                raise ValueError('Ảnh nguồn đã đổi. Tải lại phiếu.')
            pages = invoice_pages(sheet, rows, day_images(report.parent))
            index, delta = payload.get('index'), payload.get('delta')
            if type(index) is not int or not 0 <= index < len(pages) or delta not in (-90, 90):
                raise ValueError('Chọn trang ảnh và góc xoay hợp lệ.')
            path = pages[index]
            build(path, (saved_rotation(path) + delta) % 360)
        return {'saved': True}
    if action == 'remove_receipt':
        from rec_remove_receipt import remove
        from receipt_workflow import guard, review_token
        from receiving_service import invoice_pages

        with guard:
            data = get_rows(report, sheet, version)
            images = day_images(report.parent)
            pages = invoice_pages(sheet, data[sheet], images)
            without_images = payload.get('withoutImages') is True
            if without_images:
                if pages or payload.get('sourceToken') is not None:
                    raise ValueError('Ảnh nguồn đã thay đổi. Tải lại phiếu trước khi gỡ.')
            else:
                token = review_token(report, sheet, data[sheet], images)
                if not token or payload.get('sourceToken') != token:
                    raise ValueError('Ảnh nguồn đã thay đổi. Tải lại phiếu trước khi gỡ.')
            source_hashes = {value for path in pages for value in (digest(path), source_digest(path))}
            for other, rows in data.items():
                if other != sheet and rows and any(
                    digest(path) in source_hashes or source_digest(path) in source_hashes
                    for path in invoice_pages(other, rows, images)
                ):
                    raise ValueError('Ảnh nguồn đang dùng chung với phiếu khác. Rà lại trước khi gỡ.')
            ledger = accounting_root(store)/'.receiving'/'receiving-ledger.sqlite'
            remove(report, version, sheet, pages, ledger, allow_no_images=without_images, day=payload.get('day'))
        return {'saved': True}
    if action == 'delete':
        row = payload.get('row')
        if not isinstance(sheet,str) or type(row) is not int or row < 2:
            raise ValueError('Chọn dòng cần xóa.')
        if row not in dict(get_rows(report, sheet, version)[sheet]):
            raise ValueError('Dòng không còn trong phiếu.')
        mutate_invoice(report, version, sheet, 'delete', [row])
        return {'saved':True}
    with output_lock(report):
        data = get_rows(report, sheet, version)
        rows = data[sheet]
        if action == 'nickname':
            label = payload.get('label')
            suppliers = {str(r.get('Nhà cung cấp') or '').strip() for _,r in rows} - {''}
            if len(suppliers)!=1 or not isinstance(label,str) or len(label)>100:
                raise ValueError('Cần một NCC duy nhất và tên hiển thị tối đa 100 ký tự.')
            set_nickname(profile, next(iter(suppliers)), label)
        elif action == 'no_po':
            if type(payload.get('enabled')) is not bool:
                raise ValueError('Chọn trạng thái PR/PO.')
            set_mode(report.parent/'.receiving',sheet,rows,day_images(report.parent),payload['enabled'])
        elif action == 'merge':
            other = payload.get('other')
            if not isinstance(other,str) or other == sheet or not data.get(other):
                raise ValueError('Chọn phiếu chứa trang cần ghép.')
            selected = (rows,data[other])
            for field in ('Nhà cung cấp','Số chứng từ trên phiếu'):
                names = {normalize_name(str(r.get(field) or '')) for group in selected for _,r in group} - {''}
                if len(names)>1:
                    raise ValueError('Hai phiếu khác '+field.lower()+'. Rà lại trước khi ghép.')
            refs = []
            for group in selected:
                sources = [str(r.get('Ảnh nguồn') or '').strip() for _,r in group if r.get('Ảnh nguồn')]
                if not sources:
                    raise ValueError('Phiếu thiếu tên ảnh nguồn.')
                refs.append(sources[0])
            if refs[0].casefold()==refs[1].casefold():
                raise ValueError('Hai phiếu cùng ảnh nguồn. Rà lại trước khi ghép.')
            return {'saved':True,'sheet':merge_saved_invoices(report,refs)}
        else:
            raise ValueError('Thao tác phiếu không hợp lệ.')
    return {'saved':True}


