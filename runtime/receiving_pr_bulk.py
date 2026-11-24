from receiving_image_archive import image_name, source_digest
"""Refresh existing PR comparisons without OCR, confirmations or ledger writes."""
import json,hashlib
from pathlib import Path
from receiving_service import digest,sheet_signature,invoice_images,atomic_json
from receiving_pr import compare
from receiving_pr_library import load,images_for

def prepare(folder,report,sheets,images,directory):
    report_hash=digest(report);records=load(directory);changes=[];skipped=[];manual=[]
    from receiving_no_po import active
    for sheet,rows in sheets:
        if active(folder,sheet,rows,images):manual.append((sheet,'Không có PR/PO — theo dõi thiếu hàng thủ công trên Sheets'));continue
        refs=invoice_images(sheet,rows);source=[p for p in images if image_name(p) in refs]
        if not source or {image_name(p) for p in source}!=refs:skipped.append((sheet,'Thiếu ảnh nguồn'));continue
        identities=sorted((image_name(p),source_digest(p)) for p in source)
        key=hashlib.sha256(json.dumps(identities).encode()).hexdigest()
        link=Path(folder)/'.receiving/manual-pr-links'/(key+'.json');path=link.with_suffix('.comparison.json')
        try:
            if not link.exists():
                legacy=sorted((image_name(p),digest(p)) for p in source)
                legacy_key=hashlib.sha256(json.dumps(legacy).encode()).hexdigest()
                link=link.with_name(legacy_key+'.json');path=link.with_suffix('.comparison.json')
            if not link.exists():raise ValueError('Chưa chọn PR cho phiếu')
            original=link.read_bytes();selection=json.loads(original)
            if selection.get('source')=='pr-library':
                record=records[selection['library_key']]
                if record['images']!=selection.get('paths'):raise ValueError('Bộ ảnh PR đã đổi')
                prs=images_for(record);items=record['items']
            else:
                prs=[p for p in images if {image_name(n):v for n,v in selection.get('images',{}).items()}.get(image_name(p)) in (source_digest(p),digest(p))]
                if len(prs)!=len(selection.get('images',{})):raise ValueError('Ảnh PR đã đổi')
                from receiving_pr_library import identity
                record=records.get(identity(prs,directory))
                if not record:raise ValueError('PR chưa có trong thư viện; đối chiếu riêng trước')
                items=record['items']
            if not prs:raise ValueError('Chưa chọn PR')
            signature=sheet_signature(sheet,rows);hashes={image_name(p):source_digest(p) for p in prs}
            saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            links={int(k):v for k,v in saved.get('links',{}).items()};conversions={int(k):v for k,v in saved.get('conversions',{}).items()}
            if saved and (saved.get('signature')!=signature or not __import__('receiving_pr_image_identity').pr_images_match(saved.get('images'),prs)):raise ValueError('Nguồn đổi, cần rà lại gán tay/quy đổi')
            if saved.get('pr_items') and saved['pr_items']!=items:raise ValueError('Nội dung PR đổi, cần rà lại riêng')
            results=compare(items,rows,links,conversions)
            payload=dict(version=1,signature=signature,images=hashes,links=links,conversions=conversions,pr_items=items,results=results)
            changes.append(dict(sheet=sheet,path=path,before=path.read_bytes() if path.exists() else None,link=link,link_bytes=original,images={str(p):digest(p) for p in source+prs},payload=payload,review=sum(bool(set(r.get('alerts',[]))-{'short','previous_receipt_invalid'}) or ('pr_index' not in r and not r.get('deposit')) for r in results)))
        except (OSError,ValueError,KeyError,TypeError) as exc:skipped.append((sheet,str(exc)))
    if digest(report)!=report_hash:raise ValueError('Báo cáo vừa đổi. Chưa cập nhật.')
    return dict(report=Path(report),report_hash=report_hash,changes=changes,skipped=skipped,manual=manual)

def apply(preview):
    from datetime import datetime
    import shutil
    def unchanged(c):
        return c['link'].read_bytes()==c['link_bytes'] and (c['path'].read_bytes() if c['path'].exists() else None)==c['before'] and all(Path(p).is_file() and digest(p)==h for p,h in c['images'].items())
    if digest(preview['report'])!=preview['report_hash'] or not all(unchanged(c) for c in preview['changes']):raise ValueError('Nguồn đã đổi; chạy cập nhật lại.')
    backup=preview['report'].parent/'.autowatcher-backups'/('bulk-pr-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for c in preview['changes']:
        if digest(preview['report'])!=preview['report_hash'] or not unchanged(c):raise ValueError('Nguồn thay đổi; dừng cập nhật, kết quả đã lưu vẫn giữ.')
        if c['path'].exists():backup.mkdir(parents=True,exist_ok=True);shutil.copy2(c['path'],backup/c['path'].name)
        atomic_json(c['path'],json.loads(json.dumps(c['payload'],default=str)))
    return len(preview['changes'])
