from receiving_image_archive import image_name, source_digest
"""Conservative automatic PR links. Never confirms receipts or writes ledger totals."""
import hashlib
import json
from pathlib import Path
from fractions import Fraction
import receiving_pr_library as library
from receiving_service import digest, atomic_json, invoice_images, snapshot, sheet_signature
from supplier_rules import normalize_name
from pr_warehouse import pr_reference


def date_key(value):
    from datetime import datetime
    for pattern in ('%Y-%m-%d','%d/%m/%Y'):
        try:return datetime.strptime(str(value).strip(),pattern).date().isoformat()
        except ValueError:pass
    return normalize_name(value)


def page_items(pages):
    result=[]
    for image, document in pages:
        for i,item in enumerate(document['items'],1):
            result.append(dict(item, source_image=Path(image).name,source_line=i,
                pr_reference_id=document.get('reference_id',''),
                **({'order_type':'po','related_pr_number':document.get('pr_reference_id',''),
                    'supplier_code':document.get('supplier_code','')}
                   if document.get('document_type')=='po' else {}),
                pr_supplier_name=document.get('supplier_name',''),
                pr_document_date=document.get('document_date',''),
                pr_department=document.get('department_name',''),
                requester_name=document.get('requester_name','')))
    return result


def possible_pr_continuation(previous,current):
    """A headerless consecutive page after an unfinished PR is not proof of delivery."""
    if not previous or previous.get('document_type') not in ('pr','po') or previous.get('has_total') is not False:return False
    if current.get('document_type')!='delivery' or current.get('reference_id') or current.get('delivery_date'):return False
    left=normalize_name(previous.get('supplier_name'));right=normalize_name(current.get('supplier_name'))
    if not left or left!=right:return False
    def numbers(d):
        values=[str(i.get('source_stt','')).strip() for i in d.get('items',[])]
        return [int(n) for n in values] if values and all(n.isdigit() for n in values) else []
    a,z=numbers(previous),numbers(current)
    if not a or not z or z[0]!=a[-1]+1:return False
    if any(i.get('receipt_mark') not in ('','unmarked','not_applicable',None) for i in current.get('items',[])):return False
    return True


def register_pages(directory, pages):
    """Only group multi-page PRs with the same explicit full document identity."""
    groups={}
    for image,document in pages:
        fields=[document.get(k,'') for k in ('reference_id','document_date','department_name','supplier_name')]
        # Without a full identity keep pages separate instead of inventing a bundle.
        key=('confirmed',document['_confirmed_pr_bundle']) if document.get('_confirmed_pr_bundle') else (document.get('document_type','pr'), *(normalize_name(v) for v in fields)) if all(fields[:3]) else (str(image),)
        groups.setdefault(key,[]).append((Path(image),document))
    saved=[]
    for group in groups.values():
        if len(group)==1 and str(group[0][1].get('page_number','')).isdigit() and int(group[0][1]['page_number'])>1:
            continue  # A continuation page alone does not define the whole PR.
        if len(group)>1:
            numbers=[str(d.get('_confirmed_page_number') or d.get('page_number') or '') for _,d in group]
            if all(n.isdigit() for n in numbers) and len(set(numbers))==len(numbers):
                group.sort(key=lambda pair:int(pair[1].get('_confirmed_page_number') or pair[1]['page_number']))
                ordered=[int(n) for n in sorted(numbers,key=int)]
                if ordered!=list(range(1,len(group)+1)):
                    raise ValueError('Bộ PR thiếu trang hoặc không bắt đầu ở trang 1. Chọn đủ trang trước khi lưu.')
            else:
                from delivery_pages import numbers as source_numbers
                sequences=[source_numbers(dict(document=d)) for _,d in group]
                if all(seq and all(y==x+1 for x,y in zip(seq,seq[1:])) for seq in sequences):
                    ordered=sorted(zip(group,sequences),key=lambda pair:pair[1][0])
                    if ordered[0][1][0]==1 and all(right[1][0]==left[1][-1]+1 and not left[0][1].get('has_total',False) for left,right in zip(ordered,ordered[1:])):
                        group=[pair[0] for pair in ordered]
                    else:
                        for page in group:saved.append(library.register(directory,[page[0]],page_items([page])))
                        continue
                else:
                    for page in group:saved.append(library.register(directory,[page[0]],page_items([page])))
                    continue
        saved.append(library.register(directory,[p for p,_ in group],page_items(group)))
    return saved


