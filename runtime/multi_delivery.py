"""Đọc các phiếu giao/dịch vụ, ghép ảnh liên tiếp theo STT rồi lưu từng phiếu."""
import argparse
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import hashlib
import json
import logging
import msvcrt
import os
from pathlib import Path
import tempfile
import sys
import threading
import time
from statistics import median

OCR_DURATIONS=[]

from openpyxl import load_workbook
import AutoWatcher as aw
from copy import deepcopy
import re
from delivery_pages import continues_invoice, sequence_warnings, ambiguous_continuation, missing_pages, comparison_value
from manual_invoice_links import parse_receipt_input, check_references, group_title, save_linked_invoice, merge_saved_invoices
from received_amounts import upgrade_received_amounts
from warehouse_directory import enrich_rows, load_warehouse_directory

BASE_DIR=Path(__file__).resolve().parent
EXTRA_HEADERS=('Ngày nhận hàng xác nhận','Ảnh nguồn','Tổng tiền phiếu (cộng Thành tiền)',
               'STT trên phiếu','SHA-256 ảnh nguồn','Thời gian chụp')
MATCH_ATTEMPTS=3
MATCH_RETRY_DELAYS=(15,30)
MATCH_PART_SIZE=8


@contextmanager
def matching_progress(attempt,timeout):
    started=time.monotonic()
    done=threading.Event()
    def report():
        while not done.wait(15):
            logging.info('Đang chờ đối chiếu mã: %.0f giây; lượt %s/%s, timeout API %.0f giây. Ctrl+C để dừng.',
                         time.monotonic()-started,attempt,MATCH_ATTEMPTS,timeout)
    worker=threading.Thread(target=report,daemon=True)
    worker.start()
    try:
        yield
    finally:
        done.set()
        worker.join(timeout=1)


def resolve_invoice_items(items,args,api_key,catalog,groups,rules,supplier):
    """Chỉ thử lại lỗi máy chủ tạm thời, giữ OCR và chưa ghi nửa phiếu."""
    model=getattr(args,'active_matching_model',aw.MODEL)
    fallback=getattr(args,'matching_fallback_model','')
    for attempt in range(1,MATCH_ATTEMPTS+1):
        logging.info('Đối chiếu %s dòng: lượt %s/%s; model %s; timeout API %.0f giây.',len(items),attempt,MATCH_ATTEMPTS,model,args.timeout)
        try:
            with matching_progress(attempt,args.timeout):
                result=aw.resolve_batch_items(api_key,model,items,[],catalog,groups,rules,args.timeout,supplier)
            args.active_matching_model=model
            if isinstance(result[0],dict):result[0]['_matching_model']=model
            return result
        except Exception as exc:
            # Interactions dùng status_code; API GenAI cũ dùng code.
            status=getattr(exc,'status_code',None) or getattr(exc,'code',None)
            from ocr_retry import transient
            if not transient(exc):
                raise
            if attempt==MATCH_ATTEMPTS:
                raise RuntimeError(f'Gemini vẫn trả lỗi máy chủ {status} sau {MATCH_ATTEMPTS} lượt. '
                                   'Phiếu này chưa lưu; cache OCR và các phiếu đã lưu được giữ. '
                                   'Chờ dịch vụ ổn định rồi mở lại BAT để tiếp tục.') from exc
            from ocr_retry import retry_delay
            delay=retry_delay(exc,attempt)
            if model==aw.MODEL and fallback and fallback!=model:
                logging.warning('Model %s đang lỗi %s; chuyển riêng bước đối chiếu sang model dự phòng %s.',model,status,fallback)
                model=fallback
            logging.warning('Gemini trả lỗi máy chủ %s; tự chờ %s giây rồi thử lại lượt %s/%s. '
                            'Giữ OCR đã đọc; chưa lưu phiếu này. Ctrl+C để dừng.',status,delay,attempt+1,MATCH_ATTEMPTS)
            time.sleep(delay)


