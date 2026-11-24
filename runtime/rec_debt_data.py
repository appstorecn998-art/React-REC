"""Separate accounting reconciliation store; no production receiving mutations."""
import json,os,shutil,hashlib,tempfile
from pathlib import Path
from datetime import date
from receiving_service import atomic_json,snapshot

def workspace(destination):
    from receiving_service import accounting_root
    primary=accounting_root(destination).resolve()
    root=primary.parent/'REC_CongNo'
    if root.resolve()==primary:raise ValueError('Thư mục công nợ phải tách khỏi dữ liệu nhận hàng.')
    return root

def profile(root,source,template=None):
    root=Path(root);source=Path(source);target=root/'CauHinh';target.mkdir(parents=True,exist_ok=True)
    for name in ('DanhMuc.xlsm','NhaCungCap.json','Phieu giao hang ngay X.xlsx'):
        src=Path(template) if template and name=='Phieu giao hang ngay X.xlsx' else source/name
        if not src.is_file():raise ValueError('Thiếu cấu hình đọc phiếu: '+name)
        # Refresh an independent configuration snapshot only between runs.
        from rec_runtime import atomic_bytes
        atomic_bytes(target/name,src.read_bytes())
    return target

def reports(root):
    # Only live accounting day folders; never include history/cache workbooks.
    return sorted((Path(root)/'DuLieu').glob('Thang */Ngay */TongHopPhieuNgay_*.xlsx'))


def export(root,target,day):
    from openpyxl import Workbook
    from multi_delivery_export import export_multiple
    import AutoWatcher as aw
    from receiving_service import digest
    root=Path(root);target=Path(target);cfg=root/'CauHinh'
    if target.exists():raise ValueError('File xuất đã tồn tại. Chọn tên mới để giữ bản cũ.')
    from receiving_service import paths
    _,selected=paths(cfg,day,root/'DuLieu')
    sources=[selected] if selected.is_file() else []
    if not sources:raise ValueError('Chưa có phiếu đã đọc để xuất.')
    before={p:digest(p) for p in sources};book=Workbook();book.remove(book.active);count=0;origins={}
    for report in sources:
        for name,rows in snapshot(report)[1]:
            if not rows:continue
            sheet=book.create_sheet('Phieu_'+str(len(book.sheetnames)+1))
            origins[sheet.title]=(report,name,[r for r,_ in rows])
            headers=list(dict.fromkeys(key for _,value in rows for key in value))
            sheet.append(headers)
            for _,value in rows:
                sheet.append([value.get(h) for h in headers]);count+=1
                for cell in sheet[sheet.max_row]:
                    if isinstance(cell.value,str):cell.data_type='s'
    if not count:raise ValueError('Chưa có mặt hàng trong kết quả đọc.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root,prefix='xuat-cong-no-') as td:
        combined=Path(td)/'TongHop.xlsx';book.save(combined);book.close()
        catalog,_=aw.load_catalog_data(cfg/'DanhMuc.xlsm')
        built=Path(td)/'CongNo.xlsx'
        try:
            export_multiple(combined,catalog,cfg/'DanhMuc.xlsm',cfg/'NhaCungCap.json',built,cfg/'Phieu giao hang ngay X.xlsx')
        except ValueError as exc:
            import re
            message=str(exc)
            match=re.search(r'Sheet (Phieu_\d+)(?:, dòng (\d+))?',message)
            if match and match[1] in origins:
                source,name,row_numbers=origins[match[1]]
                message=message.replace('Sheet '+match[1],source.parent.parent.name+' / '+source.parent.name+' · Phiếu '+name,1)
                if match[2]:
                    index=int(match[2])-2
                    if 0<=index<len(row_numbers):message=message.replace('dòng '+match[2], 'dòng '+str(row_numbers[index]),1)
                message=message.replace('Rà TongHop trước khi xuất.','Mở đúng nhóm ngày và phiếu này để bổ sung trước khi xuất.')
            raise ValueError(message) from exc
        if any(digest(p)!=stamp for p,stamp in before.items()):raise ValueError('Dữ liệu công nợ đã đổi; xuất lại để giữ bản mới.')
        with target.open('xb') as out,built.open('rb') as source:shutil.copyfileobj(source,out)
    return count
