"""Local Receiving workflow; no API call at import time."""
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import shutil
import tempfile
from openpyxl import load_workbook
from receiving_image_archive import image_name, source_digest, archive_image, archive_directory, archived_images, link_archive

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def sheet_signature(name, rows):
    payload=json.dumps([name, rows],ensure_ascii=False,sort_keys=True,default=str)
    return 'sheet-v1:'+hashlib.sha256(payload.encode('utf-8')).hexdigest()

def invoice_images(name,rows):
    refs=set()
    for _,values in rows:
        source=str(values.get('Ảnh nguồn') or '').strip()
        if source: refs.add(image_name(source))
        for part in str(values.get('Các ảnh cùng phiếu') or '').split(';'):
            if part.strip():refs.add(image_name(part.strip()))
    # Legacy reports can lack a source column: use the exact sheet stem only.
    if not refs:
        refs.update((name+ext).casefold() for ext in IMAGE_EXTENSIONS)
    return refs

def invoice_pages(name,rows,images):
    """Use document order, never the archive's encoder-completion order."""
    refs=invoice_images(name,rows)
    candidates=[p for p in images if image_name(p) in refs]
    stored=[];numbers={}
    for _,values in rows:
        for part in str(values.get('Các ảnh cùng phiếu') or '').split(';'):
            if part.strip():stored.append(image_name(part.strip()))
        source=str(values.get('Ảnh nguồn') or '').strip()
        if source:
            key=image_name(source);stored.append(key)
            from delivery_pages import stt_number
            number=stt_number(values.get('STT trên phiếu'))
            numbers.setdefault(key,[]).append(number)
    ordered=list(dict.fromkeys(stored))
    rank={key:i for i,key in enumerate(ordered)}
    candidates.sort(key=lambda p:rank.get(image_name(p),len(rank)))
    # Only override saved order when every page has unambiguous, disjoint STT ranges.
    ranges={}
    for p in candidates:
        values=numbers.get(image_name(p),[])
        if not values or any(v is None for v in values):return candidates
        ranges[image_name(p)]=(min(values),max(values))
    by_stt=sorted(candidates,key=lambda p:ranges[image_name(p)][0])
    if all(ranges[image_name(a)][1]<ranges[image_name(b)][0] for a,b in zip(by_stt,by_stt[1:])):
        return by_stt
    return candidates


IMAGE_EXTENSIONS = {'.jpg','.jpeg','.png','.webp','.heic','.heif'}

def accounting_root(root):
    import re
    root = Path(root)
    return root.parent if re.fullmatch(r'Thang\s+\d{1,2}', root.name, re.I) else root

def day_directory(root, day):
    root = accounting_root(root)
    if root.name == str(day.year):
        year_root = root
    elif (root / str(day.year)).is_dir() or day.year != datetime.now().year:
        year_root = root / str(day.year)
    else:
        year_root = root  # Existing current-year accounting layout.
    return year_root / f'Thang {day.month}' / f'Ngay {day.day:02d}'

def find_day_report(directory, day):
    directory = Path(directory)
    candidates = [directory / f'TongHopPhieuNgay_{day:%d-%m-%Y}.xlsx',
                  directory / f'TongHop_{day:%Y-%m-%d}.xlsx',
                  directory / 'TongHopNhieuPhieuGiaoHang.xlsx']
    found = [p for p in candidates if p.is_file()]
    if len(found) > 1:
        raise ValueError('Có nhiều báo cáo tổng hợp trong cùng ngày; cần chọn lại bằng cách giữ đúng một bản làm việc: ' + ', '.join(p.name for p in found))
    # A yearless folder must never silently select a file from another year.
    import re
    for p in directory.glob('*.xlsx'):
        m = re.search(r'(?:\d{1,2}-\d{1,2}-)(\d{4})', p.stem)
        if m and int(m.group(1)) != day.year:
            raise ValueError('Thư mục ngày đang chứa báo cáo năm khác. Chọn thư mục gốc riêng theo năm trước khi tiếp tục.')
    return found[0] if found else candidates[0]

