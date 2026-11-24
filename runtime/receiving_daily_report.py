"""Daily manager workbook using the supplied template and saved receipt rows."""
from pathlib import Path
from copy import copy
from datetime import datetime,time
from openpyxl import load_workbook
from openpyxl.styles import Alignment

def build(report,output,day,template=None):
    from receiving_service import snapshot,display_rows,day_images,invoice_images
    from receiving_image_archive import image_name
    from receiving_capture_time import capture_time
    import json
    originals=None
    try:originals=Path(json.loads((Path(__import__('rec_runtime').user_root())/'.receiving/inbox-settings.json').read_text())['source'])
    except (OSError,ValueError,KeyError):pass
    images=day_images(Path(report).parent)
    template=Path(template or Path(__file__).with_name('daily-work-template.xlsx'))
    book=load_workbook(template);checklist=book['Công việc hằng ngày'];sheet=book['Nhật Ký Nhận Hàng']
    for row in range(5,checklist.max_row+1):
        checklist.cell(row,5).value=None;checklist.cell(row,6).value=None
    styles={col:copy(sheet.cell(5,col)._style) for col in range(1,13)}
    for merged in list(sheet.merged_cells):sheet.unmerge_cells(str(merged))
    for row in sheet.iter_rows(min_row=5):
        for cell in row:cell.value=None
    sheet['D1']=datetime.combine(day,datetime.min.time());sheet['D1'].number_format='dd/mm/yyyy'
    sheet.freeze_panes=None;current=5;count=0
    for name,raw in snapshot(report)[1]:
        if not raw:continue
        count+=1;start=current;rows=display_rows(raw)
        times=[str(v.get('Thời gian chụp') or '') for _,v in rows if v.get('Thời gian chụp')]
        if not times:
            refs=invoice_images(name,raw)
            times=[capture_time(p,originals) for p in images if image_name(p) in refs]
        hour=None
        for value in times:
            try:hour=time.fromisoformat(value);break
            except ValueError:continue
        first=rows[0][1]
        for _,values in rows:
            quantity=values.get('Thực nhận');price=values.get('Đơn giá')
            code,name=journal_item(values)
            data=[count,hour,values.get('Nhà cung cấp'),values.get('Ngày giao hàng'),code,name,str(values.get('Đơn vị tính') or '').strip().capitalize(),quantity,price,None,values.get('Bộ phận'),str(values.get('Mã kho') or '')]
            for col,value in enumerate(data,1):
                cell=sheet.cell(current,col);cell._style=copy(styles[col]);cell.value=value
                if isinstance(value,str):cell.data_type='s'
                cell.alignment=Alignment(horizontal='left' if col in (3,6) else 'center',vertical='center',wrap_text=True)
            value=sheet.cell(current,4).value
            if isinstance(value,str):
                for fmt in ('%Y-%m-%d','%d/%m/%Y'):
                    try:sheet.cell(current,4).value=datetime.strptime(value,fmt);break
                    except ValueError:pass
            sheet.cell(current,10,f'=H{current}*I{current}')
            sheet.cell(current,1).number_format='00';sheet.cell(current,2).number_format='hh:mm';sheet.cell(current,4).number_format='dd/mm/yyyy'
            for col in (5,12):sheet.cell(current,col).number_format='@'
            for col in (8,9,10):sheet.cell(current,col).number_format='#,##0.00'
            from delivery_export import quantity_format
            sheet.cell(current,8).number_format=quantity_format(quantity)
            sheet.cell(current,9).number_format=quantity_format(price)
            from decimal import Decimal
            amount=(Decimal(str(quantity))*Decimal(str(price)) if quantity is not None and price is not None else None)
            sheet.cell(current,10).number_format=quantity_format(amount)
            sheet.row_dimensions[current].height=max(30,15*(1+len(str(data[5]))//48))
            current+=1
        for col in range(1,5):
            sheet.cell(start,col).value=[count,hour,first.get('Nhà cung cấp'),sheet.cell(start,4).value][col-1]
            if current-start>1:sheet.merge_cells(start_row=start,end_row=current-1,start_column=col,end_column=col)
    if sheet.max_row>=current:sheet.delete_rows(current,sheet.max_row-current+1)
    sheet.print_area=f'A1:L{max(5,current-1)}';sheet.print_title_rows='1:4'
    reset_journal_view(sheet)
    from receiving_manager_shortages import add
    add(book,report.parent.parent.parent/'.receiving/receiving-ledger.sqlite')
    book.save(output);book.close();return count

def stage_images(report,stage):
    from receiving_service import snapshot,day_images,invoice_images,digest,accounting_root
    from receiving_image_archive import image_name,source_digest
    from receiving_preferences import nickname
    from rec_runtime import user_root
    from receiving_pr_library import load,images_for
    import shutil,re,json,hashlib
    report=Path(report);available=day_images(report.parent);result=[]
    directory=accounting_root(report.parent.parent.parent)/'.receiving/pr-library'
    for number,(sheet,rows) in enumerate(((n,r) for n,r in snapshot(report)[1] if r),1):
        refs=invoice_images(sheet,rows)
        sources=[p for p in available if image_name(p) in refs]
        explicit=any(v.get('Ảnh nguồn') or v.get('Các ảnh cùng phiếu') for _,v in rows)
        if not sources or explicit and {image_name(p) for p in sources}!=refs:raise ValueError('Thiếu ảnh phiếu: '+sheet)
        unique={}
        for path in sources:
            key=image_name(path)
            if key in unique and digest(unique[key])!=digest(path):raise ValueError('Ảnh trùng tên khác nội dung: '+key)
            unique[key]=path
        sources=list(unique.values())
        suppliers={str(v.get('Nhà cung cấp') or '').strip() for _,v in rows}-{''}
        supplier=next(iter(suppliers)) if len(suppliers)==1 else 'Chưa rõ NCC'
        label=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',nickname(user_root(),supplier) or supplier).strip().rstrip('. ')[:90] or 'Chưa rõ NCC'
        # Read the same verified link selection as the app; never guess PR by NCC.
        identities=sorted((image_name(p),source_digest(p)) for p in sources)
        legacy=sorted((image_name(p),digest(p)) for p in sources)
        link=None
        for values in [identities,legacy]:
            key=hashlib.sha256(json.dumps(values).encode()).hexdigest()
            candidate=report.parent/'.receiving/.receiving/manual-pr-links'/(key+'.json')
            if candidate.exists():link=candidate;break
        prs=[]
        if link:
            selected=json.loads(link.read_text(encoding='utf-8'))
            if selected.get('source')=='pr-library':
                records=load(directory);record=records.get(selected.get('library_key'))
                if not record or record['images']!=selected.get('paths'):raise ValueError('Liên kết PR đã đổi: '+sheet)
                prs=images_for(record)
            else:
                hashes={image_name(k):v for k,v in selected.get('images',{}).items()}
                prs=[p for p in available if hashes.get(image_name(p)) in (source_digest(p),digest(p))]
                if len(prs)!=len(hashes):raise ValueError('Thiếu ảnh PR đã ghép: '+sheet)
        for kind,images in [(' - Phiếu giao',sources),(' - PR',prs)]:
            for page,path in enumerate(images,1):
                suffix=(' - Trang '+str(page).zfill(2)) if len(images)>1 else ''
                relative=Path('Phiếu giao hàng')/export_photo_name(number,label,kind,suffix,path.suffix.lower(),len(images),page)
                target=Path(stage)/relative;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():raise ValueError('Tên ảnh xuất bị trùng: '+str(relative))
                shutil.copy2(path,target);result.append(str(relative))
    return result


def reset_journal_view(sheet):
    """Discard the template's saved scroll/selection outside the new data."""
    from openpyxl.worksheet.views import Selection
    sheet.sheet_view.topLeftCell='A1'
    sheet.freeze_panes=None
    sheet.sheet_view.selection=[Selection(activeCell='A1',sqref='A1')]



def export_photo_name(number,label,kind,suffix,extension,page_count,page=1):
    page_suffix=(' - Trang '+str(page).zfill(2)) if page_count>1 else suffix
    order='01' if kind.strip(' -')=='Phiếu giao' else '02'
    return f'{number:03d}.{label} - {order} {kind.strip(" -")}{page_suffix}{extension}'


def journal_item(values):
    """Use the same unknown-code fallback and name formatting as the delivery form."""
    from delivery_export import vietnamese_item_name
    code=str(values.get('Mã vật tư') or '').strip()
    unknown=not code or code=='CHUA CO MA'
    if unknown:
        english=str(values.get('Tên tiếng Anh trên phiếu') or '').strip()
        vietnamese=str(values.get('Tên tiếng Việt trên phiếu') or '').strip()
        name=f'{english}/{vietnamese}' if english and vietnamese else english or vietnamese or values.get('Tên hàng trên phiếu (Ảnh)')
    else:
        name=values.get('Tên chuẩn hệ thống') or values.get('Tên hàng trên phiếu (Ảnh)')
    return ('' if unknown else code),vietnamese_item_name(name)
