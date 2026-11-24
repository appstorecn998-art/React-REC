"""Audited per-line stop/reopen decisions. Never alters receipt quantities."""
import json,uuid,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from fractions import Fraction
from receiving_units import exact_text

def line_key(line):
    from receiving_ledger import fingerprint
    return fingerprint({k:line.get(k) for k in ('index','name','unit','ordered','price','code','specification')})

def entries(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='item_closures'").fetchone():return {}
    return {(oid,int(index)):json.loads(raw) for oid,index,raw in conn.execute('SELECT order_id,line_index,payload FROM item_closures')}

def apply_summary(path,rows):
    import receiving_ledger as ledger
    with closing(sqlite3.connect(__import__('pathlib').Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as conn:saved=entries(conn)
    for row in rows:
        decision=saved.get((row['order_id'],int(row['index'])))
        row['item_stopped']=False;row['physical_remaining']=None if row['source_unverified'] else exact_text(max(Fraction(0),Fraction(row['ordered'])-Fraction(row['received'])))
        if not decision:continue
        row['stop_reason']=decision['reason'];row['stop_time']=decision['time']
        if decision['line_key']!=line_key(row):
            row.update(remaining=None,status='Nội dung PR đã đổi; cần rà quyết định ngừng món',source_unverified=True)
            continue
        row['item_stopped']=True
        if not row['source_unverified']:
            row.update(remaining='0',cancelled=row['physical_remaining'],reason=decision['reason'],status='Đã ngừng giao bù món này')
    return rows

def set_items(path,oid,indices,reason,reopen=False,expected=None,attachments=None):
    from receiving_evidence import validate as evidence_valid
    evidence_valid(attachments or [])
    import receiving_ledger as ledger
    if not reason.strip():raise ValueError('Nhập người/bộ phận xác nhận và lý do.')
    indices=set(map(int,indices))
    if not indices:raise ValueError('Chọn ít nhất một món.')
    with ledger.database(path) as conn:
        ledger.backup(conn,path);conn.execute('BEGIN IMMEDIATE')
        try:
            record=conn.execute('SELECT lines FROM orders WHERE id=?',(oid,)).fetchone()
            if not record:raise ValueError('PR không còn trong sổ.')
            lines=json.loads(record[0]);saved=entries(conn)
            if conn.execute('SELECT 1 FROM closures WHERE order_id=?',(oid,)).fetchone():raise ValueError('Cả PR đã ngừng. Mở lại PR trước khi thao tác từng món.')
            if any(i<0 or i>=len(lines) for i in indices):raise ValueError('Mặt hàng đã thay đổi.')
            if expected is not None and any(expected.get(str(i))!=line_key(lines[i]) for i in indices):raise ValueError('PR đã thay đổi; tải lại trước khi lưu.')
            if not reopen:
                from receiving_opening_balance import quantities
                opening,error=quantities(conn,oid,lines)
                if error:raise ValueError(error)
                received={int(i):q for i,q in opening.items()}
                for (raw,) in conn.execute('SELECT payload FROM receipts WHERE order_id=? AND active=1',(oid,)):
                    for i,q in json.loads(raw)['allocations'].items():received[int(i)]=received.get(int(i),Fraction(0))+Fraction(q)
                if any(Fraction(lines[i]['ordered'])<=received.get(i,Fraction(0)) for i in indices):raise ValueError('Món đã nhận đủ hoặc dư; tải lại bảng trước khi ngừng.')
            conn.execute('CREATE TABLE IF NOT EXISTS item_closures(order_id TEXT,line_index INTEGER,payload TEXT NOT NULL,PRIMARY KEY(order_id,line_index))')
            for index in sorted(indices):
                old=saved.get((oid,index))
                if reopen:
                    if not old:raise ValueError('Món đang chọn chưa ngừng giao bù.')
                    conn.execute('DELETE FROM item_closures WHERE order_id=? AND line_index=?',(oid,index))
                    new=dict(action='reopen_item',reason=reason.strip(),attachments=attachments or [])
                else:
                    new=dict(line_key=line_key(lines[index]),reason=reason.strip(),attachments=attachments or [],time=datetime.now(timezone.utc).isoformat())
                    conn.execute('INSERT OR REPLACE INTO item_closures VALUES(?,?,?)',(oid,index,json.dumps(new,ensure_ascii=False)))
                conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,datetime.now(timezone.utc).isoformat(),'item:'+oid+':'+str(index),json.dumps(old,ensure_ascii=False),json.dumps(new,ensure_ascii=False)))
            conn.commit()
        except Exception:conn.rollback();raise
