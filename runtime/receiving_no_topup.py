"""Explicit per-item follow-up decision; quantities remain untouched."""
from datetime import datetime,timezone

def identity(item):
    from receiving_ledger import fingerprint
    return fingerprint(item)

def decision(item,reason):
    if not reason.strip():raise ValueError('Nhập người/bộ phận xác nhận và lý do không cần giao bù.')
    return dict(item=identity(item),reason=reason.strip(),time=datetime.now(timezone.utc).isoformat())

def valid(item,value):
    return isinstance(value,dict) and value.get('item')==identity(item) and bool(str(value.get('reason','')).strip())

def commit(conn,oid,lines,items,conversions):
    import json,uuid
    from fractions import Fraction
    from receiving_item_closure import line_key,entries
    from receiving_opening_balance import quantities
    saved=entries(conn)
    for index,item in enumerate(items):
        entry=conversions.get(str(index),conversions.get(index,{})) or {}
        stop=entry.get('no_topup')
        if not stop:continue
        if not valid(item,stop):raise ValueError('Món PR đã đổi; xác nhận lại quyết định không giao bù.')
        prior=saved.get((oid,index))
        if stop.get('action')=='reopen':
            if prior:
                if prior['line_key']!=line_key(lines[index]):raise ValueError('PR đã đổi; rà lại quyết định trong sổ.')
                conn.execute('DELETE FROM item_closures WHERE order_id=? AND line_index=?',(oid,index))
                conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,datetime.now(timezone.utc).isoformat(),'item:'+oid+':'+str(index),json.dumps(prior,ensure_ascii=False),json.dumps(dict(action='reopen_item',reason=stop['reason']),ensure_ascii=False)))
            continue
        if prior:
            if prior['line_key']!=line_key(lines[index]):raise ValueError('PR đã đổi; rà lại quyết định ngừng giao bù trong sổ.')
            continue
        received,error=quantities(conn,oid,lines)
        if error:raise ValueError(error)
        amount=Fraction(received.get(str(index),received.get(index,0)))
        for (raw,) in conn.execute('SELECT payload FROM receipts WHERE order_id=? AND active=1',(oid,)):
            amount+=Fraction(json.loads(raw)['allocations'].get(str(index),'0'))
        if amount>=Fraction(lines[index]['ordered']):raise ValueError('Món đã nhận đủ/dư; bỏ quyết định không giao bù rồi ghi lại.')
        value=dict(line_key=line_key(lines[index]),reason=stop['reason'],time=stop['time'],attachments=[])
        conn.execute('CREATE TABLE IF NOT EXISTS item_closures(order_id TEXT,line_index INTEGER,payload TEXT NOT NULL,PRIMARY KEY(order_id,line_index))')
        conn.execute('INSERT INTO item_closures VALUES(?,?,?)',(oid,index,json.dumps(value,ensure_ascii=False)))
        conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,datetime.now(timezone.utc).isoformat(),'item:'+oid+':'+str(index),None,json.dumps(value,ensure_ascii=False)))