def day_images(directory):
    directory = Path(directory)
    roots = [directory, directory/'Phiếu giao hàng', directory/'Phieu giao hang']
    result = []
    seen = set()
    exported=set()
    for filename in ['published.json','published-temporary.json']:
        file=directory/'.receiving'/filename
        if file.exists():
            for record in json.loads(file.read_text(encoding='utf-8')).values():
                exported.update((directory/name).resolve() for name in record.get('image_files',[]))
    for root in roots:
        if not root.is_dir(): continue
        for p in sorted(root.iterdir(), key=lambda p:p.name.casefold()):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and p.resolve() not in seen and p.resolve() not in exported:
                result.append(p); seen.add(p.resolve())
    archived = archived_images(directory)
    replacements = {image_name(p): p for p in archived}
    result = [p for p in result if image_name(p) not in replacements or digest(p) not in (source_digest(replacements[image_name(p)]),digest(replacements[image_name(p)]))]
    result.extend(archived)
    excluded_file=directory/'.receiving'/'excluded-images.json'
    if excluded_file.exists():
        excluded=json.loads(excluded_file.read_text(encoding='utf-8'))
        if not isinstance(excluded,list) or any(not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in excluded):
            raise ValueError('Danh sách ảnh đã gỡ không hợp lệ; khôi phục bản sao lưu trước khi đọc.')
        excluded=set(excluded)
        result=[p for p in result if digest(p) not in excluded and source_digest(p) not in excluded]
    return result

def paths(base, day, destination=None):
    base = Path(base)
    if destination is not None:
        directory = day_directory(destination, day)
        return directory / '.receiving', find_day_report(directory, day)
    return base / '.receiving' / day.isoformat(), base / f'TongHopPhieuNgay_{day:%d-%m-%Y}.xlsx'

def import_images(base, day, sources, destination=None, progress=None, image_result=None):
    metadata, report = paths(base, day, destination)
    folder = archive_directory(destination,day) if destination is not None else metadata/'images'
    folder.mkdir(parents=True,exist_ok=True)
    from concurrent.futures.thread import ThreadPoolExecutor
    from concurrent.futures import as_completed
    sources=[Path(p) for p in sources if Path(p).suffix.lower() in IMAGE_EXTENSIONS]
    total=len(sources);results={}
    if progress:progress(f'Đã nhận {total} ảnh · đang chuẩn bị 0/{total}')
    # Only encoders run concurrently. archive_image serializes manifest commits.
    # Completion order must never change the document/page order returned here.
    error=None
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='rec-webp') as pool:
        jobs={pool.submit(archive_image,source,folder):i for i,source in enumerate(sources)}
        completed=0
        for job in as_completed(jobs):
            index = jobs[job]
            failure = None
            try:
                results[index] = job.result()
            except Exception as exc:
                failure = exc
                if error is None:
                    error = exc
            if image_result:
                image_result(sources[index].name, failure)
            completed+=1
            if progress:progress(f'Đã nhận {total} ảnh · đang chuẩn bị {completed}/{total}')
    # Preserve completed imports for retry, even when another image failed.
    if results:link_archive(report.parent,folder)
    if error is not None:raise error
    added=[results[i][0] for i in range(total) if results[i][1]]
    return added


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def snapshot(report):
    report = Path(report)
    if not report.exists():
        return None, []
    before = digest(report)
    book = load_workbook(report, data_only=False)
    try:
        result = []
        for sheet in book:
            headers = {str(c.value or '').strip(): c.column for c in sheet[1]}
            rows = []
            for r in range(2, sheet.max_row + 1):
                if not sheet.cell(r, 1).value:
                    continue
                rows.append((r, {h: sheet.cell(r, col).value for h, col in headers.items()}))
            result.append((sheet.title, rows))
    finally:
        book.close()
    if before != digest(report):
        raise ValueError('Báo cáo vừa thay đổi. Tải lại trước khi sửa.')
    return before, result

NUMBERS = {'Số lượng','Thực nhận','Đơn giá'}
EDITABLE = {'Thời gian chụp','Mã vật tư','Tên hàng trên phiếu (Ảnh)','Đơn vị tính','Số lượng','Thực nhận','Đơn giá', 'Ngày nhận hàng xác nhận','Ngày giao hàng','Nhà cung cấp','Ghi chú','Mã kho'}

