"""Audited pre-REC received quantities, separate from delivery receipts."""
import json,sqlite3,uuid
from pathlib import Path
from contextlib import closing
from datetime import date,datetime,timezone
from fractions import Fraction

def scope(lines):
 from receiving_ledger import fingerprint
 return fingerprint([{k:(line.get('requested',line.get('ordered')) if k=='ordered' else line.get(k)) for k in ('index','name','unit','ordered','price','code','specification')} for line in lines])

def records(conn,oid=None):
 if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='opening_balances'").fetchone():return {}
 return {key:dict(json.loads(raw),revision=rev) for key,rev,raw in conn.execute('SELECT order_id,revision,payload FROM opening_balances'+(' WHERE order_id=?' if oid else ''),(oid,) if oid else ())}

def read(path,oid=None):
 if not Path(path).is_file():return {}
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as conn:return records(conn,oid)

def validate(record,lines):
 from receiving_evidence import validate as proof
 if record.get('scope')!=scope(lines):raise ValueError('PR đã đổi; cần rà lại lượng nhận trước khi dùng REC.')
 sources=record.get('pr_sources',{})
 if not sources:raise ValueError('Thiếu nguồn PR cho lượng nhận trước.')
 from receiving_service import digest
 for name,sha in sources.items():
  if not Path(name).is_absolute() or not Path(name).is_file() or digest(Path(name))!=sha:raise ValueError('Ảnh PR gốc đã mất hoặc thay đổi; cần rà lại lượng nhận trước.')
 context=record.get('pr_context')
 if context:
  from receiving_ledger import fingerprint
  library=json.loads(Path(context['index']).read_text(encoding='utf-8'));current=library.get('orders',{}).get(context['identity'])
  if not current or fingerprint(current.get('items',[]))!=context['items_hash']:raise ValueError('Nội dung các dòng PR trong thư viện đã đổi; cần rà lại lượng nhận trước.')
 proof(record.get('attachments',[]));return True

def quantities(conn,oid,lines):
 record=records(conn,oid).get(oid)
 if not record:return {},None
 if not any(Fraction(q)>0 for q in record['quantities'].values()):return {str(i):Fraction(0) for i in record['quantities']},None
 try:validate(record,lines)
 except (OSError,ValueError,KeyError) as exc:return {},str(exc)
 return {str(i):Fraction(q) for i,q in record['quantities'].items()},None

def receipt_before(payload,index,before):
 """Explicit confirmed receipt date wins over the report's working day."""
 rows=dict(payload.get('source_rows',[]));links=payload.get('allocation_rows',{});row=links.get(str(index),links.get(index));values=rows.get(row,{})
 if not values and row is not None:
  try:values=rows.get(int(row),rows.get(str(row),{}))
  except (TypeError,ValueError):values={}
 raw=str(values.get('Ngày nhận hàng xác nhận') or payload.get('day') or '').strip()[:10]
 for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y'):
  try:return datetime.strptime(raw,fmt).date()<date.fromisoformat(before)
  except ValueError:pass
 return True

