"""PR extraction and conservative, read-only comparison of a single receipt."""
import hashlib
import json
import os
from pathlib import Path
from receiving_review import normalized, has_code
from receiving_service import atomic_json, digest

VERSION = 'manual-pr-compare-v2-pr-header'

def is_timeout(error):
    return isinstance(error, TimeoutError) or any(s in (type(error).__name__ + ' ' + str(error)).lower() for s in ('timeout', 'timed out'))

def request_pr_page(aw, key, source_bytes, groups, name, progress):
    for attempt in range(2):
        seconds = 90 if attempt == 0 else 180
        progress(f'Đang đọc PR {name} · lần {attempt+1}/2 · giới hạn {seconds} giây')
        try:
            return aw.request_batch_document(key, aw.MODEL, source_bytes, groups, seconds)
        except Exception as exc:
            if not is_timeout(exc):
                raise RuntimeError(f'{name}: chưa đọc được PR. Kiểm tra kết nối đến dịch vụ đọc ảnh rồi bấm Đối chiếu PR để chạy tiếp; các trang đã lưu vẫn giữ.') from exc
            if attempt == 0:
                progress(f'{name}: quá thời gian chờ; đang thử lại một lần với giới hạn 180 giây.')
                continue
            raise RuntimeError(f'{name}: Gemini vẫn chưa phản hồi sau hai lần chờ (90 và 180 giây). '
                               'Các trang PR đã đọc và số liệu phiếu vẫn được giữ. Bấm Đối chiếu PR để chạy tiếp trang chưa xong.') from exc

def read_pr(root, folder, images, progress=None):
    progress = progress or (lambda message: None)
    import AutoWatcher as aw
    root, folder = Path(root), Path(folder)
    _, groups = aw.load_catalog_data(root / 'DanhMuc.xlsm')
    key = None
    documents = []
    for path in images:
        path = Path(path)
        source_bytes = path.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        signature = hashlib.sha256((VERSION + aw.MODEL + source_hash + json.dumps(groups,sort_keys=True,default=str)).encode()).hexdigest()
        cache = folder / '.receiving' / 'pr-documents' / (signature + '.json')
        if cache.exists():
            progress(f'Dùng PR đã đọc: {path.name}')
            document = aw.validate_batch_document(json.loads(cache.read_text(encoding='utf-8')))
        else:
            if key is None:
                key = os.environ.get('GEMINI_API_KEY', '').strip()
                if not key: key = (root / 'gemini_api_key.txt').read_text(encoding='utf-8-sig').strip()
            document = request_pr_page(aw, key, source_bytes, groups, path.name, progress)
            if document['document_type'] not in ('pr','po'):
                raise ValueError(f'{path.name}: chưa nhận diện là PR/PO. Kiểm tra ảnh đã ghép.')
            atomic_json(cache, document)
        if document['document_type'] not in ('pr','po'): raise ValueError('Kết quả đã lưu không phải PR/PO.')
        if digest(path) != source_hash: raise ValueError('Ảnh PR đã thay đổi trong khi đọc. Đọc lại.')
        documents.append({'image': path.name, 'sha256': source_hash, 'document': document})
    from rec_pr_bundle import apply_confirmed
    documents=apply_confirmed(folder,images,documents)
    refs = {d['document'].get('reference_id','').strip() for d in documents} - {''}
    if len(refs) > 1:
        raise ValueError('Các trang có số PR khác nhau: '+ '; '.join(d['image']+' → '+str(d['document'].get('reference_id','')) for d in documents)+'. Kiểm tra trang tiếp hoặc tách PR trước khi đối chiếu.')
    from receiving_pr_auto import page_items
    return page_items((d['image'],d['document']) for d in documents)

def names(item):
    from receiving_pr_match import FILLER
    result = set()
    for field in ('item_name','english_name','vietnamese_name','Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống'):
        raw = str(item.get(field) or '')
        for part in [raw, *raw.split('/')]:
            value=normalized(part)
            if value and set(value.split())-FILLER and value not in {'chua co ma','khong xac dinh duoc ma phu hop'}: result.add(value)
    return result

