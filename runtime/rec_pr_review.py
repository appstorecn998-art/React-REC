"""Explicit review marker, bound to the comparison and its source state."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def token(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()

def marker_path(path):return Path(path).with_suffix('.review.json')

def outside_rows(results):
    return [r for r in results if r.get('pr_index') is None and not r.get('deposit') and (r.get('received') is None or r.get('received')!=0)]

def eligible(results,allow_outside=False):
    selected=[r for r in results if r.get('pr_index') is not None]
    return bool(selected) and (allow_outside or not outside_rows(results)) and all(not (set(r.get('alerts',[]))-{'short','previous_receipt_invalid'}) for r in selected)

def blocking_details(results):
    if eligible(results):
        return []
    blockers=[r for r in results if r.get('pr_index') is not None and set(r.get('alerts',[]))-{'short','previous_receipt_invalid'}]
    blockers.extend(outside_rows(results))
    return [f"{r['name']} — {r['status']}" for r in blockers] or ['Đối chiếu chưa có dòng PR đủ điều kiện.']

def decision(saved):
    from receiving_image_archive import image_name
    # Computed status text/cumulative totals are not the user's decisions.
    return token({'signature':saved.get('signature'),'images':{image_name(k):v for k,v in saved.get('images',{}).items()},'links':saved.get('links',{}),'conversions':saved.get('conversions',{}),'pr_items':saved.get('pr_items',[])})

def receipt_source(w):
    from receiving_service import invoice_images,digest,sheet_signature
    from receiving_image_archive import image_name,source_digest
    refs=invoice_images(w.current_sheet,w.data_by_sheet.get(w.current_sheet,[]))
    return token({'signature':sheet_signature(w.current_sheet,w.data_by_sheet.get(w.current_sheet,[])),
                  'receipt_images':sorted((image_name(p),source_digest(p)) for p in getattr(w,'images',[]) if image_name(p) in refs),
                  'pr_images':sorted((image_name(p),source_digest(p)) for p in w.receipt_references())})

def legacy_source_matches(w,expected):
    if receipt_source(w)==expected:return True
    from receiving_image_archive import image_name,source_digest,sha
    from receiving_service import invoice_images,sheet_signature
    refs=invoice_images(w.current_sheet,w.data_by_sheet.get(w.current_sheet,[]))
    receipt=[p for p in getattr(w,'images',[]) if image_name(p) in refs]
    for receipt_digest in (source_digest,sha):
        for pr_digest in (source_digest,sha):
            value=dict(signature=sheet_signature(w.current_sheet,w.data_by_sheet.get(w.current_sheet,[])),
                receipt_images=sorted((image_name(p),receipt_digest(p)) for p in receipt),
                pr_images=sorted((image_name(p),pr_digest(p)) for p in w.receipt_references()))
            if token(value)==expected:return True
    return False


def legacy_reviewed_snapshot(w, saved, mark):
    """Recover only snapshots authenticated by the original review hash."""
    from receiving_image_archive import image_name, source_digest, sha
    from receiving_pr import compare
    from receiving_cumulative import apply
    import copy
    images=w.receipt_references()
    variants=[saved]
    for hashes in ({image_name(p):source_digest(p) for p in images},
                   {image_name(p):sha(p) for p in images}):
        candidate=dict(saved,images=hashes)
        variants.append(candidate)
    for candidate in variants:
        if mark.get('version',1)>=3:
            if mark.get('decision')==decision(candidate):return True
        elif mark.get('comparison')==token(candidate):return True
    if mark.get('version',1)>=3:return False
    rows=w.data_by_sheet.get(w.current_sheet,[])
    links={int(k):v for k,v in saved.get('links',{}).items()}
    conversions={int(k):v for k,v in saved.get('conversions',{}).items()}
    items=saved.get('pr_items',[])
    # Older dialogs added unknown-history display fields; bulk refresh removed
    # them. Reconstruct that display, requiring an exact signed snapshot match.
    original=compare(items,rows,links,conversions)
    for candidate in variants:
        for uncertain in (set(),set(range(len(items)))):
            results=apply(copy.deepcopy(original),{},uncertain,0)
            snapshot=json.loads(json.dumps(dict(candidate,results=results),default=str))
            if mark.get('comparison')==token(snapshot):return True
            # Frozen v1 renderer wording: authenticate the exact old snapshot,
            # never use today's presentation strings as approval evidence.
            for result in snapshot['results']:
                result['status']=result.get('status','').replace('Nguồn lần nhận khác đã đổi; cần cập nhật phiếu. ','Lịch sử chưa xác minh; chưa kết luận thiếu/dư. ')
            if mark.get('comparison')==token(snapshot):return True
    return False

# Only business inputs belong to a review. Display/cache fields never do.
RECEIPT_FIELDS=('Tên hàng trên phiếu (Ảnh)','Mã vật tư','Tên chuẩn hệ thống',
 'Đơn vị tính','Đơn vị trên phiếu','Số lượng','Thực nhận','Đơn giá','Thành tiền',
 'Nhà cung cấp','Ngày giao hàng','Ngày nhận hàng xác nhận','Mã kho','Bộ phận',
 'STT trên phiếu','Thành tiền trên phiếu','Thành tiền gốc (trước công thức)')
PR_FIELDS=('item_name','catalog_code','quantity','unit_price','unit','specification',
 'pr_reference_id','pr_supplier_name','pr_document_date','pr_department','source_stt','source_line')


def canonical(value):
    # JSON key types and Decimal/int serialization must not change decisions.
    if isinstance(value,dict):return {str(k):canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [canonical(v) for v in value]
    if value is None or isinstance(value,bool):return value
    from decimal import Decimal,InvalidOperation
    if isinstance(value,(int,float,Decimal)):
        return format(Decimal(str(value)).normalize(),'f')
    return str(value)


def comparable_receipt(rows):
    """PR review excludes routing; supplier aliases must identify the same supplier."""
    from rec_runtime import user_root
    from supplier_rules import find_supplier
    from receiving_review import normalized
    try:rules=json.loads((user_root()/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):rules={'suppliers':[]}
    names={};result=[]
    for index,raw in rows:
        value={k:v for k,v in raw.items() if k not in ('Mã kho','Tên kho','Bộ phận')}
        if 'Nhà cung cấp' in value:
            name=str(value['Nhà cung cấp'] or '')
            if name not in names:
                matched=find_supplier(name,rules)
                names[name]=('supplier',matched['id']) if matched else ('name',normalized(name))
            value['Nhà cung cấp']=names[name]
        result.append([index,value])
    return canonical(result)


def comparable_evidence(value):
    result=dict(value)
    result['receipt']=comparable_receipt(value.get('receipt',[]))
    return result


def receipt_inputs(w):
    from receiving_service import invoice_images
    from receiving_document_identity import page_ids
    rows=w.data_by_sheet.get(w.current_sheet,[]);refs=invoice_images(w.current_sheet,rows)
    images=[p for p in getattr(w,'images',[]) if __import__('receiving_image_archive').image_name(p) in refs]
    if images and {__import__('receiving_image_archive').image_name(p) for p in images}!=refs:raise ValueError('Thiếu ảnh phiếu giao')
    prs=w.receipt_references()
    return dict(receipt=canonical([[index,{k:row.get(k) for k in RECEIPT_FIELDS}] for index,row in rows]),
                receipt_images=sorted(page_ids(images).values()) if images else [],
                pr_images=sorted(page_ids(prs).values()) if prs else [])


def evidence(w,saved):
    value=receipt_inputs(w)
    value.update(pr=canonical([{k:item.get(k) for k in PR_FIELDS} for item in saved.get('pr_items',[])]),
                 links=canonical(saved.get('links',{})),conversions=canonical(saved.get('conversions',{})))
    return value


def sources(w):return token(receipt_inputs(w))


def reviewed_snapshot(w,saved,mark):
    return comparable_evidence(evidence(w,saved))==comparable_evidence(mark.get('evidence',{})) if mark.get('version',1)>=4 else legacy_reviewed_snapshot(w,saved,mark)


def inspection(w,path,dirty=False):
    try:mark=json.loads(marker_path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:return dict(state='pending',reason='Chưa xác nhận rà PR')
    except (OSError,ValueError,TypeError):return dict(state='stale',reason='Không đọc được dấu xác nhận PR')
    try:
        saved=json.loads(Path(path).read_text(encoding='utf-8'))
        if dirty:return dict(state='stale',reason='Cặp gán hoặc quy đổi đang thay đổi, chưa lưu')
        if mark.get('version',1)>=4:
            old=mark.get('evidence');current=evidence(w,saved)
            if not isinstance(old,dict) or mark.get('evidence_hash')!=token(old):return dict(state='stale',reason='Dấu xác nhận thiếu hoặc sai dữ liệu; cần phục hồi')
            labels={'receipt':'Nội dung phiếu giao đã đổi','receipt_images':'Ảnh phiếu giao đã đổi',
                    'pr_images':'Bộ ảnh PR đã đổi','pr':'Nội dung PR đã đổi',
                    'links':'Cặp gán dòng đã đổi','conversions':'Quy đổi hoặc xác nhận giá/quy cách đã đổi'}
            old=comparable_evidence(old);current=comparable_evidence(current)
            changes=[labels[k] for k in labels if old.get(k)!=current.get(k)]
            if changes:return dict(state='stale',reason='; '.join(changes),changed=[k for k in labels if old.get(k)!=current.get(k)])
        else:
            from receiving_service import sheet_signature
            from receiving_pr_image_identity import pr_images_match
            if saved.get('signature')!=sheet_signature(w.current_sheet,w.data_by_sheet.get(w.current_sheet,[])):return dict(state='stale',reason='Nội dung phiếu khác bản đối chiếu cũ')
            if not pr_images_match(saved.get('images'),w.receipt_references()):return dict(state='stale',reason='Bộ ảnh PR khác bản đối chiếu cũ')
            if not eligible(saved.get('results',[]),mark.get('scope')=='current_pr'):return dict(state='stale',reason='Bản đối chiếu cũ còn cảnh báo cần xử lý')
            if mark.get('version',1)>=3 and not legacy_source_matches(w,mark.get('receipt_source')):return dict(state='stale',reason='Nguồn khác dấu xác nhận cũ')
            if not legacy_reviewed_snapshot(w,saved,mark):return dict(state='stale',reason='Chưa khôi phục được bằng chứng xác nhận cũ; cần kiểm tra bản lưu')
        return dict(state='partial_done' if mark.get('scope')=='current_pr' and outside_rows(saved.get('results',[])) else 'done',reason='Đã rà PR')
    except (OSError,ValueError,TypeError,KeyError) as exc:return dict(state='stale',reason='Không kiểm chứng được nguồn: '+str(exc))


def state(w,path,dirty=False):return inspection(w,path,dirty)['state']


def review_record(w,saved,scope,reviewed_at):
    data=evidence(w,saved)
    return dict(version=4,scope=scope,reviewed_at=reviewed_at,evidence=data,evidence_hash=token(data))


def migrate(w,path):
    """Explicit one-time migration; state/inspection never write to disk."""
    from receiving_service import atomic_json
    mark=json.loads(marker_path(path).read_text(encoding='utf-8'))
    if mark.get('version',1)>=4:return False
    if inspection(w,path)['state'] not in ('done','partial_done'):return False
    saved=json.loads(Path(path).read_text(encoding='utf-8'))
    updated=review_record(w,saved,mark.get('scope','receipt'),mark.get('reviewed_at'))
    updated['migrated_from']=dict(version=mark.get('version',1),comparison=mark.get('comparison'),decision=mark.get('decision'))
    atomic_json(marker_path(path),updated);return True


def confirm(w,path,results,opened_sources,allow_outside=False):
    from receiving_service import atomic_json
    inputs=receipt_inputs(w)
    if not inputs['receipt_images'] or not inputs['pr_images']:raise ValueError('Thiếu ảnh phiếu hoặc ảnh PR; chưa thể xác nhận.')
    if not eligible(results,allow_outside):raise ValueError('Còn cảnh báo về hàng, giá hoặc quy đổi cần xử lý.')
    if sources(w)!=opened_sources:raise ValueError('Nội dung phiếu hoặc bộ ảnh PR đã đổi. Mở lại đối chiếu.')
    saved=json.loads(Path(path).read_text(encoding='utf-8'))
    if token(saved.get('results'))!=token(results):raise ValueError('Kết quả chưa được lưu đúng. Lưu đối chiếu rồi thử lại.')
    atomic_json(marker_path(path),review_record(w,saved,'current_pr' if allow_outside else 'receipt',datetime.now(timezone.utc).isoformat()))

def label(value):
    return {'done':('✓ Đã rà PR','#15803d'), 'partial_done':('✓ Đã rà PR này · ⚠ Còn dòng ngoài PR chưa rà','#15803d'), 'current_done':('✓ Đã rà lần này · ⚠ Nguồn lần nhận khác cần cập nhật','#15803d'), 'stale':('⚠ Cần rà lại','#b7791f'), 'pending':('Chưa xác nhận rà PR','#64748b')}[value]

def decorate_tab(w,text,diagnostic=None):
    from PySide6.QtGui import QIcon,QPixmap,QPainter,QColor,QFont
    from PySide6.QtCore import Qt
    try:
        diagnostic=diagnostic or inspection(w,w.reference_link_path().with_suffix('.comparison.json'),getattr(w,'pr_dirty',lambda:False)())
        value=diagnostic['state'];w.review_tabs.setTabToolTip(1,diagnostic['reason'])
    except (OSError,ValueError):value='pending'
    if value!='pending':text='PR · '+label(value)[0].replace('✓ ','').replace('⚠ ','')
    w.review_tabs.setTabText(1,text)
    if value=='pending':w.review_tabs.setTabIcon(1,QIcon());return
    w.review_tabs.setTabIcon(1,QIcon(str(Path(__file__).with_name('pr-reviewed.svg' if value in ('done','current_done','partial_done') else 'pr-review-warning.svg'))))

def badge_html(value,reason=None):
    from html import escape
    text,color=label(value)
    if value=='stale' and reason:text='Cần rà: '+reason
    if value=='pending':return escape(text)
    check=Path(__file__).with_name('pr-reviewed.svg').as_posix()
    warning=Path(__file__).with_name('pr-review-warning.svg').as_posix()
    if value=='partial_done':return f'<img src="{check}" width="18" height="18"> <span style="color:#15803d">Đã rà PR này</span> · <img src="{warning}" width="18" height="18"> <span style="color:#b7791f">Còn dòng ngoài PR chưa rà; nguồn các lần nhận khác cần cập nhật</span>'
    if value=='current_done':return f'<img src="{check}" width="18" height="18"> <span style="color:#15803d">Đã rà lần này</span> · <img src="{warning}" width="18" height="18"> <span style="color:#b7791f">Nguồn lần nhận khác cần cập nhật</span>'
    icon=check if value=='done' else warning
    return f'<img src="{icon}" width="18" height="18"> '+escape(text.replace('✓ ','').replace('⚠ ',''))
