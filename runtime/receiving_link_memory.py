"""User-confirmed PR line pairs, scoped by supplier and full product identity."""
import json,hashlib,shutil
from datetime import datetime
from pathlib import Path
from receiving_review import normalized
from receiving_service import atomic_json

def supplier(value,rules):
    from supplier_rules import find_supplier
    found=find_supplier(value,rules)
    return found['id'] if found else normalized(value)

def identity(item,pr):
    fields=('item_name','catalog_code','specification','unit') if pr else ('Tên hàng trên phiếu (Ảnh)','Mã vật tư','Tên chuẩn hệ thống','Đơn vị tính')
    return {k:normalized(item.get(k,'')) for k in fields}

def pair_key(pr,delivery,rules):
    name=str(delivery.get('Nhà cung cấp') or '').strip()
    if not name:raise ValueError('Chưa rõ NCC, không lưu cách ghép chung.')
    return {'supplier':supplier(name,rules),'pr':identity(pr,True),'delivery':identity(delivery,False)}

def reusable_pair(pr,delivery):
    from receiving_pr_match import product_conflict,spec_conflict,pasta_identity
    from receiving_review import has_code
    name=normalized(delivery.get('Nhà cung cấp') or '')
    if name in {'','chua ro','chua ro ncc','ncc chua ro','chua xac dinh nha cung cap','khong xac dinh'}:
        raise ValueError('Cần xác định nhà cung cấp trước khi ghi nhớ.')
    code=str(pr.get('catalog_code') or '').strip()
    if code and has_code(delivery) and code!=str(delivery.get('Mã vật tư') or '').strip():
        raise ValueError('Hai mã vật tư khác nhau. Cặp này chỉ lưu cho phiếu hiện tại.')
    pr_shape,delivery_shape=pasta_identity(pr),pasta_identity(delivery)
    if product_conflict(pr,delivery) or spec_conflict(pr,delivery) or (pr_shape and delivery_shape and pr_shape!=delivery_shape):
        raise ValueError('Tên hoặc quy cách có mâu thuẫn. Cặp này chỉ lưu cho phiếu hiện tại.')