def save(path,oid,title,lines,values,before,person,reason,attachments,expected_revision=0,expected_receipts=None,pr_sources=None,pr_context=None):
 import receiving_ledger as ledger
 from receiving_evidence import validate as proof
 if not lines or any(line.get('index')!=i or not str(line.get('name') or '').strip() or not str(line.get('unit') or '').strip() for i,line in enumerate(lines)):raise ValueError('PR phải có đủ tên hàng, đơn vị và chỉ số dòng hợp lệ.')
 for line in lines:ledger.amount(line.get('ordered'))
 boundary=date.fromisoformat(before)
 if boundary>date.today():raise ValueError('Mốc bắt đầu không được ở tương lai.')
 if not person.strip() or not reason.strip():raise ValueError('Nhập người/bộ phận xác nhận và căn cứ nhận trước.')
 if set(values)!={str(i) for i in range(len(lines))}:raise ValueError('Nhập lượng nhận trước cho đủ các dòng PR; món chưa nhận nhập 0.')
 if not pr_sources:raise ValueError('Cần ảnh PR gốc đã xác minh trước khi lưu lượng nhận trước.')
 normalized={str(i):ledger.exact_text(ledger.amount(value)) for i,value in values.items()};proof(attachments)
 with ledger.database(path) as conn:
  ledger.backup(conn,path);conn.execute('BEGIN IMMEDIATE')
  try:
   if pr_context:
    from receiving_pr_number_identity import check_new_order
    orders=[(key,title,json.loads(raw)) for key,title,raw in conn.execute('SELECT id,title,lines FROM orders')]
    check_new_order(Path(pr_context['index']).parent,path,pr_context['identity'],oid,orders,lines)
   old=records(conn,oid).get(oid)
   if (old['revision'] if old else 0)!=expected_revision:raise ValueError('Lượng nhận trước đã đổi. Mở lại PR rồi nhập lại.')
   if expected_receipts is not None:
    current_receipts=ledger.fingerprint(list(conn.execute('SELECT id,revision,active FROM receipts WHERE order_id=? ORDER BY id',(oid,))))
    if current_receipts!=expected_receipts:raise ValueError('Các phiếu đã ghi thay đổi. Mở lại để xem đúng tổng trước khi lưu lượng nhận trước.')
   existing=conn.execute('SELECT lines FROM orders WHERE id=?',(oid,)).fetchone()
   if existing and scope(json.loads(existing[0]))!=scope(lines):raise ValueError('Nội dung PR khác sổ. Chưa lưu lượng nhận trước.')
   if conn.execute('SELECT 1 FROM closures WHERE order_id=?',(oid,)).fetchone():raise ValueError('Mở lại PR đã ngừng trước khi chỉnh lượng nhận trước.')
   for (raw,) in conn.execute('SELECT payload FROM receipts WHERE order_id=? AND active=1',(oid,)):
    receipt=json.loads(raw)
    if any(Fraction(q)>0 and Fraction(normalized.get(str(i),'0'))>0 and receipt_before(receipt,i,before) for i,q in receipt['allocations'].items()):raise ValueError('Đã có phiếu cũ trước mốc bắt đầu cho món này. Không cộng thêm lượng đầu kỳ trùng chứng từ.')
   payload=dict(version=1,kind='opening_balance',scope=scope(lines),pr_sources=dict(pr_sources),pr_context=pr_context,before=before,person=person.strip(),reason=reason.strip(),quantities=normalized,attachments=attachments,time=datetime.now(timezone.utc).isoformat())
   validate(payload,lines)
   conn.execute('INSERT OR IGNORE INTO orders VALUES(?,?,?)',(oid,title,json.dumps(lines,ensure_ascii=False,sort_keys=True)))
   conn.execute('INSERT OR IGNORE INTO order_aliases VALUES(?,?)',(oid,oid))
   for i in range(len(lines)):conn.execute('INSERT OR IGNORE INTO order_line_ids VALUES(?,?,?)',(oid,i,ledger.fingerprint([oid,i])))
   conn.execute('CREATE TABLE IF NOT EXISTS opening_balances(order_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
   revision=(old['revision'] if old else 0)+1
   conn.execute('INSERT OR REPLACE INTO opening_balances VALUES(?,?,?)',(oid,revision,json.dumps(payload,ensure_ascii=False)))
   conn.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,payload['time'],'opening:'+oid,json.dumps(old,ensure_ascii=False) if old else None,json.dumps(payload,ensure_ascii=False)))
   conn.commit();return revision
  except Exception:conn.rollback();raise

def guard_receipt(conn,oid,payload):
 record=records(conn,oid).get(oid)
 if record and any(Fraction(q)>0 and Fraction(record['quantities'].get(str(i),'0'))>0 and receipt_before(payload,i,record['before']) for i,q in payload['allocations'].items()):raise ValueError('Phiếu trước mốc nhận đầu kỳ. Rà/giảm lượng nhận trước của món này trước khi nhập phiếu cũ để tránh tính trùng.')