def resolve_invoice_parts(items,args,api_key,catalog,groups,rules,supplier,invoice_digest=''):
    """Lưu từng phần đã kiểm, chỉ ghép/ghi Excel khi đủ toàn bộ phiếu."""
    if len(items)<=MATCH_PART_SIZE:
        return resolve_invoice_items(items,args,api_key,catalog,groups,rules,supplier)[0]
    context=json.dumps(['multi-parts-v2-fallback',invoice_digest,catalog,groups,rules,aw.MODEL,
                        getattr(args,'matching_fallback_model',''),
                        aw.receipt_rules_fingerprint().hex(),supplier],ensure_ascii=False,sort_keys=True)
    combined={'extracted':{'supplier_name':supplier,'items':[]},'items':[]}
    total=(len(items)+MATCH_PART_SIZE-1)//MATCH_PART_SIZE
    for start in range(0,len(items),MATCH_PART_SIZE):
        part=items[start:start+MATCH_PART_SIZE]
        number=start//MATCH_PART_SIZE+1
        signature=hashlib.sha256((context+json.dumps(part,ensure_ascii=False,sort_keys=True)).encode('utf-8')).hexdigest()
        cache=args.output/'.autowatcher-cache'/'multiple-delivery-parts'/(signature+'.json')
        if cache.is_file():
            logging.info('Phần %s/%s (dòng %s–%s): lấy đối chiếu đã lưu.',number,total,start+1,start+len(part))
            resolved=json.loads(cache.read_text(encoding='utf-8'))
            cached_model=resolved.get('_matching_model') if isinstance(resolved,dict) else None
            if cached_model in {aw.MODEL,getattr(args,'matching_fallback_model','')}:
                args.active_matching_model=cached_model
        else:
            logging.info('Phần %s/%s: đối chiếu dòng %s–%s của %s dòng.',number,total,start+1,start+len(part),len(items))
            resolved=resolve_invoice_items(part,args,api_key,catalog,groups,rules,supplier)[0]
        # Kiểm line_id, số dòng, tên và phục hồi số liệu OCR trước khi lưu phần.
        if (not isinstance(resolved,dict) or not isinstance(resolved.get('items'),list)
                or any(not isinstance(item,dict) for item in resolved['items'])
                or [item.get('line_id') for item in resolved['items']]!=[item['line_id'] for item in part]):
            raise ValueError('Phần đối chiếu thiếu dòng hoặc đổi thứ tự line_id. Chưa lưu phiếu.')
        resolved=aw.restore_delivery_source_fields(resolved,part)
        plans=aw.build_plans(resolved['extracted'],catalog,groups,rules)
        aw.validate_rows(resolved,catalog,plans,groups)
        if len(plans)!=len(part) or [p['invoice_name'] for p in plans]!=[aw.text(i['item_name']) for i in part]:
            raise ValueError('Phần đối chiếu thiếu dòng hoặc đổi tên/thứ tự. Chưa lưu phiếu.')
        if not cache.is_file():save_json(cache,resolved)
        combined['items'].extend(resolved['items'])
        combined['extracted']['items'].extend(resolved['extracted']['items'])
        logging.info('Đã đối chiếu đủ %s/%s dòng; giữ nguyên một phiếu khi ghi Excel.',start+len(part),len(items))
    return combined


@contextmanager
def reading_progress(path, timeout, cached=False):
    started=time.monotonic()
    done=threading.Event()
    estimate=median(OCR_DURATIONS[-10:]) if OCR_DURATIONS else None
    if cached:
        logging.info('Đang lấy OCR đã lưu: %s; không gọi AI đọc ảnh.',path.name)
    elif estimate is not None:
        logging.info('Đang đọc %s — dự đoán khoảng %.0f giây (từ %s lượt AI gần nhất; có thể thay đổi); timeout %.0f giây.',path.name,estimate,min(len(OCR_DURATIONS),10),timeout)
    else:
        logging.info('Đang đọc %s — chưa có số đo trong phiên để dự đoán; timeout %.0f giây.',path.name,timeout)
    def report():
        while not done.wait(10):
            elapsed=time.monotonic()-started
            if estimate is not None and elapsed < estimate:
                logging.info('Đang đọc %s: %.0f giây; dự đoán còn khoảng %.0f giây.',path.name,elapsed,estimate-elapsed)
            elif estimate is not None:
                logging.info('Đang đọc %s: %.0f giây; lâu hơn dự đoán, vẫn chờ kết quả (timeout %.0f giây).',path.name,elapsed,timeout)
            else:
                logging.info('Đang đọc %s: %.0f giây; chưa đủ số đo để dự đoán.',path.name,elapsed)
    worker=threading.Thread(target=report,daemon=True)
    worker.start()
    try:
        yield
        if not cached:
            elapsed=time.monotonic()-started
            OCR_DURATIONS.append(elapsed)
            del OCR_DURATIONS[:-10]
            logging.info('AI đọc xong %s sau %.1f giây.',path.name,elapsed)
    finally:
        done.set()
        worker.join(timeout=1)


