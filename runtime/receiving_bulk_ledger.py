from receiving_image_archive import image_name, source_digest
"""Explicit batch approval of new receipts, with per-receipt source guards."""
import json
from pathlib import Path
import receiving_ledger as ledger
from receiving_service import digest,sheet_signature,invoice_images,atomic_json,snapshot
from receiving_validation import check

def prepare(folder,report,sheets,images,directory,path,day,*,receipt_reviewed=None):
    from receiving_pr_bulk import prepare as comparisons
    from receiving_pr import compare
    before=digest(report);current=dict(snapshot(report)[1])
    if any(sheet not in current or sheet_signature(sheet,rows)!=sheet_signature(sheet,current[sheet]) for sheet,rows in sheets) or set(current)!=set(dict(sheets)) or digest(report)!=before:raise ValueError('Excel đã đổi so với bảng đang xem. Tải lại trước khi duyệt ghi sổ.')
    library_path=Path(directory)/'index.json'
    library_hash=digest(library_path)
    from receiving_pending_pr import read as pending_pr
    waiting=[];active_sheets=[]
    for sheet,rows in sheets:
        pending=pending_pr(folder,sheet,rows,images)
        if pending:waiting.append(dict(sheet=sheet,status='Chờ PR thay thế',reason=pending['reason']))
        else:active_sheets.append((sheet,rows))
    preview=comparisons(folder,report,active_sheets,images,directory)
    if digest(library_path)!=library_hash:raise ValueError('Thư viện PR vừa đổi. Tải lại trước khi duyệt ghi sổ.')
    if preview['report_hash']!=before:raise ValueError('Excel vừa đổi. Tải lại trước khi duyệt ghi sổ.')
    cache={}
    _,history=ledger.summary(path,lambda p:check(p,cache))
    recorded={p['receipt_id']:p for p in history}
    orders=ledger.list_orders(path);values=dict(sheets);entries=[];seen=set();staged={};staged_documents={}
    entries.extend(waiting)
    for sheet,reason in preview['skipped']:entries.append(dict(sheet=sheet,status='Cần rà lại',reason=reason))
    for sheet,reason in preview['manual']:entries.append(dict(sheet=sheet,status='Không có PR/PO',reason=reason))
    for c in preview['changes']:
        sheet=c['sheet'];entry=dict(sheet=sheet,status='Cần rà lại',reason='');entries.append(entry)
        try:
            rows=values[sheet];items=c['payload']['pr_items'];links=dict(c['payload']['links']);conversions=c['payload']['conversions']
            from rec_department_guard import require_departments
            require_departments(rows)
            refs=invoice_images(sheet,rows)
            sources={p:h for p,h in c['images'].items() if image_name(Path(p)) in refs}
            from receiving_pr_image_identity import pr_images_match
            prs={p:h for p,h in c['images'].items() if image_name(Path(p)) in c['payload']['images']}
            if not prs or not pr_images_match(c['payload']['images'],[Path(p) for p in prs]):raise ValueError('Ảnh PR thiếu hoặc đã thay đổi')
            from receiving_document_identity import receipt_identity
            rid=receipt_identity([Path(p) for p in sources],path)
            if rid in seen:raise ValueError('Trùng ảnh nguồn với phiếu khác trong lượt này')
            seen.add(rid)
            previous=recorded.get(rid)
            if previous and previous['active'] and previous['valid'] and previous['signature']==sheet_signature(sheet,rows):
                # Same receipt is skipped only if its reviewed decisions also match.
                current_links=dict(links)
                for result in compare(items,rows,links,conversions):
                    if result.get('pr_index') is not None and result.get('row') is not None:current_links.setdefault(result['pr_index'],result['row'])
                same_links=json.loads(json.dumps(current_links))==previous.get('allocation_rows')
                same_decisions=same_links and json.loads(json.dumps(previous.get('conversions',{}),default=str))==json.loads(json.dumps(conversions,default=str))
                if same_decisions and previous.get('pr_link_hash')==digest(c['link']):
                    entry.update(status='Đã ghi sổ',reason='Đã ghi, không cộng lại');continue
            from receiving_batch_review import reviewed_window
            from rec_pr_review import inspection
            window=reviewed_window(sheet,rows,[Path(p) for p in sources],[Path(p) for p in prs])
            review=inspection(window,c['path'])
            if review['state'] not in ('done','partial_done') and not (
                receipt_reviewed and receipt_reviewed(sheet,rows)
            ):
                raise ValueError('Chưa kiểm xong phiếu: '+review['reason'])
            if previous and not previous['active']:raise ValueError('Lần nhận đã thu hồi; mở riêng để khôi phục')
            results=compare(items,rows,links,conversions)
            for r in results:
                if 'pr_index' in r and r.get('row') is not None:links.setdefault(r['pr_index'],r['row'])
            from rec_pr_review import blocking_details
            blockers=blocking_details(results)
            if blockers:raise ValueError(' | '.join(blockers))
            lines=ledger.order_lines(items,conversions);alloc=ledger.allocations(items,rows,links,conversions)
            from receiving_pr_library import identity as pr_identity
            identity=pr_identity([Path(p) for p in prs],directory);oid=ledger.resolve_order(path,identity)
            from receiving_pr_number_identity import check_new_order
            identity_note=check_new_order(directory,path,identity,oid,orders,lines)
            from receiving_pr_number_identity import check_batch_document
            document=check_batch_document(directory,identity,oid,staged_documents)
            payload=dict(pr_identity=identity,day=day,sheet=sheet,report=str(report),supplier_name=' / '.join(sorted({str(v.get('Nhà cung cấp') or '').strip() for _,v in rows}-{''})) or 'Chưa xác định nhà cung cấp',signature=sheet_signature(sheet,rows),source_rows=json.loads(json.dumps(rows,default=str)),reviews_path=str(Path(folder)/'reviewed.json'),source_images=sources,pr_images=prs,allocations=alloc,allocation_rows={str(k):v for k,v in links.items()},conversions=conversions,pr_link_path=str(c['link']),pr_link_hash=digest(c['link']))
            if any(entry.get('no_topup') for entry in conversions.values()):
                payload['no_topup_items']=items
            if previous and previous['order_id']!=oid:raise ValueError('Đổi PR của phiếu đã ghi; cần mở riêng để xác nhận chuyển PR')
            warnings=ledger.receipt_warnings(path,oid,lines,rid,payload)
            if warnings:raise ValueError('; '.join(warnings))
            from fractions import Fraction
            prior=staged.get(oid,[])
            if any(a==alloc and any(Fraction(q)>0 for q in alloc.values()) for a in prior):raise ValueError('Giống lượng nhận của phiếu khác cùng PR trong lượt này; rà nguy cơ trùng')
            for i,line in enumerate(lines):
                key=str(i)
                existing=sum((Fraction(p['allocations'].get(key,'0')) for p in history if p['active'] and p['order_id']==oid and p['receipt_id']!=rid),Fraction(0))
                from receiving_overreceipt import permits
                from receiving_opening_balance import read as read_opening
                opening=read_opening(path,oid).get(oid,{})
                previous_total=existing+sum((Fraction(a[key]) for a in prior),Fraction(0))+Fraction(opening.get('quantities',{}).get(key,'0'))
                if previous_total+Fraction(alloc[key])>Fraction(line['ordered']) and not permits(payload,i,line,previous_total):raise ValueError(line['name']+': tổng nhận trong lượt này vượt lượng đặt; mở riêng để duyệt')
            staged.setdefault(oid,[]).append(alloc)
            staged_documents[document]=oid
            title=', '.join(Path(p).name for p in prs)
            entry.update(expected_revision=previous['revision'] if previous else 0,status='Sẵn sàng ghi sổ',reason=(identity_note+' · ' if identity_note else '')+'; '.join(line['name']+': nhận '+alloc[str(i)]+'/'+line['ordered']+' '+line['unit'] for i,line in enumerate(lines)),candidate=c,payload=payload,lines=lines,receipt_id=rid,order_id=oid,title=title,rows=rows)
        except (OSError,ValueError,KeyError,TypeError) as exc:entry['reason']=str(exc)
    preview.update(entries=entries,ledger_path=Path(path),library_path=library_path,library_hash=library_hash,receipt_reviewed=receipt_reviewed);return preview