def parse_value(header, value):
    value = value.strip()
    if header=='Thời gian chụp':
        if not value:return ''
        import re
        if not re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?',value):raise ValueError('Nhập giờ chụp theo HH:mm, ví dụ 13:59.')
        try:return datetime.strptime(value,'%H:%M:%S' if value.count(':')==2 else '%H:%M').strftime('%H:%M')
        except ValueError:raise ValueError('Giờ chụp không hợp lệ; dùng 00:00 đến 23:59.') from None
    if header in NUMBERS:
        if not value:
            return None
        # No guessing whether a comma is decimal or thousands separator.
        if ',' in value:
            raise ValueError('Nhập số với dấu chấm thập phân, không có dấu phân cách nghìn (ví dụ 12.4 hoặc 150000).')
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError('Số không hợp lệ.') from None
        if not number.is_finite() or number < 0:
            raise ValueError('Nhập số từ 0 trở lên; không dùng giá trị vô hạn hoặc ký hiệu đặc biệt.')
        return int(number) if number == number.to_integral_value() else float(number)
    if header in {'Ngày nhận hàng xác nhận','Ngày giao hàng'}:
        if not value: return None
        for fmt in ('%d/%m/%Y','%Y-%m-%d'):
            try:return datetime.strptime(value,fmt).strftime('%d/%m/%Y')
            except ValueError:pass
        raise ValueError('Ngày không hợp lệ. Chọn ngày hoặc nhập dd/mm/yyyy.')
    return value

