"""Atomic manual lines in the isolated debt report."""
from pathlib import Path
import os,tempfile,shutil
from datetime import datetime
from openpyxl import Workbook,load_workbook
from receiving_service import digest,parse_value,EDITABLE
from multi_delivery import output_lock

MANUAL='Phiếu nhập tay'
def save_line(report,expected,title,changes,catalog,day,image='',create=False,position=None,warehouse_directory=None):
    import AutoWatcher as aw
    report=Path(report);report.parent.mkdir(parents=True,exist_ok=True)
    if not title.strip() or len(title)>31 or any(c in title for c in '[]:*?/\\'):
        raise ValueError('Tên phiếu tối đa 31 ký tự, không dùng []:*?/ hoặc dấu gạch chéo ngược.')
    values={k:parse_value(k,str(v)) for k,v in changes.items() if k in EDITABLE}
    if not str(values.get('Tên hàng trên phiếu (Ảnh)') or '').strip():raise ValueError('Nhập tên mặt hàng.')
    code=values.get('Mã vật tư','')
    if code and code!='CHUA CO MA' and code not in catalog:raise ValueError('Mã hàng không có trong danh mục.')
    if 'Mã kho' in values:
        code_kho=values['Mã kho']
        if code_kho and (not warehouse_directory or code_kho not in warehouse_directory):raise ValueError('Kho không có trong DanhMucKho.')
        name,department=warehouse_directory[code_kho] if code_kho else ('','')
        values.update({'Tên kho':name,'Bộ phận':department})
    with output_lock(report):
        current=digest(report) if report.exists() else None
        if current!=expected:raise ValueError('Báo cáo đã đổi. Tải lại trước khi lưu phiếu.')
        book=load_workbook(report) if report.exists() else Workbook();tmp=None
        if current is None:book.remove(book.active)
        try:
            if create:
                if title in book.sheetnames:raise ValueError('Tên phiếu đã tồn tại. Chọn tên khác.')
                # Manual sheets stay first, preserving their creation order.
                index=0
                for existing in book:
                    if MANUAL not in [c.value for c in existing[1]]:break
                    index+=1
                if position is not None:index=position
                sheet=book.create_sheet(title,index)
                sheet.append(list(dict.fromkeys(aw.HEADERS+['Ngày nhận hàng xác nhận','Ảnh nguồn',MANUAL])))
            else:
                sheet=book[title]
                if MANUAL not in [c.value for c in sheet[1]]:raise ValueError('Chỉ thêm dòng vào phiếu nhập tay.')
            headers={c.value:c.column for c in sheet[1] if c.value};row=sheet.max_row+1
            values['Ảnh nguồn']=image
            values.update({MANUAL:'1','Nguồn chọn mã':'Người dùng nhập tay','Trạng thái':'CẦN KIỂM TRA'})
            if create:
                values.setdefault('Ngày nhận hàng xác nhận',day.strftime('%d/%m/%Y'));values['Ảnh nguồn']=image
            if code in catalog:
                values['Tên chuẩn hệ thống'],values['Đơn vị tính']=catalog[code][:2]
            for key,value in values.items():
                if key in headers:
                    cell=sheet.cell(row,headers[key],value)
                    if isinstance(value,str):cell.data_type='s'
            qty=headers['Thực nhận'];price=headers['Đơn giá']
            from openpyxl.utils import get_column_letter as letter
            sheet.cell(row,headers['Thành tiền'],f'={letter(qty)}{row}*{letter(price)}{row}')
            book.calculation.fullCalcOnLoad=True
            fd,tmp=tempfile.mkstemp(dir=report.parent,suffix='.xlsx');os.close(fd);book.save(tmp)
            if (digest(report) if report.exists() else None)!=expected:raise ValueError('Báo cáo đã đổi khi lưu.')
            if report.exists():
                backup=report.parent/'.autowatcher-backups'/('manual-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True);shutil.copy2(report,backup/report.name)
            os.replace(tmp,report)
        finally:
            book.close()
            if tmp:Path(tmp).unlink(missing_ok=True)
