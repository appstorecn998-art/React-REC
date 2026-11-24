"""Provisional packages are isolated from official exports and all approval state."""
from pathlib import Path
import tempfile,shutil,json,os
from receiving_service import snapshot,digest,day_directory,atomic_json

def pending(w):
    import receiving_ledger as ledger
    from receiving_validation import check
    cache={};_,history=ledger.summary(w.ledger_path(),getattr(w,'validate_ledger',None) or (lambda p:check(p,cache)))
    resolve_report=getattr(w,'resolve_report',lambda p:Path(p))
    found={(str(resolve_report(r['report']).resolve()).casefold(),r['sheet']):r for r in history if r['active']}
    from receiving_no_po import active
    result=[]
    for sheet,rows in w.data:
        reasons=[]
        if not w.approved(sheet):reasons.append('chưa kiểm xong phiếu giao')
        no_po=active(w.folder,sheet,rows,w.images)
        r=found.get((str(Path(w.report).resolve()).casefold(),sheet))
        from receiving_pending_pr import read as pending_pr
        waiting=pending_pr(w.folder,sheet,rows,w.images)
        if not no_po and not waiting and (not r or not r['valid']):reasons.append('chưa ghi sổ' if not r else 'nguồn ghi sổ cần cập nhật')
        if reasons:result.append((sheet,'; '.join(reasons)))
    return result

def export(root,day,destination,report,desktop=None,validate=None):
    import AutoWatcher as aw
    from multi_delivery_export import export_multiple
    from multi_delivery import output_lock
    from receiving_daily_report import build,stage_images
    from receiving_export_distribution import distribute
    from openpyxl import load_workbook
    root=Path(root);report=Path(report);folder=day_directory(destination,day);folder.mkdir(parents=True,exist_ok=True)
    suffix=' - BẢN TẠM';invoice=f'Phieu giao hang {day.day}-{day.month}-{day.year}{suffix}.xlsx';daily=f'Cong viec hang ngay {day.day}-{day.month}-{day.year}{suffix}.xlsx'
    manifest=folder/'.receiving/published-temporary.json'
    with output_lock(report):
        if validate:validate()
        original=digest(report);old=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {};previous=old.get(str(folder.resolve()),{})
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td);catalog,_=aw.load_catalog_data(root/'DanhMuc.xlsm')
            try:template=aw.delivery_template_path(folder)
            except FileNotFoundError:template=root/'Phieu giao hang ngay X.xlsx'
            source=stage/report.name
            shutil.copy2(report,source)
            export_multiple(source,catalog,root/'DanhMuc.xlsm',root/'NhaCungCap.json',stage/invoice,template)
            for name in [invoice]:
                book=load_workbook(stage/name)
                for sheet in book:
                    sheet.oddHeader.center.text='BẢN TẠM — CHƯA HOÀN TẤT KIỂM/GHI SỔ'
                book.save(stage/name);book.close()
            photos=stage_images(report,stage);names=[invoice]+photos
            for name in names:
                target=folder/name
                if target.exists() and digest(target)!=previous.get('files',{}).get(name) and digest(target)!=digest(stage/name):raise ValueError('File đã có hoặc sửa riêng: '+str(target))
            if digest(report)!=original:raise ValueError('Nguồn vừa thay đổi, chưa xuất bản tạm.')
            if validate:validate()
            backup=stage/'backup';backup.mkdir();replaced=[]
            try:
                for index,name in enumerate(names):
                    target=folder/name;target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists():shutil.copy2(target,backup/str(index))
                    aw.atomic_copy_file(stage/name,target);replaced.append((index,target))
                old[str(folder.resolve())]=dict(source_report=str(report.resolve()),source=original,image_files=photos,files={n:digest(folder/n) for n in names})
                atomic_json(manifest,old)
            except Exception:
                for index,target in reversed(replaced):
                    if (backup/str(index)).exists():shutil.copy2(backup/str(index),target)
                    else:target.unlink(missing_ok=True)
                raise
        distribute(folder,day,desktop=desktop,provisional=True)
    return folder