def ordered_supplier(rows):
    """Only the supplier's explicitly confirmed PR policy enables order hints."""
    from rec_runtime import user_root
    from supplier_rules import find_supplier
    try:
        rules=json.loads((user_root()/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
        suppliers=[find_supplier(v.get('Nhà cung cấp',''),rules) for _,v in rows]
        return bool(suppliers) and all(s and s.get('pr_same_order') is True for s in suppliers) and len({s['id'] for s in suppliers})==1
    except (OSError,ValueError,KeyError,TypeError):return False


def compare(pr_items, rows, links=None, conversions=None):
    """Conservative unique bilingual matches; never converts units or values."""
    import AutoWatcher as aw
    links = links or {}
    from receiving_lot_rows import grouped
    rows=grouped(rows,links,conversions)
    from receiving_pr_match import infer_links,spec_conflict
    from receiving_units import factor_for,converted
    from receiving_link_memory import inferred,rejected
    from receiving_deposit import effective as deposit_effective
    deposits={row:deposit_effective(row,value,conversions) for row,value in rows}
    goods=[(row,value) for row,value in rows if not deposits[row]]
    if any(row in deposits and deposits[row] for row in links.values() if row is not None):
        raise ValueError('Dòng tiền cọc không được gán vào hàng PR. Bỏ gán hoặc bỏ xác nhận cọc trước.')
    learned=inferred(pr_items,goods,links)
    combined=dict(learned);combined.update(links)
    mapping,match_reasons,suggestions=infer_links(pr_items,goods,combined,names,ordered=ordered_supplier(goods),blocked=rejected(pr_items,goods))
    for p,r in learned.items():match_reasons[p,r]='Theo cặp tên bạn đã gán và lưu cho đúng NCC/quy cách'

    counts = {r: list(mapping.values()).count(r) for r in mapping.values() if r is not None}
    values = dict(rows); result = []
    for p, item in enumerate(pr_items):
        row = mapping.get(p); d = values.get(row, {})
        status = []
        alerts = []
        ordered = aw.parse_simple_quantity(item.get('quantity'))
        from receiving_pr_quantity import effective as manual_ordered
        ordered=manual_ordered(item,(conversions or {}).get(p,(conversions or {}).get(str(p),{})))
        original_ordered=ordered
        from receiving_packaging import effective
        ordered,packing=effective(item,(conversions or {}).get(p,(conversions or {}).get(str(p))),d.get('Nhà cung cấp') if d else None)
        price = aw.parse_invoice_amount(item.get('unit_price'))
        original_pr_price=price;price_approval=None
        from receiving_price_approval import effective as approved_price
        try:price_approval=approved_price(row,item,d,(conversions or {}).get(p,(conversions or {}).get(str(p),{}))) if row is not None else None
        except ValueError as exc:alerts.append('price_approval_stale');status.append(str(exc))
        if price_approval:
            from decimal import Decimal
            price=Decimal(price_approval['price'])
            status.append('Purchase duyệt giá: '+str(original_pr_price)+' → '+str(price)+'/'+str(item.get('unit',''))+'; '+price_approval['person']+' · '+price_approval['date'])

        received = aw.parse_simple_quantity(d.get('Thực nhận'))
        delivered = aw.parse_simple_quantity(d.get('Số lượng'))
        dprice = aw.parse_invoice_amount(d.get('Đơn giá'))
        original_delivered,original_received,original_price=delivered,received,dprice
        factor,label=factor_for(conversions,p,row,item,d) if row is not None else (None,'')
        if factor is not None:
            if delivered is not None:delivered=converted(delivered,factor)
            if received is not None:received=converted(received,factor)
            if dprice is not None:dprice=converted(aw.parse_simple_quantity(dprice),factor,inverse=True)
        from receiving_quantity_correction import actual
        corrected=None
        try:corrected=actual(conversions,p,row,item,d) if row is not None else None
        except ValueError:status.append('Xác nhận thực nhận đã cũ — cần xác nhận lại');alerts.append('receipt_correction')
        if corrected:
            from decimal import Decimal
            received=Decimal(corrected['received']);delivered=None;dprice=None;factor=1
            label='NCC ghi sai lượng/ĐVT — thực nhận '+corrected['packs']+' gói × '+corrected['grams']+' g = '+corrected['received']+' '+corrected['unit']
            status.append(label+'; giữ nguyên lượng PR và số trên phiếu. Cần xác minh tiền với NCC.');alerts.append('receipt_correction')
        remaining = None
        if p in links and row is None:
            status.append('Chưa giao (đã xác định)')
            remaining = ordered
            if ordered is not None and ordered>0:alerts.append('short')
        elif row is None:
            status.append('Chưa xác định dòng giao / có thể chưa giao — chọn dòng để xác nhận')
            alerts.append('unlinked')
        elif counts.get(row, 0) > 1:
            status.append('Trùng ghép dòng giao — cần chọn lại')
            alerts.append('duplicate_link')
        else:
            from receiving_substitution import effective as substitute_effective
            substitution=None
            try:substitution=substitute_effective(row,item,d,(conversions or {}).get(p,(conversions or {}).get(str(p),{})))
            except ValueError as exc:status.append(str(exc));alerts.append('substitution_stale')
            if substitution:status.append('Hàng thay thế đã duyệt: '+substitution['department']+' / Purchase '+substitution['purchase']+' · '+substitution['date']+' · '+substitution['reason'])
            from receiving_spec_equivalence import equivalent
            if spec_conflict(item,d) and not substitution and not equivalent(item,d):status.append('Quy cách/dung lượng khác — cần kiểm trên ảnh');alerts.append('specification')
            if item.get('catalog_code') and has_code(d) and str(item['catalog_code']) != str(d.get('Mã vật tư')) and not substitution:
                status.append('Khác mã hàng — kiểm loại/quy cách')
                alerts.append('code')
            if factor is None:
                status.append('Đơn vị khác nhau hoặc còn thiếu — cần xác nhận quy đổi trước khi so lượng và giá')
                alerts.append('unit')
            else:
                if ordered is None or received is None: status.append('Chưa xác định đủ số lượng đặt hoặc số lượng thực nhận');alerts.append('unknown_quantity')
                else:
                    remaining = ordered - received
                    if remaining > 0: status.append('Thiếu trong lần giao này');alerts.append('short')
                    elif remaining < 0: status.append('Nhận vượt lượng đặt');alerts.append('over')
                if price is None or dprice is None: status.append('Giá PR/phiếu chưa rõ');alerts.append('unknown_price')
                elif price != dprice:
                    if price_approval:status.append('Giữ giá Purchase đã duyệt '+str(price)+'; giá NCC '+str(dprice)+' — chênh lệch giữ để theo dõi, không sửa phiếu')
                    else:status.append('Đơn giá khác nhau — kiểm tra thuế VAT và chiết khấu');alerts.append('price')
            # Informational matching/conversion provenance is not an unresolved alert.
            if not alerts:status.append('Khớp lượng và giá')
            if label:status.append(label.split(' · ',1)[0])
            if not (str(item.get('catalog_code') or '') and str(item.get('catalog_code')) == str(d.get('Mã vật tư'))):
                status.append('Dòng giao đã chọn' if p in links or label else 'Tự ghép theo tên — kiểm tra đúng mặt hàng')
        overreceipt=None
        entry=(conversions or {}).get(p,(conversions or {}).get(str(p),{})) or {}
        if row is not None:
            from receiving_overreceipt import effective as effective_overreceipt
            try:overreceipt=effective_overreceipt(row,item,d,entry,ordered,received)
            except ValueError as exc:alerts.append('overreceipt_stale');status.append(str(exc))
            if overreceipt and 'over' in alerts:
                alerts.remove('over');status.append('Đã duyệt nhận dư '+overreceipt['excess']+' '+str(item.get('unit',''))+' — Chờ bộ phận bổ sung PR; '+overreceipt['reason'])
        if packing:status.append(f"Đóng gói đã duyệt: PR {original_ordered} → mua {ordered} {item.get('unit','')}; tăng {ordered-original_ordered}. {packing['reason']}")
        result.append({'overreceipt_approval':overreceipt,'original_pr_price':original_pr_price,'price_approval':price_approval,'requested':original_ordered,'purchase_approval':packing,'pr_index':p, 'row':row, 'name':item.get('item_name',''), 'unit':item.get('unit',''),
                       'ordered':ordered, 'delivered':delivered, 'received':received, 'price':price,
                       'delivery_price':dprice, 'remaining':remaining, 'status':'; '.join(status) or 'Khớp lượng và giá',
                       'alerts':alerts,
                       'suggested_row':suggestions.get(p),'match_reason':match_reasons.get((p,row),'Ghép thủ công' if p in links else ''),
                       'conversion_label':label,'original_delivered':original_delivered,'original_received':original_received,'original_price':original_price,
                       'source':f"{item.get('source_image','')} · dòng {item.get('source_line','')}"})
    used = {r for r in mapping.values() if r in values}
    for row, value in rows:
        if row not in used:
            result.append({'row':row,'name':value.get('Tên hàng trên phiếu (Ảnh)',''),
                           'unit':value.get('Đơn vị tính',''), 'delivered':aw.parse_simple_quantity(value.get('Số lượng')),
                           'received':aw.parse_simple_quantity(value.get('Thực nhận')),
                           'delivery_price':aw.parse_invoice_amount(value.get('Đơn giá')),
                           'deposit':bool(deposits[row]), 'alerts':[],
                           'status':('Tiền cọc vỏ / bao bì ngoài PR đã xác nhận — không tính vào lượng hàng; '+deposits[row]['reason']) if deposits[row] else 'Dòng phiếu giao chưa ghép với dòng PR nào — kiểm tra có phải hàng ngoài PR', 'source':'Phiếu giao'})
    for entry in result:
        if entry.get('pr_index') is None and entry.get('received')==0 and not entry.get('deposit'):
            entry['not_received']=True;entry['status']='Không nhận trong phiếu này — không tính vào lượng PR'
    for entry in result:
        source=dict(rows).get(entry.get('row'),{})
        if source.get('Các dòng/lô đã ghép'):
            entry['lot_rows']=source['Các dòng/lô đã ghép']
            entry['status']+=' · Cộng '+str(len(entry['lot_rows']))+' dòng/lô giao cùng mã'
    from receiving_no_topup import valid
    for entry in result:
        p=entry.get('pr_index')
        if p is None:continue
        stop=((conversions or {}).get(p,(conversions or {}).get(str(p),{})) or {}).get('no_topup')
        if stop and not valid(pr_items[p],stop):entry['alerts'].append('no_topup_stale')
        elif stop:entry['no_topup']=stop
    return result