def remember(root,items,rows,links,source='Lưu đối chiếu thủ công'):
    from multi_delivery import output_lock
    path=Path(root)/'NhaCungCap.json';values=dict(rows)
    with output_lock(path):
        original=path.read_bytes();rules=json.loads(original.decode('utf-8-sig'));records=rules.setdefault('pr_link_rules',[]);added=0
        for index,row in links.items():
            if row is None or not isinstance(index,int) or not 0<=index<len(items) or row not in values:continue
            # Ambiguous duplicated manual allocations are not training examples.
            if list(links.values()).count(row)!=1:continue
            try:
                reusable_pair(items[index],values[row])
                key=pair_key(items[index],values[row],rules)
            except ValueError:continue
            existing=next((r for r in records if r.get('key')==key),None)
            if existing is not None:
                if existing.get('active',True):continue
                existing.update(active=True,confirmed_at=datetime.now().astimezone().isoformat(),source=source)
                added+=1
                continue
            records.append({'key':key,'confirmed_at':datetime.now().astimezone().isoformat(),'source':source,'pr_name':items[index].get('item_name'),'delivery_name':values[row].get('Tên hàng trên phiếu (Ảnh)'),'supplier_name':values[row].get('Nhà cung cấp')});added+=1
        if not added:return 0
        backup=Path(root)/'.autowatcher-backups'/('pr-link-learning-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True);shutil.copy2(path,backup/path.name)
        if path.read_bytes()!=original:raise ValueError('Quy tắc NCC đã đổi; chưa lưu cách ghép.')
        atomic_json(path,rules);return added

def inferred(items,rows,manual,root=None):
    from rec_runtime import user_root
    try:rules=json.loads((Path(root or user_root())/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return {}
    records=rules.get('pr_link_rules',[])
    if not records:return {}
    def frozen(value):return tuple(sorted(value.items()))
    known=set()
    for record in records:
        if record.get('active',True) is False:continue
        key=record.get('key') or {}
        if isinstance(key.get('pr'),dict) and isinstance(key.get('delivery'),dict):
            known.add((key.get('supplier'),frozen(key['pr']),frozen(key['delivery'])))
    candidates=[];used={r for r in manual.values() if r is not None}
    suppliers={};deliveries=[]
    for row,value in rows:
        if row in used:continue
        name=str(value.get('Nhà cung cấp') or '').strip()
        if not name:continue
        if name not in suppliers:suppliers[name]=supplier(name,rules)
        deliveries.append((row,suppliers[name],frozen(identity(value,False)),value))
    for index,item in enumerate(items):
        if index in manual:continue
        pr=frozen(identity(item,True))
        for row,name,delivery,value in deliveries:
            if (name,pr,delivery) not in known:
                continue
            try:
                reusable_pair(item,value)
            except ValueError:
                continue
            candidates.append((index,row))
    from collections import Counter
    pr_counts=Counter(p for p,_ in candidates);row_counts=Counter(r for _,r in candidates)
    return {p:r for p,r in candidates if pr_counts[p]==1 and row_counts[r]==1}


def record_id(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def for_suppliers(rows,root=None):
    from rec_runtime import user_root
    try:rules=json.loads((Path(root or user_root())/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return []
    allowed={r.get('key',{}).get('supplier') for r in rules.get('pr_link_rules',[])} if rows is None else {supplier(v.get('Nhà cung cấp',''),rules) for _,v in rows if v.get('Nhà cung cấp')}
    return [dict(id=record_id(r),pr=r.get('pr_name') or r.get('key',{}).get('pr',{}).get('item_name',''),delivery=r.get('delivery_name') or r.get('key',{}).get('delivery',{}).get('Tên hàng trên phiếu (Ảnh)',''),supplier=r.get('supplier_name',''),active=r.get('active',True)) for r in rules.get('pr_link_rules',[]) if r.get('key',{}).get('supplier') in allowed]


def set_active(root,rows,identity,active,reason):
    from multi_delivery import output_lock
    if type(active) is not bool or not isinstance(reason,str) or not reason.strip():raise ValueError('Nhập lý do thay đổi quy tắc ghép.')
    path=Path(root)/'NhaCungCap.json'
    with output_lock(path):
        original=path.read_bytes();rules=json.loads(original.decode('utf-8-sig'))
        allowed={r.get('key',{}).get('supplier') for r in rules.get('pr_link_rules',[])} if rows is None else {supplier(v.get('Nhà cung cấp',''),rules) for _,v in rows if v.get('Nhà cung cấp')}
        matches=[r for r in rules.get('pr_link_rules',[]) if record_id(r)==identity and r.get('key',{}).get('supplier') in allowed]
        if len(matches)!=1:raise ValueError('Quy tắc đã thay đổi hoặc khác NCC. Tải lại danh sách.')
        record=matches[0];record['active']=active
        record.setdefault('history',[]).append(dict(active=active,reason=reason.strip(),time=datetime.now().astimezone().isoformat()))
        backup=Path(root)/'.autowatcher-backups'/('pr-pair-status-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir(parents=True);shutil.copy2(path,backup/path.name)
        if path.read_bytes()!=original:raise ValueError('Quy tắc NCC đã đổi; thử lại.')
        atomic_json(path,rules)


def rejected(items,rows,root=None):
    from rec_runtime import user_root
    try:rules=json.loads((Path(root or user_root())/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return set()
    records=[r['key'] for r in rules.get('pr_link_rules',[]) if r.get('active',True) is False and isinstance(r.get('key'),dict)]
    if not records:return set()
    result=set()
    for p,item in enumerate(items):
        for row,value in rows:
            try:key=pair_key(item,value,rules)
            except ValueError:continue
            if key in records:result.add((p,row))
    return result
