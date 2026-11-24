"""Local shortage ledger. Explicit reviewed receipts; exact Decimal arithmetic."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from receiving_units import exact_text
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from receiving_review import normalized

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def amount(value):
    if value is None or isinstance(value,bool):raise ValueError('Số lượng chưa rõ; chưa ghi sổ.')
    try:d=Fraction(str(value))
    except (ValueError,ZeroDivisionError,OverflowError):raise ValueError('Số lượng không hợp lệ.')
    if d<0:raise ValueError('Số lượng không hợp lệ.')
    return d

def order_lines(items,conversions=None):
    import AutoWatcher as aw
    lines=[]
    for i,item in enumerate(items):
        qty=aw.parse_simple_quantity(item.get('quantity'))
        from receiving_packaging import effective
        qty,packing=effective(item,(conversions or {}).get(i,(conversions or {}).get(str(i))))
        unit=normalized(item.get('unit'))
        if qty is None or not unit:raise ValueError('Chưa xác định đủ số lượng đặt hoặc đơn vị trên PR. Kiểm tra trước khi ghi sổ.')
        lines.append({'index':i,'name':str(item.get('item_name') or ''),'unit':unit,
                      'ordered':exact_text(amount(qty)),'price':None if aw.parse_invoice_amount(item.get('unit_price')) is None else exact_text(amount(aw.parse_invoice_amount(item.get('unit_price')))),
                      'code':str(item.get('catalog_code') or ''),'specification':str(item.get('specification') or '')})
        if packing:lines[-1].update(requested=packing['requested'],purchase_approval=packing)
    if not lines:raise ValueError('PR chưa có dòng hàng.')
    return lines

def allocations(items, rows, links,conversions=None):
    import AutoWatcher as aw
    from receiving_units import factor_for
    # The caller must confirm every PR row, including explicitly not delivered.
    if set(links)!=set(range(len(items))):raise ValueError('Chọn rõ dòng giao hoặc Chưa giao cho từng dòng PR trước khi ghi sổ.')
    from receiving_lot_rows import grouped
    rows=grouped(rows,links,conversions)
    values=dict(rows);used=set();result={}
    for i,item in enumerate(items):
        row=links[i]
        if row is None:result[str(i)]='0';continue
        if row not in values or row in used:raise ValueError('Dòng phiếu giao đã bị xóa hoặc đang được ghép với nhiều dòng PR. Chọn lại dòng giao.')
        used.add(row);value=values[row]
        from receiving_deposit import effective as deposit_effective
        if deposit_effective(row,value,conversions):raise ValueError('Tiền cọc không được tính vào lượng nhận PR.')
        from receiving_packaging import effective
        entry=(conversions or {}).get(i,(conversions or {}).get(str(i)))
        if isinstance(entry,dict) and entry.get('purchase_approval') and effective(item,entry,value.get('Nhà cung cấp'))[1] is None:raise ValueError('Duyệt đóng gói không còn đúng NCC/mặt hàng. Duyệt lại trước khi ghi sổ.')
        from receiving_quantity_correction import actual
        correction=actual(conversions,i,row,item,value)
        from receiving_price_approval import effective as approved_price
        approved_price(row,item,value,entry or {})
        factor,_=factor_for(conversions,i,row,item,value)
        if correction:factor=1
        if factor is None:raise ValueError('Đơn vị PR và dòng giao khác nhau; chọn Quy đổi đơn vị trong bảng đối chiếu và xác nhận hệ số trước.')
        code=str(item.get('catalog_code') or '')
        dcode=str(value.get('Mã vật tư') or '')
        from receiving_substitution import effective as substitute_effective
        substitution=substitute_effective(row,item,value,entry or {})
        if code and dcode and normalized(dcode)!='chua co ma' and code!=dcode and not substitution:raise ValueError('Mã PR và phiếu khác nhau; cần rà trước khi ghi sổ.')
        qty=correction['received'] if correction else aw.parse_simple_quantity(value.get('Thực nhận'))
        result[str(i)]=exact_text(amount(qty)*factor)
    return result

@contextmanager
def database(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=10)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, title TEXT NOT NULL, lines TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), revision INTEGER NOT NULL, payload TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, time TEXT NOT NULL, receipt_id TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS closures(order_id TEXT PRIMARY KEY REFERENCES orders(id), reason TEXT NOT NULL, time TEXT NOT NULL);
        ''')
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS order_aliases(alias TEXT PRIMARY KEY,order_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS order_line_ids(order_id TEXT,line_index INTEGER,line_id TEXT UNIQUE,PRIMARY KEY(order_id,line_index));
        CREATE TABLE IF NOT EXISTS receipt_versions(receipt_id TEXT,revision INTEGER,payload TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(receipt_id,revision));
        CREATE TABLE IF NOT EXISTS sync_outbox(id TEXT PRIMARY KEY,receipt_id TEXT,revision INTEGER,state TEXT NOT NULL,created TEXT NOT NULL,error TEXT);
        ''')
        yield conn
    finally:conn.close()

def backup(conn,path):
    folder=Path(path).parent/'ledger-backups';folder.mkdir(exist_ok=True)
    target=folder/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid.uuid4().hex[:8]+'.sqlite')
    dest=sqlite3.connect(target)
    try:conn.backup(dest)
    finally:dest.close()

def save_receipt(path,order_id,title,lines,receipt_id,payload,expected_revision=0,acknowledged=None):
    if payload.get('reviews_path'):
        from receiving_pending_pr import read as pending_pr
        if pending_pr(Path(payload['reviews_path']).parent,payload['sheet'],payload.get('source_rows',[]),[Path(n) for n in payload.get('source_images',{})]):
            raise ValueError('Phiếu đang chờ PR thay thế. Thay PR hoặc bỏ chờ sau khi xác minh trước khi ghi sổ.')
    # Caller supplies a stable ID from source photo hashes, independent of date.
    if not lines or set(payload['allocations'])!={str(i) for i in range(len(lines))}:raise ValueError('Chưa xác định số lượng nhận cho đủ các dòng PR.')
    for quantity in payload['allocations'].values():amount(quantity)
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    encoded_lines=json.dumps(lines,ensure_ascii=False,sort_keys=True)
    with database(path) as conn:
        backup(conn,path)
        try:
            conn.execute('BEGIN IMMEDIATE')
            old=conn.execute('SELECT order_id,revision,payload,active FROM receipts WHERE id=?',(receipt_id,)).fetchone()
            if old and old[0]==order_id and old[2]==encoded and old[3]:conn.rollback();return old[1]
            if (old[1] if old else 0)!=expected_revision:raise ValueError('Sổ đã thay đổi. Mở lại trước khi ghi.')
            if old and conn.execute('SELECT 1 FROM closures WHERE order_id=?',(old[0],)).fetchone():raise ValueError('PR của lần nhận cũ đã chốt hủy. Mở lại PR trước khi sửa hoặc chuyển lần nhận.')
            existing=conn.execute('SELECT lines FROM orders WHERE id=?',(order_id,)).fetchone()
            if existing and existing[0]!=encoded_lines:
                old_lines=json.loads(existing[0])
                if any(old.get('purchase_approval') and not new.get('purchase_approval') for old,new in zip(old_lines,lines)):
                    raise ValueError('PR trong sổ đã có lượng mua duyệt theo đóng gói. Duyệt lại cùng quy cách cho phiếu này trước khi ghi, không tự hạ về lượng PR gốc.')
                def originals(values):
                    return [dict({k:v for k,v in line.items() if k not in ['requested','purchase_approval','ordered']},ordered=line.get('requested',line['ordered'])) for line in values]
                if originals(old_lines)!=originals(lines):raise ValueError('Nội dung PR khác sổ đã lưu. Không cộng gộp; cần rà lại PR.')
                conn.execute('UPDATE orders SET lines=? WHERE id=?',(encoded_lines,order_id))
                conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,datetime.now(timezone.utc).isoformat(),receipt_id,existing[0],json.dumps({'action':'purchase_packaging_approval','lines':lines},ensure_ascii=False)))
            if conn.execute('SELECT 1 FROM closures WHERE order_id=?',(order_id,)).fetchone():raise ValueError('Bộ phận đã báo hủy phần còn thiếu. Mở lại PR trước khi ghi nhận lần giao tiếp theo.')
            from receiving_opening_balance import guard_receipt
            guard_receipt(conn,order_id,payload)
            warnings=_warnings(conn,order_id,lines,receipt_id,payload)
            if warnings and warnings!=acknowledged:raise ValueError('Có nguy cơ ghi nhận trùng phiếu: '+'; '.join(warnings))
            conn.execute('INSERT OR IGNORE INTO orders VALUES(?,?,?)',(order_id,title,encoded_lines))
            alias=payload.get('pr_identity',order_id)
            existing_alias=conn.execute('SELECT order_id FROM order_aliases WHERE alias=?',(alias,)).fetchone()
            if existing_alias and existing_alias[0]!=order_id:raise ValueError('Bộ PR này đã liên kết với đơn khác. Không tự chuyển lịch sử.')
            conn.execute('INSERT OR IGNORE INTO order_aliases VALUES(?,?)',(alias,order_id))
            for index in range(len(lines)):conn.execute('INSERT OR IGNORE INTO order_line_ids VALUES(?,?,?)',(order_id,index,fingerprint([order_id,index])))
            revision=(old[1] if old else 0)+1
            conn.execute('INSERT OR REPLACE INTO receipts VALUES(?,?,?,?,1)',(receipt_id,order_id,revision,encoded))
            conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,datetime.now(timezone.utc).isoformat(),receipt_id,json.dumps(old,ensure_ascii=False) if old else None,json.dumps({'payload':payload,'warnings_acknowledged':warnings if acknowledged else []},ensure_ascii=False)))
            now=datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO receipt_versions VALUES(?,?,?,?)',(receipt_id,revision,encoded,now))
            conn.execute('INSERT INTO sync_outbox VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,receipt_id,revision,'pending',now,None))
            from receiving_no_topup import commit as commit_no_topup
            commit_no_topup(conn,order_id,lines,payload.get('no_topup_items',[]),payload.get('conversions',{}))
            conn.commit();return revision
        except Exception:conn.rollback();raise

def receipt_revision(path,receipt_id,*,active_only=False):
    if not Path(path).exists():return 0
    with database(path) as conn:
        row=conn.execute('SELECT revision FROM receipts WHERE id=? AND (?=0 OR active=1)',(receipt_id,active_only)).fetchone()
        return row[0] if row else 0

def list_orders(path):
    if not Path(path).exists():return []
    with database(path) as conn:return [(a,b,json.loads(c)) for a,b,c in conn.execute('SELECT * FROM orders ORDER BY title')]

def _warnings(conn,oid,lines,rid,payload):
    from receiving_opening_balance import quantities
    opening,opening_error=quantities(conn,oid,lines)
    if opening_error:raise ValueError(opening_error)
    totals={str(i):opening.get(str(i),Fraction(0)) for i in range(len(lines))};warnings=[]
    for other_id,raw in conn.execute('SELECT id,payload FROM receipts WHERE order_id=? AND active=1 AND id<>?',(oid,rid)):
        p=json.loads(raw)
        for i,q in p['allocations'].items():totals[i]=totals.get(i,Fraction(0))+amount(q)
        if p['allocations']==payload['allocations'] and any(amount(q)>0 for q in payload['allocations'].values()):
            warnings.append(f"Giống lượng đã nhận ở phiếu {p['sheet']} ngày {p['day']} — có thể giao/ghi trùng")
    for i,line in enumerate(lines):
        new=amount(payload['allocations'][str(i)])
        if new and opening.get(str(i),Fraction(0))>0:warnings.append(line['name']+': đã có '+exact_text(opening[str(i)])+' '+line['unit']+' nhận trước khi dùng REC; xác nhận phiếu này là lần nhận mới, chưa tính trong lượng nhận trước')
        from receiving_overreceipt import permits
        approved_excess=permits(payload,i,line,totals[str(i)])
        if new and totals[str(i)]>=amount(line['ordered']) and not approved_excess:warnings.append(line['name']+': đã nhận đủ trước lần này')
        elif totals[str(i)]+new>amount(line['ordered']) and not approved_excess:warnings.append(line['name']+': tổng nhận vượt lượng đặt')
    return warnings

def receipt_warnings(path,oid,lines,rid,payload):
    if not Path(path).exists():return []
    with database(path) as conn:return _warnings(conn,oid,lines,rid,payload)

def summary(path,validate=None,order_id=None):
    if not Path(path).exists():return [],[]
    with database(path) as conn:
        where=' WHERE order_id=?' if order_id is not None else ''
        args=(order_id,) if order_id is not None else ()
        orders=list(conn.execute('SELECT * FROM orders'+(' WHERE id=?' if order_id is not None else '')+' ORDER BY title',args))
        receipts=list(conn.execute('SELECT id,order_id,revision,payload,active FROM receipts'+where,args))
        closures=dict(conn.execute('SELECT order_id,reason FROM closures'+where,args))
        from receiving_opening_balance import quantities,records as opening_records
        opening_records_by_order=opening_records(conn,order_id)
        opening={oid:quantities(conn,oid,json.loads(raw)) for oid,_,raw in orders}
    from receiving_item_closure import apply_summary
    history=[];totals={};recorded={};uncertain=set()
    for rid,oid,rev,raw,active in receipts:
        p=json.loads(raw);validation=validate(p) if validate and active else True;valid=bool(active) and bool(validation)
        unknown=set(validation.get('uncertain',[])) if isinstance(validation,dict) else set(p['allocations']) if not valid else set()
        history.append(dict(p,receipt_id=rid,order_id=oid,revision=rev,active=bool(active),valid=valid,uncertain_indices=sorted(unknown,key=int)))
        if not active:continue
        for index,qty in p['allocations'].items():
            recorded[(oid,str(index))]=recorded.get((oid,str(index)),Fraction(0))+amount(qty)
            if str(index) in unknown:uncertain.add((oid,str(index)))
            else:totals[(oid,str(index))]=totals.get((oid,str(index)),Fraction(0))+amount(qty)
    for oid,record in opening_records_by_order.items():
        values,error=opening.get(oid,({},None))
        for index,quantity in record['quantities'].items():
            key=(oid,str(index));recorded[key]=recorded.get(key,Fraction(0))+amount(quantity)
            if error and amount(quantity)>0:uncertain.add(key)
            else:totals[key]=totals.get(key,Fraction(0))+values.get(str(index),Fraction(0))
    result=[]
    for oid,title,raw in orders:
        for index,line in enumerate(json.loads(raw)):
            total=totals.get((oid,str(index)),Fraction(0));remaining=amount(line['ordered'])-total
            result.append(dict(line,order_id=oid,title=title,received=exact_text(total),recorded_received=exact_text(recorded.get((oid,str(index)),Fraction(0))),remaining=None if (oid,str(index)) in uncertain else '0' if oid in closures else exact_text(remaining),
                               cancelled=None if (oid,str(index)) in uncertain else exact_text(max(Fraction(0),remaining)) if oid in closures else '0',
                               reason=closures.get(oid,''),status='Nguồn đã đổi / bỏ xác nhận — cần cập nhật sổ' if (oid,str(index)) in uncertain else ('Đã hủy phần còn thiếu — không giao tiếp' if oid in closures else 'Còn thiếu' if remaining>0 else 'Đã đủ' if remaining==0 else 'Nhận thừa')))
    for row in result:
        record=opening_records_by_order.get(row['order_id'],{});row['opening_received']=record.get('quantities',{}).get(str(row['index']),'0');row['opening_before']=record.get('before','')
        row['local_received']=row['received'];row['source_unverified']=row['remaining'] is None
        row['history_unverified']=False
    return apply_summary(path,result),history

def revoke_receipt(path,receipt_id,expected_revision,reason=None):
    with database(path) as conn:
        backup(conn,path)
        try:
            conn.execute('BEGIN IMMEDIATE')
            old=conn.execute('SELECT revision,payload,active,order_id FROM receipts WHERE id=?',(receipt_id,)).fetchone()
            if not old or old[0]!=expected_revision:raise ValueError('Lần nhận đã thay đổi. Mở lại sổ.')
            if conn.execute('SELECT 1 FROM closures WHERE order_id=?',(old[3],)).fetchone():raise ValueError('Mở lại PR đã chốt hủy trước khi gỡ lần nhận.')
            conn.execute('UPDATE receipts SET active=0,revision=revision+1 WHERE id=?',(receipt_id,))
            conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,datetime.now(timezone.utc).isoformat(),receipt_id,old[1],json.dumps(dict(active=False,**({'reason':str(reason).strip()} if reason is not None else {})),ensure_ascii=False)))
            conn.commit()
        except Exception:conn.rollback();raise

def close_order(path,order_id,reason,reopen=False,attachments=None):
    from receiving_evidence import validate as evidence_valid
    evidence_valid(attachments or [])
    if not str(reason).strip():raise ValueError('Nhập bộ phận/người báo và lý do hủy hoặc mở lại.')
    with database(path) as conn:
        backup(conn,path)
        try:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT 1 FROM orders WHERE id=?',(order_id,)).fetchone():raise ValueError('Không tìm thấy PR.')
            old=conn.execute('SELECT reason,time FROM closures WHERE order_id=?',(order_id,)).fetchone()
            now=datetime.now(timezone.utc).isoformat()
            if reopen:conn.execute('DELETE FROM closures WHERE order_id=?',(order_id,))
            else:conn.execute('INSERT OR REPLACE INTO closures VALUES(?,?,?)',(order_id,reason.strip(),now))
            conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,now,order_id,json.dumps(old),json.dumps({'action':'reopen' if reopen else 'cancel_remaining','reason':reason,'attachments':attachments or []},ensure_ascii=False)))
            conn.commit()
        except Exception:conn.rollback();raise

def pending_sync(path):
    if not Path(path).exists():return []
    with database(path) as conn:return [r[0] for r in conn.execute("SELECT id FROM sync_outbox WHERE state='pending'")]

def sync_result(path,ids,error=None):
    if not ids:return
    with database(path) as conn:
        conn.executemany('UPDATE sync_outbox SET state=?,error=? WHERE id=?', [('pending' if error else 'synced',error,i) for i in ids]);conn.commit()

def resolve_order(path,identity):
    if not Path(path).exists():return identity
    with database(path) as conn:
        row=conn.execute('SELECT order_id FROM order_aliases WHERE alias=?',(identity,)).fetchone()
        return row[0] if row else identity

def migrate(path):
    """Idempotent structural migration; never approves or changes quantities."""
    with database(path) as conn:
        backup(conn,path)
        try:
            conn.execute('BEGIN IMMEDIATE')
            for oid,raw in conn.execute('SELECT id,lines FROM orders').fetchall():
                conn.execute('INSERT OR IGNORE INTO order_aliases VALUES(?,?)',(oid,oid))
                for i,_ in enumerate(json.loads(raw)):conn.execute('INSERT OR IGNORE INTO order_line_ids VALUES(?,?,?)',(oid,i,fingerprint([oid,i])))
            for rid,revision,raw in conn.execute('SELECT id,revision,payload FROM receipts').fetchall():
                conn.execute('INSERT OR IGNORE INTO receipt_versions VALUES(?,?,?,?)',(rid,revision,raw,datetime.now(timezone.utc).isoformat()))
            conn.commit()
        except Exception:conn.rollback();raise
