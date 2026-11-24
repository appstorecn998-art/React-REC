"""Durable supplier/product rules; never stores receipt quantities or prices."""
import json, shutil
from datetime import datetime
from pathlib import Path
from receiving_link_memory import pair_key
from receiving_units import source_delivery, conversion, positive, exact_text
from receiving_service import atomic_json


def read(root=None):
    from rec_runtime import user_root
    return json.loads((Path(root or user_root())/'NhaCungCap.json').read_text(encoding='utf-8-sig'))


def key_for(item, delivery, rules):
    from receiving_review import normalized
    name=normalized(delivery.get('Nhà cung cấp') or '')
    if name in {'','chua ro','chua ro ncc','ncc chua ro','chua xac dinh nha cung cap','khong xac dinh'}:
        raise ValueError('Cần xác định nhà cung cấp trước khi lưu quy cách.')
    key=pair_key(item,source_delivery(delivery),rules)
    if not key['pr']['item_name'] or not key['delivery']['Tên hàng trên phiếu (Ảnh)']:
        raise ValueError('Cần có tên hàng trên PR và phiếu giao.')
    return key


def lookup(item,delivery,root=None):
    try:
        rules=read(root); key=key_for(item,delivery,rules)
        matches=[r for r in rules.get('pr_spec_rules',[]) if r.get('key')==key]
        if len(matches)==1:return matches[0]
    except (OSError,ValueError,TypeError,KeyError):pass
    return {}


def packaging(item,delivery,root=None):
    remembered=lookup(item,delivery,root).get('packaging')
    if remembered:return remembered
    # Read existing desktop confirmations without approving a new purchase.
    try:
        rules=read(root)
        key={'supplier':str(delivery.get('Nhà cung cấp') or '').strip(),
             **{k:item.get(k,'') for k in ('item_name','catalog_code','specification','unit')}}
        matches=[r for r in rules.get('packaging_rules',[]) if r.get('key')==key]
        if len(matches)==1:return {'value':exact_text(positive(matches[0]['pack_size'])),'reason':matches[0]['reason']}
    except (OSError,ValueError,KeyError,TypeError):pass
    return {}


def remember(root,item,delivery,kind,value,reason):
    if kind not in ('conversion','packaging'):raise ValueError('Chọn loại quy cách hợp lệ.')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Nhập căn cứ quy cách đã kiểm tra.')
    value=exact_text(positive(value))
    if kind=='conversion':conversion(0,item,delivery,value,reason)
    from multi_delivery import output_lock
    path=Path(root)/'NhaCungCap.json'
    with output_lock(path):
        original=path.read_bytes(); rules=json.loads(original.decode('utf-8-sig'))
        key=key_for(item,delivery,rules)
        records=rules.setdefault('pr_spec_rules',[])
        matches=[r for r in records if r.get('key')==key]
        if len(matches)>1:raise ValueError('Có quy tắc trùng; cần rà trước khi ghi đè.')
        record=matches[0] if matches else {'key':key}
        record[kind]={'value':value,'reason':reason.strip(),'confirmed_at':datetime.now().astimezone().isoformat()}
        if not matches:records.append(record)
        backup=Path(root)/'.autowatcher-backups'/('spec-rule-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup.mkdir(parents=True);shutil.copy2(path,backup/path.name)
        if path.read_bytes()!=original:raise ValueError('Quy tắc NCC đã thay đổi. Tải lại trước khi lưu.')
        atomic_json(path,rules)


def remembered_conversion(row,item,delivery,root=None):
    rule=lookup(item,delivery,root).get('conversion')
    if rule:
        result=conversion(row,item,delivery,rule['value'],rule['reason'])
        result['rule_source']='Quy cách đã nhớ cho NCC'
        return result
    # Keep existing explicit unit confirmations working in the React view.
    from receiving_units import approved_conversion
    try:return approved_conversion(read(root),delivery.get('Nhà cung cấp'),row,item,source_delivery(delivery))
    except (OSError,ValueError,KeyError,TypeError):return None
