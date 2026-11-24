"""Ghép phiếu theo xác nhận tên ảnh; không gọi AI hoặc suy quan hệ từ STT."""
from copy import copy
import hashlib
import os
from pathlib import Path
import re
import tempfile

from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
import AutoWatcher as aw

GROUP_HEADER='Các ảnh cùng phiếu'
SOURCE_HEADER='Ảnh nguồn'
TOTAL_HEADER='Tổng tiền phiếu (cộng Thành tiền)'
LINK_PATTERN=r'\s+(?:thuộc|thuoc)\s+(?:phiếu|phieu)\s+giao\s+(?:hàng|hang)\s+trong\s+(?:ảnh|anh)\s+'


def image_names(value):
    return list(dict.fromkeys(part.strip().strip('"\'() ') for part in
                             re.split(r'[,;\n]+',str(value or '')) if part.strip()))


def valid_image_reference(name):
    return bool(name and Path(name).name==name and name not in {'.','..'}
                and ('/' not in name and '\\' not in name)
                and (not Path(name).suffix or Path(name).suffix.lower() in aw.IMAGE_EXTENSIONS))


def parse_receipt_input(answer):
    parts=re.split(LINK_PATTERN,answer.strip(),maxsplit=1,flags=re.IGNORECASE)
    received=aw.choose_delivery_date(parts[0]) if parts[0] else aw.datetime.now().date()
    refs=image_names(parts[1]) if len(parts)>1 else []
    if len(parts)>1 and (not refs or any(not valid_image_reference(name) for name in refs)):
        raise ValueError('Nhập tên ảnh, ví dụ IMG_4098 (không cần đuôi); nhiều tên ngăn bằng dấu phẩy.')
    return received,refs


def headers(sheet):
    return {aw.text(cell.value):cell.column for cell in sheet[1] if aw.text(cell.value)}


def sheet_images(sheet):
    columns=headers(sheet)
    result=[]
    for header in (GROUP_HEADER,SOURCE_HEADER):
        if header in columns:
            for row in sheet.iter_rows(min_row=2,min_col=columns[header],max_col=columns[header],values_only=True):
                result.extend(image_names(row[0]))
    return list(dict.fromkeys(result))


def find_sheets(workbook,refs):
    result=[]
    index=[(sheet,sheet_images(sheet)) for sheet in workbook]
    for ref in refs:
        if not valid_image_reference(ref):raise ValueError(f'Tên ảnh không hợp lệ: {ref}')
        if not Path(ref).suffix:
            candidates={name.casefold():name for _,names in index for name in names
                        if Path(name).stem.casefold()==ref.casefold()}
            if len(candidates)>1:
                raise ValueError(f'Tên {ref} trùng nhiều định dạng: '+', '.join(candidates.values())+'. Nhập kèm đuôi để chọn đúng ảnh.')
            exact=next(iter(candidates),'')
        else:exact=ref.casefold()
        matches=[sheet for sheet,names in index if exact in {name.casefold() for name in names}]
        if len(matches)!=1:
            reason='chưa được lưu trong TongHop' if not matches else 'xuất hiện ở nhiều sheet'
            raise ValueError(f'Ảnh {ref} {reason}. Kiểm tra tên ảnh rồi nhập lại; chưa ghép/lưu phiếu.')
        if matches[0] not in result:result.append(matches[0])
    return result


def commit_merge(report,temporary,expected_digest,retry_write=None):
    """Giữ file tạm qua lỗi khóa; kiểm nguồn mỗi lần thử lại, không ghi đè sửa mới."""
    backup=None
    while True:
        try:
            if aw.delivery_report_digest(report)!=expected_digest:
                raise ValueError('TongHop thay đổi trong lúc ghép/chờ ghi. Chọn lại nhóm để rà dữ liệu mới; chưa ghi đè.')
            if backup is None:
                destination=report.parent/'.autowatcher-backups'/('manual-group-'+aw.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))/report.name
                aw.atomic_copy_file(report,destination)
                backup=destination
            os.replace(temporary,report)
            return
        except PermissionError as exc:
            if retry_write is None or not retry_write(exc):raise


