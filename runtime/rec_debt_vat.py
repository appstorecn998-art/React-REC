"""Atomic VAT conversion for explicitly selected debt receipt lines."""
from pathlib import Path
import tempfile,os,shutil
from datetime import datetime
from openpyxl import load_workbook
from receiving_service import digest,snapshot
from receiving_vat import convert_row
from multi_delivery import output_lock

def apply(report,expected,selection,rate):
    report=Path(report)
    if not selection:raise ValueError('Chưa chọn dòng cần tách VAT.')
    with output_lock(report):
        if digest(report)!=expected:raise ValueError('Báo cáo đã đổi. Tải lại trước khi tách VAT.')
        book=load_workbook(report);tmp=None;count=0
        try:
            for name,rows in selection.items():
                sheet=book[name];headers={str(c.value or '').strip():c.column for c in sheet[1]}
                for row in rows:
                    if row<2 or not sheet.cell(row,headers['Tên hàng trên phiếu (Ảnh)']).value:raise ValueError('Dòng mặt hàng đã thay đổi.')
                    # Restoring untouched rows is a no-op.
                    if rate==0 and ('Giá NCC gồm VAT gốc' not in headers or sheet.cell(row,headers['Giá NCC gồm VAT gốc']).value is None):continue
                    convert_row(sheet,headers,row,rate);count+=1
            if not count:return 0
            book.calculation.fullCalcOnLoad=True
            fd,tmp=tempfile.mkstemp(dir=report.parent,suffix='.xlsx');os.close(fd);book.save(tmp)
            if digest(report)!=expected:raise ValueError('Báo cáo đã đổi khi lưu VAT.')
            backup=report.parent/'.autowatcher-backups'/('vat-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True);shutil.copy2(report,backup/report.name);os.replace(tmp,report)
            return count
        finally:
            book.close()
            if tmp:Path(tmp).unlink(missing_ok=True)

def defaults(root,report):
    import json
    settings=Path(root)/'vat-ncc.json'
    if not settings.exists():return 0
    rules=json.loads(settings.read_text(encoding='utf-8'));count=0
    # Recheck each workbook signature; each supplier batch is atomic.
    for supplier,rate in rules.items():
        if rate not in (8,10):raise ValueError('Quy tắc VAT NCC không hợp lệ.')
        expected,data=snapshot(report);selection={}
        for name,rows in data:
            selected=[row for row,v in rows if str(v.get('Nhà cung cấp') or '').strip()==supplier and not v.get('Giá NCC gồm VAT gốc')]
            if selected:selection[name]=selected
        if selection:count+=apply(report,expected,selection,rate)
    return count