@contextmanager
def output_lock(report):
    """Windows releases this lock on exit/crash; no stale lock marker to remove."""
    path=report.with_suffix('.lock')
    with path.open('a+b') as handle:
        if not path.stat().st_size:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:
            raise ValueError('File này đang được một phiên xử lý nhiều phiếu khác sử dụng. Đóng phiên cũ trước.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def image_key(digest):
    return Path('PG_'+digest[:20]+'.jpg')


def saved_sheets(report):
    if not report.exists():
        return set()
    workbook=load_workbook(report,read_only=True)
    try:
        return set(workbook.sheetnames)
    finally:
        workbook.close()


def saved_image_digests(report):
    """Hashes nằm cùng workbook để lưu phiếu và đánh dấu hoàn tất một lần nguyên tử."""
    if not report.exists():
        return set()
    workbook=load_workbook(report,read_only=True)
    try:
        digests=set()
        for sheet in workbook:
            headers={aw.text(c.value):c.column for c in sheet[1]}
            column=headers.get('SHA-256 ảnh nguồn')
            if column:
                for row in sheet.iter_rows(min_row=2,min_col=column,max_col=column,values_only=True):
                    digests.update(re.findall(r'\b[0-9a-f]{64}\b',aw.text(row[0])))
        return digests
    finally:
        workbook.close()


def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.json',delete=False) as handle:
            temporary=Path(handle.name)
        temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        os.replace(temporary,path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def read_delivery(path,args,api_key,catalog,groups,rules,digest):
    entry=aw.extract_batch_document(path,args,api_key,groups)
    entry['digest']=digest
    rows,_=read_invoice([entry],args,api_key,catalog,groups,rules)
    return rows


def read_invoice(entries,args,api_key,catalog,groups,rules):
    entries=deepcopy(entries)
    metadata={field:next((aw.text(e['document'].get(field)) for e in entries
                         if aw.text(e['document'].get(field))), '')
              for field in ('supplier_name','delivery_date','document_kind')}
    for entry in entries:
        document=aw.validate_batch_document(entry['document'])
        if document['document_type']!='delivery':
            raise ValueError('Ảnh không được nhận diện là phiếu giao/dịch vụ của NCC. Không tự coi PR/PO là phiếu giao.')
        for field,value in metadata.items():
            if not document.get(field): document[field]=value
        aw.validate_batch_document(document)
        if hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()!=entry['digest']:
            raise ValueError('Ảnh thay đổi trong lúc đọc. Chờ gửi ảnh xong rồi chạy lại.')
    signature=json.dumps(['multi-delivery-v7-small-parts-fallback',entries,catalog,groups,rules,aw.MODEL,
                          getattr(args,'matching_fallback_model',''),
                          aw.receipt_rules_fingerprint().hex()],ensure_ascii=False,sort_keys=True).encode('utf-8')
    cache=args.output/'.autowatcher-cache'/'multiple-deliveries'/(hashlib.sha256(signature).hexdigest()+'.json')
    items=aw.flatten_batch_items(entries,'delivery')
    if cache.is_file():
        resolved=json.loads(cache.read_text(encoding='utf-8'))
        logging.info('Dùng kết quả đối chiếu đã lưu cho %s ảnh cùng phiếu.',len(entries))
    else:
        resolved=resolve_invoice_parts(items,args,api_key,catalog,groups,rules,metadata['supplier_name'],
                                       hashlib.sha256(signature).hexdigest())
        aw.validate_rows(resolved,catalog,aw.build_plans(resolved['extracted'],catalog,groups,rules),groups)
        save_json(cache,resolved)
    resolved=aw.restore_delivery_source_fields(resolved,items)
    plans=aw.build_plans(resolved['extracted'],catalog,groups,rules)
    for entry in entries:
        if hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()!=entry['digest']:
            raise ValueError('Ảnh thay đổi trong lúc đọc. Chờ gửi ảnh xong rồi chạy lại.')
    rows=aw.validate_rows(resolved,catalog,plans,groups)
    warnings=sequence_warnings(entries)
    for row,item in zip(rows,items):
        notes=list(warnings)
        if metadata['document_kind']=='service_payment':
            notes.append('CHỨNG TỪ THANH TOÁN DỊCH VỤ — chưa xác nhận thực nhận; không suy số lượng/ngày giao từ số tiền/ngày hóa đơn.')
        if notes:
            row[5]='CẦN KIỂM TRA'
            row[6]=' '.join([row[6],*notes]).strip()
    return rows,items


def stable_image_digest(path):
    """Chỉ nhận hash khi file giữ nguyên kích thước/mtime trong lúc đọc."""
    try:
        before=path.stat()
        source=path.read_bytes()
        after=path.stat()
    except PermissionError:
        return None
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or len(source)!=after.st_size:
        return None
    return hashlib.sha256(source).hexdigest()


def invoice_groups(images,report,args,api_key,groups):
    saved=saved_sheets(report)
    seen=saved_image_digests(report)
    pending=[]
    after_failure=False
    held=getattr(args,'held_image_names',[])
    from ocr_events import emit
    for path in images:
        if path.name in getattr(args,'failed_image_names',set()):
            names = [Path(entry['path']).name for entry in pending]
            held.extend(names)
            if names:
                emit('retry_held', 'Chờ ảnh liền sau được đọc để xác định ranh giới phiếu.',
                     files=', '.join(names))
            pending=[];after_failure=True
            continue
        digest=stable_image_digest(path)
        if digest is None or not (digest in seen or aw.sheet_name(image_key(digest)) in saved):
            aw.wait_ready(path)
            digest=stable_image_digest(path)
            if digest is None:
                raise ValueError(f'Ảnh {path.name} thay đổi trong lúc kiểm tra. Chờ gửi xong rồi chạy lại.')
        if digest in seen or aw.sheet_name(image_key(digest)) in saved:
            if pending:
                yield pending
                pending=[]
            logging.info('Bỏ qua ảnh đã lưu: %s (giữ nguyên dữ liệu đã sửa).',path.name)
            continue
        if digest in {e['digest'] for e in pending}:
            logging.info('Bỏ qua bản ảnh trùng nội dung: %s.',path.name)
            continue
        # Lỗi ảnh tiếp theo: giữ cache, chưa lưu nửa phiếu khi chưa biết ranh giới.
        prepared=getattr(args,'preclassified_documents',{}).get(digest)
        if prepared is not None:
            # Content hash was checked again above; reuse this worker's read.
            entry={'path':str(path),'document':deepcopy(prepared)}
        else:
            cached=False
            if getattr(args,'rules',None) is not None and Path(args.rules).is_file():
                cached=aw.batch_document_cache_path(path,path.read_bytes(),args,groups,aw.MODEL).is_file()
            with reading_progress(path,getattr(args,'timeout',90),cached=cached):
                entry=aw.extract_batch_document(path,args,api_key,groups)
        aw.validate_batch_document(entry['document'])
        if after_failure:
            from ocr_retry import explicit_start
            if not explicit_start(entry['document']):
                held.append(path.name)
                emit('retry_held', 'Chưa rõ ảnh thuộc phiếu nào sau một ảnh chưa đọc được.', files=path.name)
                logging.warning('Giữ ảnh %s: sau ảnh lỗi, chưa chứng minh đây là đầu phiếu mới.',path.name)
                continue
            after_failure=False
        logging.info('Đã đọc %s: %s dòng; đang kiểm tra ghép trang.',path.name,len(entry['document']['items']))
        entry['digest']=digest
        if entry['document']['document_type']!='delivery':
            raise ValueError(f'{path.name}: không nhận diện là phiếu giao/dịch vụ; PR/PO không xử lý ở bước 03.')
        previous=deepcopy(pending[-1]) if pending else None
        if previous:
            for field in ('supplier_name','reference_id','delivery_date','document_kind'):
                previous['document'][field]=next((e['document'].get(field) for e in pending
                                                  if e['document'].get(field)), '')
        linked = bool(pending and continues_invoice(previous,entry))
        if pending and not linked:
            from delivery_pages import continuation_candidate
            if continuation_candidate(previous,entry):
                from receiving_page_pair import verify_continuation
                linked = verify_continuation(previous,entry,args,api_key)
        if pending and not linked:
            if ambiguous_continuation(previous,entry) and getattr(args, 'web_receipts', False):
                names = [Path(page['path']).name for page in pending]
                held.extend(names)
                emit('needs_pages', 'Chưa xác định đủ trang hoặc chưa xác minh được trang liền sau.',
                     files=', '.join(names))
            else:
                if ambiguous_continuation(previous,entry):
                    logging.warning('Cần rà ghép trang: %s và %s.', Path(previous['path']).name, path.name)
                yield pending
                seen.update(e['digest'] for e in pending)
            pending=[]
        if pending and linked: logging.info('Đã xác minh ghép trang: %s + %s',Path(previous['path']).name,path.name)
        pending.append(entry)
        if entry['document'].get('has_total',False):
            yield pending
            seen.update(e['digest'] for e in pending)
            pending=[]
    if pending:
        yield pending


def ask_receipt_date(path,report=None,with_links=False):
    while True:
        answer=input(f'Ngày nhận hàng của {path.name} (DD/MM dùng năm hiện tại {aw.datetime.now().year}; Enter=hôm nay; Q=dừng; ghép: 15/10 thuộc phiếu giao hàng trong ảnh IMG_4098): ').strip()
        if answer.casefold()=='q': return None
        try:
            received,refs=parse_receipt_input(answer)
            if refs:
                if report is None:raise ValueError('Không có báo cáo đích để kiểm tra ảnh ghép.')
                check_references(report,refs,received)
            return (received,refs) if with_links else received
        except (ValueError,PermissionError) as exc:
            print(f'Chưa nhận: {exc}. Nhập lại ngày và tên ảnh; DD/MM hoặc DD/MM/YYYY.')


def upgrade_invoice_totals(report):
    """Chỉ thêm tổng vào các sheet cũ, giữ số liệu/sửa tay và sao lưu trước ghi."""
    if not report.is_file():
        return 0
    original_digest=aw.delivery_report_digest(report)
    workbook=load_workbook(report)
    temporary=None
    updated=0
    try:
        for sheet in workbook:
            headers={aw.text(c.value) for c in sheet[1]}
            if 'Tổng tiền phiếu (cộng Thành tiền)' not in headers:
                aw.add_invoice_total(sheet)
                updated+=1
        if not updated:
            return 0
        workbook.calculation.calcMode='auto'
        workbook.calculation.fullCalcOnLoad=True
        workbook.calculation.forceFullCalc=True
        with tempfile.NamedTemporaryFile(dir=report.parent,suffix='.xlsx',delete=False) as handle:
            temporary=Path(handle.name)
        workbook.save(temporary);workbook.close()
        if aw.delivery_report_digest(report)!=original_digest:
            raise ValueError('TongHop thay đổi trong lúc thêm tổng tiền. Đóng file và thử lại.')
        backup=report.parent/'.autowatcher-backups'/('invoice-totals-'+aw.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))/report.name
        aw.atomic_copy_file(report,backup)
        os.replace(temporary,report)
        logging.info('Đã thêm tổng tiền vào %s sheet; bản trước sửa: %s',updated,backup)
        return updated
    finally:
        workbook.close()
        if temporary is not None:temporary.unlink(missing_ok=True)


def invoice_identity(supplier, reference, document_date):
    identity = (aw.normalize_name(supplier or ''), aw.text(reference).casefold(),
                comparison_value('document_date', document_date))
    if all(identity) and identity[0] not in {'chua ro', 'chua ro ncc'}:
        try:
            date.fromisoformat(identity[2])
        except ValueError:
            return None
        return identity
    return None


def saved_identities(report):
    from receiving_service import snapshot
    identities = {}
    registry = report.parent / '.receiving' / 'inbox-documents'
    for sheet, rows in snapshot(report)[1]:
        if not rows:
            continue
        first = rows[0][1]
        key = invoice_identity(first.get('Nhà cung cấp trên chứng từ'),
                               first.get('Số chứng từ trên phiếu'),
                               first.get('Ngày chứng từ trên phiếu'))
        if key:
            identities[key] = sheet
            continue
        hashes = {digest for _, row in rows for digest in
                  re.findall(r'\b[0-9a-f]{64}\b', aw.text(row.get('SHA-256 ảnh nguồn')))}
        legacy_keys = set()
        for digest in hashes:
            try:
                document = json.loads((registry / f'{digest}.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(document, dict) and document.get('document_type') == 'delivery':
                candidate = invoice_identity(document.get('supplier_name'),
                                             document.get('reference_id'), document.get('document_date'))
                if candidate:
                    legacy_keys.add(candidate)
        if len(legacy_keys) == 1:
            identities[legacy_keys.pop()] = sheet
    return identities


def invoice_metadata(entries):
    documents = [entry['document'] for entry in entries]
    keys = ('supplier_name', 'reference_id', 'document_date')
    return tuple(
        next((aw.text(doc.get(key)) for doc in documents if aw.text(doc.get(key))), '')
        for key in keys
    )


def invoice_evidence(entries, rows, items, metadata):
    documents = [entry['document'] for entry in entries]
    headers = ('Nhà cung cấp trên chứng từ', 'Số chứng từ trên phiếu', 'Ngày chứng từ trên phiếu',
               'Thành tiền in trên phiếu', 'Tổng tiền in trên phiếu', 'Tiền hàng in trước thuế/chiết khấu',
               'Tiền hàng tính lại từ lượng giao', 'Mã số thuế bên bán')
    footer = documents[-1] if documents[-1].get('has_total') else {}
    total, subtotal = (aw.parse_invoice_amount(footer.get(key)) for key in ('printed_total', 'printed_subtotal'))
    seller_taxes = '; '.join(sorted({aw.text(doc.get('supplier_tax_id')) for doc in documents} - {''}))
    calculated = []
    evidence = []
    for index, (row, item) in enumerate(zip(rows, items)):
        quantity = aw.parse_simple_quantity(item.get('quantity'))
        price = aw.parse_invoice_amount(item.get('unit_price'))
        printed = aw.parse_invoice_amount(item.get('line_amount'))
        expected = quantity * Decimal(str(price)) if quantity is not None and price is not None else None
        calculated.append(expected)
        notes = []
        if expected is not None and printed is not None and abs(expected - Decimal(str(printed))) > 1:
            notes.append('Thành tiền in lệch lượng giao × đơn giá. Kiểm tra đơn giá, chiết khấu và làm tròn.')
        if item.get('receipt_mark') in {'cross_with_number', 'cross_without_number'}:
            notes.append('Rà dấu gạch và lượng thực nhận trên ảnh gốc.')
        if notes:
            row[5] = 'CẦN KIỂM TRA'
            row[6] = ' '.join([row[6], *notes]).strip()
        evidence.append([*metadata, printed, total if index == 0 else None,
                         subtotal if index == 0 else None, None, seller_taxes])
    if calculated and all(amount is not None for amount in calculated):
        computed = sum(calculated)
        evidence[0][-2] = aw.excel_number(computed)
        if subtotal is not None and abs(computed - Decimal(str(subtotal))) > 1:
            rows[0][5] = 'CẦN KIỂM TRA'
            rows[0][6] += ' Tổng tiền hàng tính lại lệch số in trước thuế/chiết khấu.'
    return headers, evidence


def save_one(report,key,rows,sheet_title=None,link_images=(),source_units=None, evidence=None):
    rows=[list(row)+([''] if len(row)==len(aw.HEADERS)+len(aw.PR_HEADERS)+len(EXTRA_HEADERS)-1 else []) for row in rows]
    headers=list(EXTRA_HEADERS)
    if source_units is not None:
        headers.append("Đơn vị trên phiếu")
        rows=[[*row,str(unit or "")] for row,unit in zip(rows,source_units)]
    if evidence is not None:
        evidence_headers, evidence_rows = evidence
        if len(rows) != len(evidence_rows):
            raise ValueError('Số dòng thông tin đối chiếu không khớp số dòng phiếu.')
        headers.extend(evidence_headers)
        rows = [row + fields for row, fields in zip(rows, evidence_rows)]
    while True:
        try:
            if link_images:
                title=save_linked_invoice(report,key,rows,link_images,headers,sheet_title)
                logging.info('Đã ghép theo xác nhận của bạn → sheet %s.',title)
            else:
                aw.write_result(report,key,rows,extra_headers=headers,invoice_total=True,sheet_title=sheet_title)
            return True
        except PermissionError:
            answer=input(f'Chưa lưu được {report.name}. Đóng file trong WPS/Excel rồi Enter để thử lại; Q để dừng: ').strip()
            if answer.casefold()=='q': return False


def report_path(args):
    received=getattr(args,'receipt_date',None)
    name=f'TongHopPhieuNgay_{received:%d-%m-%Y}.xlsx' if received is not None else 'TongHopNhieuPhieuGiaoHang.xlsx'
    return args.output/name


def run(args,api_key):
    OCR_DURATIONS.clear()
    logging.info('Đang tải danh mục và quy tắc...')
    catalog,groups=aw.load_catalog_data(args.excel)
    rules=aw.read_rules(args.rules,catalog,groups)
    warehouses=load_warehouse_directory(args.excel,required=False)
    report=report_path(args)
    images=sorted((p for p in args.input.iterdir() if p.is_file() and p.suffix.lower() in aw.IMAGE_EXTENSIONS),key=lambda p:p.name.casefold())
    with output_lock(report):
        logging.info('Đã tải danh mục. Tìm thấy %s ảnh; đang kiểm tra phiếu đã lưu...',len(images))
        upgrade_invoice_totals(report)
        upgrade_received_amounts(report)
        failed_invoices=[]
        web = getattr(args, 'web_receipts', False)
        identities = saved_identities(report) if web else {}
        from ocr_events import emit
        try:
            for entries in invoice_groups(images,report,args,api_key,groups):
                try:
                    names=', '.join(Path(e['path']).name for e in entries)
                    if web and (reason := missing_pages(entries)):
                        args.held_image_names.extend(Path(entry['path']).name for entry in entries)
                        emit('needs_pages', reason + ' Chọn lại các ảnh của phiếu cùng trang bổ sung.', files=names)
                        continue
                    metadata = invoice_metadata(entries) if web else None
                    identity = invoice_identity(*metadata) if metadata else None
                    if identity and identity in identities:
                        args.held_image_names.extend(Path(entry['path']).name for entry in entries)
                        emit('suspected_duplicate', 'Phiếu có cùng nhà cung cấp, số và ngày với phiếu đã lưu. Cần kiểm tra hai ảnh.', files=names, existing=identities[identity])
                        continue
                    logging.info('Đang đối chiếu một phiếu gồm %s ảnh: %s',len(entries),names)
                    rows,items=read_invoice(entries,args,api_key,catalog,groups,rules)
                    evidence = invoice_evidence(entries, rows, items, metadata) if web else None
                    for warning in sequence_warnings(entries): logging.warning('%s',warning)
                    received=getattr(args,'receipt_date',None)
                    receipt=(received,()) if received is not None else ask_receipt_date(Path(names),report=report,with_links=True)
                    if receipt is None: return 0
                    received,link_images=receipt
                    for row in rows: row[20:22]=['','KHÔNG CÓ PR — CẦN XÁC NHẬN KHO NẾU LIÊN QUAN']
                    enrich_rows(rows,warehouses,api_key,aw.MODEL,args.timeout,
                                args.output/'.autowatcher-cache'/'warehouses',rules,confirm_missing=False)
                    hashes='; '.join(e['digest'] for e in entries)
                    from receiving_capture_time import capture_time
                    capture_times={Path(e['path']).name:capture_time(Path(e['path'])) for e in entries}
                    capture_times.update(getattr(args,'capture_times',{}))
                    for row,item in zip(rows,items):
                        row.extend([received.strftime('%d/%m/%Y'),item['source_image'],'',
                                    aw.text(item.get('source_stt')),hashes,capture_times.get(item['source_image'],'')])
                    title=group_title([Path(entry['path']).name for entry in entries])
                    if not save_one(report,image_key(entries[0]['digest']),rows,sheet_title=title,link_images=link_images,source_units=[item.get("unit","") for item in items],evidence=evidence): return 1
                    if identity:
                        identities[identity] = title
                    logging.info('ĐÃ LƯU %s: %s dòng, ngày nhận %s → %s',names,len(rows),received.strftime('%d/%m/%Y'),report.name)
                except Exception as exc:
                    status=getattr(exc,'status_code',None) or getattr(exc,'code',None)
                    emit('invoice_error', str(exc), files=names, exception=type(exc).__name__, http_status=status)
                    if status in {401,403}:raise
                    failed_invoices.append(', '.join(Path(e['path']).name for e in entries))
                    logging.error('Phiếu chưa lưu (%s); tiếp tục phiếu kế. Lỗi %s.',failed_invoices[-1],type(exc).__name__)
        except Exception as exc:
            emit('invoice_error', str(exc), files='', exception=type(exc).__name__,
                 http_status=getattr(exc, 'status_code', None) or getattr(exc, 'code', None))
            logging.error('Chưa đọc xong: %s',str(exc).replace(api_key,'[KEY]') if api_key else str(exc))
            print('Các phiếu đã lưu vẫn được giữ. Chạy lại để tiếp tục; cache giữ phần đã đọc.')
            return 1
    if failed_invoices:
        logging.error('Chưa hoàn tất các phiếu: %s. Đọc lại để dùng cache và tiếp tục.', '; '.join(failed_invoices))
        return 1
    logging.info('Đã xử lý xong các ảnh hiện có. Kết quả: %s',report)
    return 0


def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',datefmt='%H:%M:%S')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=BASE_DIR/'PhieuGiaoNhieu_Input')
    parser.add_argument('--output',type=Path,default=BASE_DIR)
    parser.add_argument('--excel',type=Path,default=BASE_DIR/'DanhMuc.xlsm')
    parser.add_argument('--rules',type=Path,default=BASE_DIR/'NhaCungCap.json')
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--matching-fallback-model',default='gemini-3.1-flash-lite',help='Model đối chiếu dự phòng khi model chính trả lỗi máy chủ; truyền chuỗi rỗng để tắt.')
    parser.add_argument('--today',action='store_true',help='Tự dùng ngày hôm nay trên máy cho ngày nhận và tên TongHop, không hỏi ngày từng phiếu.')
    parser.add_argument('--merge-images',nargs='+',metavar='TEN_ANH',help='Gộp các ảnh đã lưu thành một phiếu, không gọi AI.')
    args=parser.parse_args()
    # Chốt ngày một lần để tên báo cáo và mọi phiếu trong phiên luôn cùng ngày.
    args.receipt_date=aw.datetime.now().date() if args.today else None
    if not 1<=args.timeout<=600: parser.error('--timeout phải từ 1 đến 600 giây.')
    if args.merge_images:
        report=report_path(args)
        try:
            with output_lock(report):title=merge_saved_invoices(report,args.merge_images)
            logging.info('ĐÃ GỘP vào sheet %s; giữ các dòng/sửa tay, đã sao lưu báo cáo cũ.',title)
            return 0
        except (OSError,ValueError) as exc:
            logging.error('Chưa gộp: %s',exc)
            return 1
    args.input.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
    date_message=(f'Ngày nhận tự động: {args.receipt_date:%d/%m/%Y} (ngày máy tính khi mở chương trình); không hỏi ngày từng phiếu.'
                  if args.receipt_date is not None else 'Mỗi phiếu hỏi ngày nhận một lần.')
    print(f'Ảnh đầu vào: {args.input}\nKết quả: {report_path(args)}\nCác ảnh cùng phiếu đặt LIÊN TIẾP theo tên file. Ghép theo STT/số phiếu/số trang; không ghép theo NCC đơn thuần.\n{date_message} Nhận cả chứng từ thanh toán dịch vụ; không đọc PR/PO/thư mục ngày.\nĐóng file Excel kết quả trước khi chạy. Không tự tạo phiếu kế toán cuối.')
    if not any(p.is_file() and p.suffix.lower() in aw.IMAGE_EXTENSIONS for p in args.input.iterdir()):
        print('Chưa có ảnh. Chép các ảnh phiếu giao vào thư mục trên rồi mở lại file bat.')
        return 0
    api_key=os.environ.get('GEMINI_API_KEY','').strip()
    key_file=BASE_DIR/'gemini_api_key.txt'
    if not api_key and key_file.is_file(): api_key=key_file.read_text(encoding='utf-8-sig').strip()
    if not api_key:
        logging.error('Thiếu API key. Dùng gemini_api_key.txt hiện có trong thư mục Auto.')
        return 1
    try:
        return run(args,api_key)
    except (KeyboardInterrupt,EOFError):
        print('\nĐã dừng. Các phiếu lưu thành công vẫn được giữ; chạy lại để tiếp tục.')
        return 1
    except Exception as exc:
        logging.error('%s',str(exc).replace(api_key,'[KEY]'))
        return 1


if __name__=='__main__': sys.exit(main())