def matching_candidate(records,rows,documents=(),totals=()):
    from receiving_pr import compare
    po_references={normalize_name(d.get('po_reference_id','')) for d in documents}-{''}
    if len(po_references)>1:return None,'Phiếu giao có nhiều số PO. Cần chọn chứng từ đối chiếu.'
    po_reference=next(iter(po_references),'')
    references={pr_reference(d) for d in documents}-{''}
    if len(references)>1:return None,'Phiếu giao có nhiều tham chiếu PR khác nhau — cần chọn PR.'
    reference=next(iter(references),'')
    suppliers={normalize_name(v.get('Nhà cung cấp','')) for _,v in rows}-{'' ,normalize_name('Chưa rõ'),normalize_name('Chưa xác định nhà cung cấp')}
    if len(suppliers)>1:return None,'Phiếu giao có nhiều NCC — cần chọn PR.'
    dates={date_key(d.get('pr_date','')) for d in documents}-{''}
    departments={normalize_name(d.get('pr_department','')) for d in documents}-{''}
    by_order={}
    for line in totals:by_order.setdefault(line['order_id'],[]).append(line)
    matches=[]
    from receiving_pr_library_dedup import compact_cards
    cards=compact_cards([dict(key=k,record=r,count=len(r.get('items',[])),has_ledger=bool(by_order.get(k))) for k,r in records.items()])
    for card in cards:
        key,record=card['key'],card['record']
        if po_reference and (record.get('order_type')!='po' or normalize_name(record.get('number',''))!=po_reference):continue
        order_reference=pr_reference(dict(document_type='pr',reference_id=record.get('number','')))
        related=pr_reference(dict(pr_reference_id=record.get('related_pr_number','')))
        if reference and reference not in (order_reference,related) and not po_reference:continue
        if dates and date_key(record.get('date','')) not in dates:continue
        if departments and normalize_name(record.get('department','')) not in departments:continue
        supplier=normalize_name(record.get('supplier',''))
        if suppliers and supplier and supplier not in suppliers:continue
        if not reference and (not supplier or supplier not in suppliers):continue
        lines=by_order.get(key,[])
        if lines and (any(r['remaining'] is None or r.get('reason') for r in lines) or
                      not any(Fraction(r['remaining'])>0 for r in lines)):continue
        results=compare(record['items'],rows)
        mapped=[r['row'] for r in results if r.get('pr_index') is not None and r.get('row') is not None]
        # All delivered products must have unique reliable matches; price/quantity may differ.
        if set(mapped)!={n for n,_ in rows} or len(mapped)!=len(set(mapped)):continue
        if any(set(r.get('alerts',())) & {'code','specification','duplicate_link'} for r in results):continue
        matches.append(key)
    if len(matches)==1:
        return matches[0],('Khớp số PR tham chiếu và mặt hàng' if reference else 'Khớp duy nhất NCC và các mặt hàng; cần rà ảnh trước khi ghi sổ')
    return None,('Có nhiều PR phù hợp — cần chọn PR.' if matches else 'Chưa có PR khớp chắc chắn — cần chọn PR.')


def valid_receipt(payload):
    from receiving_validation import check
    return check(payload)


def link_report(directory,ledger_path,folder,report,images,documents):
    import receiving_ledger as ledger
    records=library.load(directory)
    if not records or not Path(report).exists():return []
    before=digest(report);_,sheets=snapshot(report)
    totals,_=ledger.summary(ledger_path,valid_receipt)
    messages=[]
    for sheet,rows in sheets:
        refs=invoice_images(sheet,rows)
        sources=[p for p in images if image_name(p) in refs]
        if not sources or {image_name(p) for p in sources} != refs:continue
        identities=sorted((image_name(p),source_digest(p)) for p in sources)
        path=Path(folder)/'.receiving'/'manual-pr-links'/(hashlib.sha256(json.dumps(identities).encode()).hexdigest()+'.json')
        legacy=sorted((image_name(p),digest(p)) for p in sources)
        old_path=path.with_name(hashlib.sha256(json.dumps(legacy).encode()).hexdigest()+'.json')
        if any(p.exists() or p.with_suffix('.comparison.json').exists() or p.with_suffix('.comparison.review.json').exists() for p in (path,old_path)):continue  # Never replace a saved selection or infer one after link loss.
        docs=[documents[p.name] for p in sources if p.name in documents]
        key,reason=matching_candidate(records,rows,docs,totals)
        if not key:messages.append(f'{sheet}: {reason}');continue
        try:pr_images=library.images_for(records[key])
        except (OSError,ValueError):messages.append(f'{sheet}: ảnh PR đã đổi, cần chọn lại.');continue
        if digest(report)!=before:raise ValueError('Báo cáo thay đổi trong khi ghép PR; tải lại và chọn PR.')
        from rec_pr_link_write import write_link
        write_link(path,dict(version=2,source='pr-library',automatic=True,reason=reason,sheet=sheet,
            library_key=key,paths=records[key]['images'],images={p.name:digest(p) for p in pr_images}),action='automatic-first-selection')
        messages.append(f'{sheet}: Đã tự ghép {library.title(records[key])}. {reason}. Chưa xác nhận/ghi sổ.')
    return messages
