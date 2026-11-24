"""Atomic whole-receipt receiving time/warehouse edits; preserve all other fields."""
import os,shutil,tempfile
from pathlib import Path
from datetime import datetime
from openpyxl import load_workbook
from receiving_service import digest,parse_value
from multi_delivery import output_lock

def save(report,expected,sheet_name,changes,directory):
    if not isinstance(changes,dict) or not changes or set(changes)-{'receiptTime','warehouseCode','supplierName'}:raise ValueError('Chỉ lưu tên nhà cung cấp, giờ nhận và kho/bộ phận.')
    parsed={}
    if 'receiptTime' in changes:
        if not isinstance(changes['receiptTime'],str):raise ValueError('Giờ nhận không hợp lệ.')
        try:parsed['Giờ nhận']=parse_value('Thời gian chụp',changes['receiptTime'])
        except ValueError:raise ValueError('Giờ nhận không hợp lệ; nhập HH:mm từ 00:00 đến 23:59.') from None
    if 'supplierName' in changes:
        value=changes['supplierName']
        if not isinstance(value,str) or not value.strip():raise ValueError('Tên nhà cung cấp không được để trống.')
        parsed['Nhà cung cấp']=value.strip()
    if 'warehouseCode' in changes:
        code=changes['warehouseCode']
        if not isinstance(code,str) or (code and code not in directory):raise ValueError('Chọn mã kho có trong danh mục.')
        name,department=directory[code] if code else ('','')
        parsed.update({'Mã kho':code,'Tên kho':name,'Bộ phận':department})
    sheets=sheet_name if isinstance(sheet_name,list) else [sheet_name]
    if not sheets or any(not isinstance(name,str) or not name for name in sheets) or len(set(sheets))!=len(sheets):
        raise ValueError('Chọn ít nhất một phiếu; danh sách phiếu không được trùng.')
    if isinstance(sheet_name,list) and set(changes)!={'receiptTime'}:
        raise ValueError('Chỉ đặt giờ nhận cho nhiều phiếu.')
    report=Path(report)
    with output_lock(report):
        if digest(report)!=expected:raise ValueError('Báo cáo đã đổi. Tải lại trước khi lưu để giữ sửa tay mới nhất.')
        book=load_workbook(report);temporary=None
        try:
            for name in sheets:
                if name not in book:raise ValueError('Phiếu không còn trong báo cáo.')
                sheet=book[name];headers={str(c.value or '').strip():c.column for c in sheet[1]}
                name_col=headers.get('Tên hàng trên phiếu (Ảnh)')
                if name_col is None:raise ValueError('Phiếu thiếu cột tên hàng.')
                rows=[r for r in range(2,sheet.max_row+1) if sheet.cell(r,name_col).value]
                if not rows:raise ValueError('Phiếu không có dòng hàng.')
                for header,value in parsed.items():
                    if header not in headers:headers[header]=sheet.max_column+1;sheet.cell(1,headers[header],header)
                    for r in rows:
                        cell=sheet.cell(r,headers[header]);cell.value=value;cell.data_type='s'
            fd,temporary=tempfile.mkstemp(dir=report.parent,suffix='.xlsx');os.close(fd);book.save(temporary)
            if digest(report)!=expected:raise ValueError('Báo cáo vừa đổi khi lưu; tải lại để tiếp tục.')
            backup=report.parent/'.autowatcher-backups'/('web-metadata-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True)
            shutil.copy2(report,backup/report.name);os.replace(temporary,report)
        finally:
            book.close()
            if temporary:Path(temporary).unlink(missing_ok=True)