def apply(preview,progress=lambda *_:None):
    ready=[e for e in preview['entries'] if e['status']=='Sẵn sàng ghi sổ'];results=[]
    for i,e in enumerate(ready):
        progress('Đang ghi sổ · '+e['sheet'])
        try:
            c=e['candidate'];p=e['payload']
            from receiving_pending_pr import read as pending_pr
            if pending_pr(Path(p['reviews_path']).parent,e['sheet'],e['rows'],[Path(n) for n in p['source_images']]):raise ValueError('Phiếu đang chờ PR thay thế; chưa ghi sổ')
            from rec_department_guard import require_departments
            require_departments(e['rows'])
            if digest(preview['library_path'])!=preview['library_hash']:raise ValueError('Thư viện PR đã đổi sau khi duyệt. Tải lại danh sách trước khi ghi sổ.')
            if digest(preview['report'])!=preview['report_hash'] or c['link'].read_bytes()!=c['link_bytes'] or (c['path'].read_bytes() if c['path'].exists() else None)!=c['before'] or any(not Path(name).is_file() or digest(name)!=h for name,h in c['images'].items()):raise ValueError('Nguồn đổi sau khi duyệt; cần tải lại')
            from receiving_no_po import active
            if active(Path(p['reviews_path']).parent,e['sheet'],e['rows'],[Path(n) for n in p['source_images']]):raise ValueError('Phiếu vừa chuyển sang không PR/PO')
            if ledger.receipt_revision(preview['ledger_path'],e['receipt_id'])!=e.get('expected_revision',0):raise ValueError('Phiếu vừa được ghi sổ ở lượt khác; không ghi trùng')
            warnings=ledger.receipt_warnings(preview['ledger_path'],e['order_id'],e['lines'],e['receipt_id'],p)
            if warnings:raise ValueError('; '.join(warnings))
            from receiving_price_approval import audit
            audit(c['path'],p['conversions'])
            from receiving_batch_review import reviewed_window
            from rec_pr_review import inspection
            window=reviewed_window(e['sheet'],e['rows'],[Path(n) for n in p['source_images']],[Path(n) for n in p['pr_images']])
            receipt_reviewed=preview.get('receipt_reviewed')
            if inspection(window,c['path'])['state'] not in ('done','partial_done') and not (
                receipt_reviewed and receipt_reviewed(e['sheet'],e['rows'])
            ):
                raise ValueError('Xác nhận kiểm phiếu đã đổi; cần rà lại')
            ledger.save_receipt(preview['ledger_path'],e['order_id'],e['title'],e['lines'],e['receipt_id'],p,e.get('expected_revision',0))
            reviews_path=Path(p['reviews_path']);reviews=json.loads(reviews_path.read_text(encoding='utf-8')) if reviews_path.exists() else {};reviews[e['sheet']]=p['signature'];atomic_json(reviews_path,reviews)
            atomic_json(c['path'],json.loads(json.dumps(c['payload'],default=str)))
            if not check(p,{}):raise ValueError('Đã lưu nhưng nguồn chưa hợp lệ; mở riêng để kiểm tra lại')
            results.append((e['sheet'],'Đã ghi sổ',''))
        except Exception as exc:results.append((e['sheet'],'Cần rà lại',str(exc)))
        progress(f'Đã xử lý {i+1}/{len(ready)} phiếu · '+e['sheet'])
    return results