def check_references(report,refs,received):
    if not refs:return
    if not report.is_file():raise ValueError('Chưa có phiếu đã lưu để ghép. Đọc/lưu ảnh đầu trước.')
    workbook=load_workbook(report)
    try:
        for sheet in find_sheets(workbook,refs):
            column=headers(sheet).get('Ngày nhận hàng xác nhận')
            if column:
                for row in sheet.iter_rows(min_row=2,min_col=column,max_col=column,values_only=True):
                    value=row[0]
                    if value in (None,''):continue
                    if type(value) in (int,float):value=aw.from_excel(value,epoch=workbook.epoch)
                    if aw.parse_delivery_date(value)!=received:
                        raise ValueError(f'Ngày nhận khác phiếu {sheet.title}. Nhập cùng ngày nhận hoặc rà lại ngày trong TongHop trước; chưa đổi dữ liệu cũ.')
    finally:workbook.close()


def group_title(names,occupied=()):
    stems=list(dict.fromkeys(Path(name).stem for name in names))
    title='+'.join(stems)
    if len(title)>31:
        prefix=stems[0][:stems[0].rfind('_')+1] if '_' in stems[0] else ''
        if not all(stem.startswith(prefix) for stem in stems):prefix=''
        title=prefix+'+'.join(stem[len(prefix):] for stem in stems)
    title=re.sub(r'[\[\]:*?/\\]','_',title).strip("'") or 'Phieu'
    if len(title)>31:
        suffix=hashlib.sha256(';'.join(names).encode('utf-8')).hexdigest()[:5]
        title=title[:25]+'~'+suffix
    base=title
    index=1
    while title.casefold() in {name.casefold() for name in occupied}:
        index+=1
        tail=f' ({index})'
        title=base[:31-len(tail)]+tail
    return title


def merge_sheets(workbook,sheets):
    # Thứ tự đang lưu giữ nguyên: trang đầu đứng trước trang ghép thêm.
    sheets=sorted(set(sheets),key=lambda s:workbook.index(s))
    target=sheets[0]
    old_titles={s.title for s in sheets}
    # Không đổi tên/xóa sheet đang được công thức có tên sheet tham chiếu.
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                if cell.data_type=='f' and any(re.search(r"(?:'"+re.escape(title)+r"'|(?<![\w'])"+re.escape(title)+r")!",cell.value,re.I) for title in old_titles):
                    raise ValueError('Có công thức tham chiếu tên sheet cần ghép; giữ file gốc, cần rà công thức trước.')
    mapping=headers(target)
    for sheet in sheets:
        if sheet.merged_cells.ranges:
            raise ValueError('Sheet có ô gộp thủ công; chưa ghép để tránh mất bố cục.')
        for name in headers(sheet):
            if name not in mapping:
                mapping[name]=target.max_column+1
                target.cell(1,mapping[name],name)
    all_names=[]
    for sheet in sheets:all_names.extend(sheet_images(sheet))
    all_names=list(dict.fromkeys(all_names))
    for sheet in sheets[1:]:
        source_columns=headers(sheet)
        name_column=source_columns.get('Tên hàng trên phiếu (Ảnh)')
        if not name_column:raise ValueError(f'Sheet {sheet.title} thiếu cột tên hàng; chưa ghép.')
        for source_row in range(2,sheet.max_row+1):
            if not aw.text(sheet.cell(source_row,name_column).value):continue
            destination_row=target.max_row+1
            for name,source_column in source_columns.items():
                if name==TOTAL_HEADER:continue
                source=sheet.cell(source_row,source_column)
                destination=target.cell(destination_row,mapping[name])
                value=source.value
                if source.data_type=='f':
                    value=Translator(value,origin=source.coordinate).translate_formula(destination.coordinate)
                destination.value=value
                destination.data_type=source.data_type
                destination._style=copy(source._style)
                destination.comment=copy(source.comment)
                if source.hyperlink:destination._hyperlink=copy(source.hyperlink)
            target.row_dimensions[destination_row].height=sheet.row_dimensions[source_row].height
        workbook.remove(sheet)
    if GROUP_HEADER not in mapping:
        mapping[GROUP_HEADER]=target.max_column+1
        target.cell(1,mapping[GROUP_HEADER],GROUP_HEADER)
    for row_number in range(2,target.max_row+1):
        cell=target.cell(row_number,mapping[GROUP_HEADER],'; '.join(all_names))
        cell.data_type='s'
    # Tổng cũ của từng trang chỉ thay bằng một tổng cho toàn phiếu.
    total=mapping.get(TOTAL_HEADER)
    if total:
        for row in range(2,target.max_row+1):target.cell(row,total).value=None
    from received_amounts import apply_received_amounts
    apply_received_amounts(target)
    aw.add_invoice_total(target)
    target.title=group_title(all_names,[s.title for s in workbook if s is not target])
    workbook.calculation.calcMode='auto'
    workbook.calculation.fullCalcOnLoad=True
    workbook.calculation.forceFullCalc=True
    return target.title


