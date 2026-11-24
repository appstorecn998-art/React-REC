"""Distribute approved daily exports to the manager folder and desktop ZIP."""
from pathlib import Path
import json,shutil,tempfile,os,zipfile
from datetime import datetime
from receiving_service import digest,atomic_json

def destinations(day,desktop=None,provisional=False):
    desktop=Path(desktop or Path.home()/'Desktop')
    root=desktop/'Công việc/Kế toán/Báo cáo công việc'
    # Existing 2026 folder is retained. Future/past years never share it.
    month=(root if day.year==2026 else root/f'Năm {day.year}')/f'Tháng {day.month}'
    suffix=' - BẢN TẠM' if provisional else ''
    return month/f'Công việc hằng ngày {day.day:02d}-{day.month:02d}-{day.year}{suffix}.xlsx',desktop/f'Phiếu giao hàng {day.day:02d}-{day.month:02d}-{day.year}{suffix}.zip'

def distribute(folder,day,desktop=None,provisional=False):
    folder=Path(folder);suffix=' - BẢN TẠM' if provisional else ''
    report=folder/f'TongHopPhieuNgay_{day:%d-%m-%Y}.xlsx'
    invoice=folder/f'Phieu giao hang {day.day}-{day.month}-{day.year}{suffix}.xlsx'
    record_path=folder/('.receiving/export-distribution-temporary.json' if provisional else '.receiving/export-distribution.json')
    published=folder/('.receiving/published-temporary.json' if provisional else '.receiving/published.json')
    records=json.loads(published.read_text(encoding='utf-8')) if published.exists() else {}
    record=records.get(str(folder.resolve()),{})
    report=Path(record.get('source_report') or report)
    photos=record.get('image_files',[])
    if not invoice.is_file():raise ValueError('Thiếu file phiếu đã xuất.')
    if not photos:raise ValueError('Chưa có danh sách ảnh phiếu đã kiểm chứng; xuất lại bộ phiếu trước.')
    for name in photos:
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or path.parent.name!='Phiếu giao hàng':raise ValueError('Đường dẫn ảnh xuất không hợp lệ.')
        if not path.is_file() or digest(path)!=record['files'].get(name):raise ValueError('Ảnh xuất đã đổi hoặc thiếu: '+name)
    manager,archive=destinations(day,desktop,provisional);old=json.loads(record_path.read_text(encoding='utf-8')) if record_path.exists() else {}
    outputs=[manager,archive];inputs={str(p):digest(p) for p in [report,invoice]+[folder/n for n in photos]}
    if manager.exists():
        from receiving_manager_shortages import update_file
        update_file(manager,folder.parent.parent/'.receiving/receiving-ledger.sqlite')
    if old.get('inputs')==inputs and all(p.is_file() for p in outputs):return outputs
    for p in [archive]:
        if p.exists() and digest(p)!=old.get('files',{}).get(str(p)):raise ValueError('File đã có hoặc được sửa riêng, chưa ghi đè: '+str(p))
    backup=folder/'.receiving/publish-backups'/('distribution-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=backup) as td:
        td=Path(td);staged=[td/'daily.xlsx',td/'delivery.zip']
        # Existing manager workbooks belong to the user, including all hand edits.
        preserve_manager=manager.exists()
        if not preserve_manager:
            from receiving_daily_report import build
            build(report,staged[0],day)
            if provisional:
                from openpyxl import load_workbook
                book=load_workbook(staged[0])
                for sheet in book:sheet.oddHeader.center.text='BẢN TẠM — CHƯA HOÀN TẤT KIỂM/GHI SỔ'
                book.save(staged[0]);book.close()
        with zipfile.ZipFile(staged[1],'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.write(invoice,invoice.name)
            for name in photos:z.write(folder/name,Path(name).as_posix())
            if record.get('pending_pr_notes'):z.writestr('Cho PR thay the.txt','\n'.join(record['pending_pr_notes']).encode('utf-8-sig'))
        with zipfile.ZipFile(staged[1]) as z:
            if z.testzip() is not None:raise ValueError('ZIP kiểm tra không đạt.')
            assert len(z.namelist())==len(photos)+1+bool(record.get('pending_pr_notes'))
        if any(digest(Path(name))!=h for name,h in inputs.items()):raise ValueError('Nguồn thay đổi trong lúc tạo ZIP; chưa phát hành.')
        replaced=[]
        try:
            for i,(source,target) in enumerate(zip(staged,outputs)):
                if i==0 and (preserve_manager or target.exists()):continue
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():shutil.copy2(target,backup/str(i))
                fd,tmp=tempfile.mkstemp(dir=target.parent,suffix='.tmp');os.close(fd)
                try:shutil.copy2(source,tmp);os.replace(tmp,target)
                finally:Path(tmp).unlink(missing_ok=True)
                replaced.append((i,target))
            atomic_json(record_path,dict(inputs=inputs,files={str(p):digest(p) for p in outputs}))
        except Exception:
            for i,p in reversed(replaced):
                if (backup/str(i)).exists():shutil.copy2(backup/str(i),p)
                else:p.unlink(missing_ok=True)
            raise
    return outputs
