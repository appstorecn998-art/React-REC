"""Manager-facing shortage snapshot, retaining stopped items and user sheets."""
from pathlib import Path
from fractions import Fraction
from datetime import datetime
NAME='Theo dõi giao thiếu'
MARK='REC shortage report v1'

def add(book,ledger_path):
    import receiving_ledger as ledger
    from receiving_validation import check
    from receiving_pr_library import load,library_path
    from openpyxl.styles import Font,PatternFill,Alignment
    path=Path(ledger_path);cache={}
    rows,receipts=ledger.summary(path,lambda p:check(p,cache)) if path.exists() else ([],[])
    metadata=load(library_path(path));suppliers={}
    for receipt in receipts:
        if receipt.get('active') and receipt.get('supplier_name'):suppliers[receipt['order_id']]=receipt['supplier_name']
    if NAME in book:
        if book[NAME]['A2'].value!=MARK:raise ValueError('Sheet Theo dõi giao thiếu đã có nội dung riêng; chưa ghi đè.')
        del book[NAME]
    sheet=book.create_sheet(NAME);sheet.merge_cells('A1:K1');sheet['A1']='THEO DÕI GIAO THIẾU THEO NHÀ CUNG CẤP';sheet['A2']=MARK
    sheet.merge_cells('B2:K2');sheet['B2']='Cập nhật '+datetime.now().strftime('%d/%m/%Y %H:%M')+' · Toàn bộ PR trong sổ REC tại thời điểm xuất'
    sheet.merge_cells('A3:K3');sheet['A3']='Món đã ngừng vẫn giữ số thiếu thực tế và lý do. Nguồn chưa xác minh được ghi rõ, không kết luận lượng còn thiếu.'
    headers=['STT','Nhà cung cấp','Số PR','Ngày PR','Mặt hàng','ĐVT','SL đặt','Đã nhận xác minh','Thiếu thực tế','Trạng thái','Ghi chú / lý do']
    sheet.append(headers);included=[]
    for row in rows:
        unknown=row.get('source_unverified') or row.get('history_unverified') or row.get('remaining') is None
        physical=row.get('physical_remaining')
        if physical is None and not unknown:physical=str(max(Fraction(0),Fraction(row['ordered'])-Fraction(row['received'])))
        if not unknown and Fraction(physical or '0')<=0:continue
        record=metadata.get(row['order_id'],{})
        supplier=suppliers.get(row['order_id']) or record.get('supplier') or 'Chưa xác định NCC'
        status='Cần xác minh nguồn' if unknown else 'Đã ngừng giao bù' if row.get('reason') else 'Chờ giao bù'
        note=row.get('stop_reason') or row.get('reason') or ''
        if unknown:note='; '.join(filter(None,[note,row.get('status'),'Lượng còn thiếu chưa xác minh']))
        def number(v):
            q=Fraction(str(v));return q.numerator if q.denominator==1 else float(q)
        included.append([supplier,str(record.get('number') or row.get('title','')),record.get('date',''),row['name'],row['unit'],number(row['ordered']),None if unknown else number(row['received']),None if unknown else number(physical),status,note])
    included.sort(key=lambda r:(r[0].casefold(),r[1],r[3]))
    for i,values in enumerate(included,1):
        sheet.append([i,*values]);r=sheet.max_row
        for cell in sheet[r]:
            if isinstance(cell.value,str):cell.data_type='s'
            cell.alignment=Alignment(vertical='top',wrap_text=True);cell.font=Font(name='Calibri',size=11)
            cell.fill=PatternFill('solid',fgColor='FFF4DF' if values[8]=='Cần xác minh nguồn' else 'F3EEFF' if values[8]=='Đã ngừng giao bù' else ('F5F8FC' if i%2 else 'FFFFFF'))
        for col in (7,8,9):sheet.cell(r,col).number_format='#,##0.###'
        sheet.row_dimensions[r].height=45
    for cell in sheet[4]:cell.font=Font(name='Calibri',bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='344665');cell.alignment=Alignment(wrap_text=True,vertical='center')
    sheet['A1'].font=Font(name='Calibri',size=16,bold=True,color='26364D');sheet['A2'].font=Font(size=8,color='7A8798');sheet['A3'].alignment=Alignment(wrap_text=True)
    for col,width in zip('ABCDEFGHIJK',(6,32,15,15,45,10,12,16,15,23,45)):sheet.column_dimensions[col].width=width
    sheet.row_dimensions[3].height=32;sheet.row_dimensions[4].height=32;sheet.freeze_panes='E5';sheet.auto_filter.ref=f'A4:K{max(4,sheet.max_row)}'
    sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0;sheet.print_title_rows='1:4'
    return len(included)

def update_file(path,ledger_path):
    import os,tempfile,shutil
    from openpyxl import load_workbook
    from receiving_service import digest
    from multi_delivery import output_lock
    path=Path(path)
    with output_lock(path):
        before=digest(path);book=load_workbook(path);tmp=None
        try:
            count=add(book,ledger_path)
            fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.xlsx');os.close(fd);book.save(tmp)
            if digest(path)!=before:raise ValueError('Báo cáo vừa thay đổi; chưa cập nhật sheet giao thiếu.')
            backup=path.parent/'.rec-report-backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');backup.mkdir(parents=True);shutil.copy2(path,backup/path.name)
            os.replace(tmp,path);return count
        finally:
            book.close()
            if tmp:Path(tmp).unlink(missing_ok=True)