def save_linked_invoice(report,key,rows,refs,extra_headers,sheet_title):
    """Ghi phiếu mới và ghép trong bản tạm; chỉ thay workbook thật khi mọi bước đạt."""
    check_references(report,refs,aw.parse_delivery_date(rows[0][22]))
    original_digest=aw.delivery_report_digest(report)
    temporary=None
    workbook=None
    try:
        with tempfile.NamedTemporaryFile(dir=report.parent,suffix='.xlsx',delete=False) as handle:
            temporary=Path(handle.name)
        aw.atomic_copy_file(report,temporary)
        aw.write_result(temporary,key,rows,extra_headers=extra_headers,invoice_total=True,sheet_title=sheet_title)
        workbook=load_workbook(temporary)
        sheets=find_sheets(workbook,refs)
        current=find_sheets(workbook,[str(rows[0][23])])[0]
        if current in sheets:
            raise ValueError('Tên ảnh hiện tại đã thuộc phiếu đích; chưa ghi để tránh lặp dòng.')
        title=merge_sheets(workbook,[*sheets,current])
        workbook.save(temporary)
        workbook.close();workbook=None
        if aw.delivery_report_digest(report)!=original_digest:
            raise ValueError('TongHop thay đổi trong lúc ghép. Đóng/lưu Excel rồi thử lại; chưa ghi đè.')
        backup=report.parent/'.autowatcher-backups'/('manual-group-'+aw.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))/report.name
        aw.atomic_copy_file(report,backup)
        os.replace(temporary,report)
        return title
    finally:
        if workbook is not None:workbook.close()
        if temporary is not None:temporary.unlink(missing_ok=True)


def merge_saved_invoices(report,refs,retry_write=None):
    """Sửa phiếu đã tách trước đây, giữ mọi dòng/sửa tay và không gọi AI."""
    if len(refs)<2:raise ValueError('Cần ít nhất hai tên ảnh để gộp các sheet đã lưu.')
    digest=aw.delivery_report_digest(report)
    workbook=load_workbook(report)
    temporary=None
    try:
        sheets=find_sheets(workbook,refs)
        if len(sheets)<2:return sheets[0].title
        dates=set()
        for sheet in sheets:
            column=headers(sheet).get('Ngày nhận hàng xác nhận')
            if column:
                for row in sheet.iter_rows(min_row=2,min_col=column,max_col=column,values_only=True):
                    if row[0] in (None,''):continue
                    value=aw.from_excel(row[0],epoch=workbook.epoch) if type(row[0]) in (int,float) else row[0]
                    dates.add(aw.parse_delivery_date(value))
        if len(dates)>1:raise ValueError('Các sheet có ngày nhận khác nhau. Rà/sửa ngày nhận trong TongHop trước khi gộp.')
        title=merge_sheets(workbook,sheets)
        with tempfile.NamedTemporaryFile(dir=report.parent,suffix='.xlsx',delete=False) as handle:temporary=Path(handle.name)
        workbook.save(temporary);workbook.close()
        commit_merge(report,temporary,digest,retry_write=retry_write)
        return title
    finally:
        workbook.close()
        if temporary is not None:temporary.unlink(missing_ok=True)