def edit_row(report, expected, sheet_name, row, changes, catalog, warehouse_directory=None, vat_rate=None, on_saved=None):
    import AutoWatcher as aw
    from multi_delivery import output_lock
    report = Path(report)
    with output_lock(report):
        if digest(report) != expected:
            raise ValueError('Báo cáo đã đổi từ lúc mở. Tải lại để giữ sửa tay mới nhất.')
        book = load_workbook(report)
        temporary = None
        try:
            sheet = book[sheet_name]
            headers = {str(c.value or '').strip(): c.column for c in sheet[1]}
            if vat_rate is not None:
                if changes:raise ValueError('Quy đổi VAT phải lưu riêng với sửa số liệu khác.')
                from receiving_vat import convert_row
                convert_row(sheet,headers,row,vat_rate)
            for header, value in changes.items():
                if header not in EDITABLE or header not in headers:
                    raise ValueError(f'Không sửa được cột {header}.')
                if header=='Thời gian chụp':
                    parsed=parse_value(header,value)
                    for target_row in range(2,sheet.max_row+1):
                        if not any(sheet.cell(target_row,col).value is not None for col in range(1,sheet.max_column+1)):continue
                        target=sheet.cell(target_row,headers[header]);target.value=parsed;target.data_type='s'
                    continue
                cell = sheet.cell(row, headers[header])
                cell.value = parse_value(header, value)
                if isinstance(cell.value, str):
                    cell.data_type = 's'
            if 'Mã kho' in changes and warehouse_directory is not None:
                code = str(sheet.cell(row, headers['Mã kho']).value or '').strip()
                if code and code not in warehouse_directory:
                    raise ValueError('Mã kho không có trong DanhMucKho.')
                name, department = warehouse_directory[code] if code else ('', '')
                for header, value in [('Tên kho', name), ('Bộ phận', department)]:
                    if header not in headers:
                        raise ValueError('Báo cáo thiếu cột ' + header + '; chưa lưu thay đổi kho.')
                    cell = sheet.cell(row, headers[header]); cell.value = value; cell.data_type = 's'
            code = str(sheet.cell(row, headers['Mã vật tư']).value or '').strip()
            if code and code in catalog:
                resolved = [('Tên chuẩn hệ thống', catalog[code][0])]
                if 'Mã vật tư' in changes:
                    resolved.append(('Đơn vị tính', catalog[code][1]))
                for header, value in resolved:
                    cell = sheet.cell(row, headers[header]); cell.value = value; cell.data_type = 's'
            elif 'Mã vật tư' in changes:
                if code and code != 'CHUA CO MA': raise ValueError('Mã không có trong danh mục.')
                sheet.cell(row, headers['Tên chuẩn hệ thống']).value = None
            book.calculation.fullCalcOnLoad = True
            fd, temporary = tempfile.mkstemp(dir=report.parent, suffix='.xlsx')
            os.close(fd)
            book.save(temporary)
            if digest(report) != expected:
                raise ValueError('Báo cáo thay đổi khi lưu; tải lại để tiếp tục.')
            backup = report.parent / '.autowatcher-backups' / ('gui-edit-' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
            backup.mkdir(parents=True)
            shutil.copy2(report, backup / report.name)
            os.replace(temporary, report)
            if on_saved:on_saved()
        finally:
            book.close()
            if temporary: Path(temporary).unlink(missing_ok=True)

def mutate_invoice(report, expected, sheet_name, action, rows, warehouse_code=None, directory=None, supplier_name=None):
    """One atomic write for bulk warehouse assignment or removing item records.

    Deleted item cells are cleared in place so formulas on other sheets keep
    their original cell references. Snapshot/export omit records without a name.
    """
    from multi_delivery import output_lock
    from openpyxl.utils import get_column_letter
    report = Path(report)
    with output_lock(report):
        if digest(report) != expected:
            raise ValueError('Excel đã đổi; tải lại trước khi sửa.')
        book = load_workbook(report); temporary = None
        try:
            sheet = book[sheet_name]
            headers = {str(c.value or '').strip(): c.column for c in sheet[1]}
            name_col = headers['Tên hàng trên phiếu (Ảnh)']
            actual = {r for r in range(2, sheet.max_row+1) if sheet.cell(r,name_col).value}
            selected = set(rows)
            if not selected or not selected <= actual:
                raise ValueError('Dòng đã thay đổi hoặc không còn trong phiếu. Tải lại trước.')
            if action == 'supplier':
                name=str(supplier_name or '').strip()
                if not name:raise ValueError('Tên nhà cung cấp không được trống.')
                if selected!=actual:raise ValueError('Đổi NCC phải áp dụng toàn bộ dòng của phiếu.')
                if 'Nhà cung cấp' not in headers:raise ValueError('Phiếu thiếu cột nhà cung cấp.')
                for row in selected:
                    cell=sheet.cell(row,headers['Nhà cung cấp']);cell.value=name;cell.data_type='s'
            elif action == 'warehouse':
                if warehouse_code != '' and (not directory or warehouse_code not in directory):
                    raise ValueError('Kho không có trong DanhMucKho.')
                name, department = directory[warehouse_code] if warehouse_code else ('', '')
                for row in selected:
                    for header,value in [('Mã kho',warehouse_code),('Tên kho',name),('Bộ phận',department)]:
                        cell = sheet.cell(row,headers[header]); cell.value=value; cell.data_type='s'
            elif action == 'delete':
                remaining = sorted(actual-selected)
                if not remaining:
                    raise ValueError('Không xóa dòng cuối cùng của phiếu. Giữ ít nhất một dòng để tránh mất liên kết chứng từ.')
                old_values = [(r,{h:sheet.cell(r,c).value for h,c in headers.items()}) for r in sorted(actual)]
                refs = invoice_images(sheet_name,old_values)
                hashes = {part.strip() for _,values in old_values for part in str(values.get('SHA-256 ảnh nguồn') or '').split(';') if part.strip()}
                for row in selected:
                    for cell in sheet[row]: cell.value = None
                remaining_refs = invoice_images(sheet_name,[(r,{h:sheet.cell(r,c).value for h,c in headers.items()}) for r in remaining])
                if refs-remaining_refs:
                    link_col = headers.get('Các ảnh cùng phiếu')
                    if link_col is None:
                        link_col=sheet.max_column+1; sheet.cell(1,link_col,'Các ảnh cùng phiếu')
                    sheet.cell(remaining[0],link_col,'; '.join(sorted(refs)))
                if hashes and 'SHA-256 ảnh nguồn' in headers:
                    sheet.cell(remaining[0],headers['SHA-256 ảnh nguồn'],'; '.join(sorted(hashes)))
                # Rebuild only the two known application summary fields.
                for total_header, amount_header in [
                    ('Tổng tiền phiếu (cộng Thành tiền)','Thành tiền'),
                    ('Tổng tiền trên phiếu (Số lượng × Đơn giá)','Thành tiền trên phiếu')]:
                    if total_header not in headers or amount_header not in headers: continue
                    col = headers[total_header]
                    for r in range(2,sheet.max_row+1): sheet.cell(r,col).value=None
                    amount = get_column_letter(headers[amount_header]); names=get_column_letter(name_col); last=max(remaining)
                    sheet.cell(remaining[0],col, f'=IF(COUNT({amount}2:{amount}{last})<>COUNTA({names}2:{names}{last}),"CHƯA ĐỦ DỮ LIỆU",SUM({amount}2:{amount}{last}))')
            else: raise ValueError('Thao tác không hợp lệ.')
            book.calculation.fullCalcOnLoad=True
            fd,temporary=tempfile.mkstemp(dir=report.parent,suffix='.xlsx'); os.close(fd)
            book.save(temporary)
            if digest(report)!=expected: raise ValueError('Excel vừa đổi; chưa lưu thao tác.')
            backup=report.parent/'.autowatcher-backups'/('gui-'+action+'-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
            backup.mkdir(parents=True); shutil.copy2(report,backup/report.name)
            os.replace(temporary,report)
        finally:
            book.close()
            if temporary: Path(temporary).unlink(missing_ok=True)


def close_day(base, day, destination_root, template=None, report_override=None, validate=None, on_published=None, strict_existing=False):
    """Stage both outputs; detect external edits and retain last published edits."""
    import AutoWatcher as aw
    from multi_delivery import output_lock
    from multi_delivery_export import export_multiple
    base = Path(base)
    folder, report = paths(base, day)
    canonical = report_override is not None
    if canonical:
        folder, report = Path(report_override).parent / '.receiving', Path(report_override)
    target = day_directory(destination_root, day) if canonical else Path(destination_root) / f'Thang {day.month}' / f'Ngay {day.day:02d}'
    if not report.is_file(): raise ValueError('Chưa có báo cáo ngày đã chọn.')
    folder.mkdir(parents=True, exist_ok=True)
    ledger = folder / 'published.json'
    with output_lock(report):
        if validate:validate()
        original = digest(report)
        from receiving_export_pr_notes import collect as collect_pr_notes,annotate
        pr_notes=collect_pr_notes(report)
        previous = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
        key = str(target.resolve())
        names = [report.name, f'Phieu giao hang {day.day}-{day.month}-{day.year}.xlsx']
        daily_name=f'Cong viec hang ngay {day.day}-{day.month}-{day.year}.xlsx'
        # Daily manager report is built at its own destination, never in the day folder.
        publish_names = names[1:] if canonical else names
        record = previous.get(key)
        legacy_daily=target/daily_name
        if legacy_daily.is_file():
            archive=target/'.receiving'/'legacy-daily'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            archive.mkdir(parents=True,exist_ok=True)
            # Move intact, including manual edits; never discard the old workbook.
            os.replace(legacy_daily,archive/daily_name)
        if record and record.get('export_version')==10 and record.get('pending_pr_notes',[])==pr_notes and record['source'] == original and all((target/n).exists() for n in names+record.get('image_files',[])):
            if on_published:on_published(target)
            return target  # Same source: retain any hand edits in published files.
        for name in publish_names:
            existing = target/name
            if existing.exists() and ((not record and (not canonical or strict_existing)) or (record and digest(existing) != record['files'].get(name))):
                raise ValueError(f'{name} đã có/sửa riêng tại thư mục đích. Chưa ghi đè; hãy rà và đưa sửa đổi vào báo cáo nguồn trước.')
        catalog, _ = aw.load_catalog_data(base/'DanhMuc.xlsm')
        if template:
            template=Path(template)
        else:
            try:template=aw.delivery_template_path(day_directory(destination_root, day))
            except FileNotFoundError:
                template=base/'Phieu giao hang ngay X.xlsx'
                if not template.is_file():raise ValueError('Thiếu mẫu phiếu giao hàng. Kiểm tra cấu hình REC.')
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            stage = Path(temp)
            source = stage/names[0]
            shutil.copy2(report, source)
            export_multiple(source, catalog, base/'DanhMuc.xlsm', base/'NhaCungCap.json', stage/names[1], template)
            annotate(stage/names[1],pr_notes)
            from receiving_daily_report import build,stage_images
            image_files=stage_images(report,stage)
            for image in image_files:
                existing=target/image
                if existing.exists() and digest(existing)!=digest(stage/image):raise ValueError('Ảnh đích đã khác nguồn: '+image)
            for name in names:
                book = load_workbook(stage/name, read_only=True); book.close()
            if collect_pr_notes(report)!=pr_notes:raise ValueError('Trạng thái chờ PR đã đổi; mở lại trang xuất.')
            if digest(report) != original: raise ValueError('Báo cáo tổng hợp vừa thay đổi; chưa hoàn tất xuất phiếu. Tải lại rồi thử xuất lại.')
            if validate:validate()
            target.mkdir(parents=True, exist_ok=True)
            backup = folder/'publish-backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            backup.mkdir(parents=True)
            replaced = []
            retired = []
            try:
                for name in publish_names+image_files:
                    dest = target/name
                    dest.parent.mkdir(parents=True,exist_ok=True);(backup/name).parent.mkdir(parents=True,exist_ok=True)
                    if dest.exists(): shutil.copy2(dest, backup/name)
                    aw.atomic_copy_file(stage/name, dest)
                    replaced.append(name)
                for old_name in (record or {}).get('image_files',[]):
                    old_path=(target/old_name).resolve()
                    if old_name in image_files or not old_path.is_relative_to(target.resolve()) or old_path.parent.name!='Phiếu giao hàng':continue
                    if old_path.is_file():
                        saved=backup/'retired-photos'/old_name;saved.parent.mkdir(parents=True,exist_ok=True)
                        os.replace(old_path,saved);retired.append((old_path,saved))
                record = {'source_report':str(report.resolve()),'source': original, 'export_version':10,'pending_pr_notes':pr_notes,'image_files':image_files,'files': {n:digest(target/n) for n in names+image_files}}
                previous[key] = record
                atomic_json(ledger, previous)
            except Exception:
                for old_path,saved in reversed(retired):os.replace(saved,old_path)
                # Only rollback files this operation actually published.
                for name in reversed(replaced):
                    if (backup/name).exists(): aw.atomic_copy_file(backup/name, target/name)
                    else: (target/name).unlink(missing_ok=True)
                raise
        if on_published:on_published(target)
    return target

def display_rows(rows):
    """Compute only the existing standard amount formulas; preserve other cached/printed values."""
    result = []
    for row, values in rows:
        values = dict(values)
        for header, qty in [('Thành tiền','Thực nhận'),('Thành tiền trên phiếu','Số lượng')]:
            formula = values.get(header)
            if isinstance(formula,str) and formula.startswith('=IF(COUNT(') and '*'+f'O{row}' in formula:
                q,p = values.get(qty),values.get('Đơn giá')
                values[header] = q*p if isinstance(q,(int,float)) and isinstance(p,(int,float)) else 'CHƯA RÕ'
        result.append((row,values))
    for header, amount in [('Tổng tiền phiếu (cộng Thành tiền)','Thành tiền'),('Tổng tiền trên phiếu (Số lượng × Đơn giá)','Thành tiền trên phiếu')]:
        numbers = [v.get(amount) for _,v in result]
        total = sum(numbers) if numbers and all(isinstance(n,(int,float)) for n in numbers) else 'CHƯA ĐỦ DỮ LIỆU'
        for _,v in result:
            if isinstance(v.get(header),str) and v[header].startswith('=IF(COUNT('): v[header]=total
    return result
