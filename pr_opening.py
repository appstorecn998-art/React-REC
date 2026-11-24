"""Verified pre-REC balances for the React PR menu."""
from pathlib import Path
import receiving_ledger as ledger
from receiving_opening_balance import read,scope,save
from receiving_document_identity import library_identity
from receiving_service import accounting_root,digest


def context(store,state,library):
    path=accounting_root(store)/'.receiving'/'receiving-ledger.sqlite'
    identity=library_identity(state['images'],library)
    oid=ledger.resolve_order(path,identity)
    from receiving_pr_library import load
    record=load(library).get(identity)
    if not record:raise ValueError('PR cần có trong thư viện trước khi nhập lượng nhận trước.')
    if ledger.fingerprint(record['items'])!=ledger.fingerprint(state['items']):
        raise ValueError('Dòng PR khác thư viện. Ghép lại PR trước khi nhập lượng nhận trước.')
    source=ledger.order_lines(record['items'])
    existing=next((lines for key,_,lines in ledger.list_orders(path) if key==oid),None)
    if existing and scope(existing)!=scope(source):raise ValueError('PR khác nội dung đã ghi sổ. Rà lại PR trước.')
    from receiving_pr_number_identity import check_new_order
    check_new_order(library,path,identity,oid,ledger.list_orders(path),source)
    lines=existing or source;old=read(path,oid).get(oid,{})
    _,history=ledger.summary(path,lambda record:None,order_id=oid)
    expected=ledger.fingerprint(sorted((r['receipt_id'],r['revision'],int(r['active'])) for r in history if r['order_id']==oid))
    return dict(path=path,oid=oid,lines=lines,revision=old.get('revision',0),receipts=expected,quantities=old.get('quantities',{}),before=old.get('before',''),identity=identity,items_hash=ledger.fingerprint(record['items']))


def public(store,state,library):
    try:
        data=context(store,state,library)
        return {k:data[k] for k in ('lines','revision','receipts','quantities','before')}
    except (OSError,ValueError,KeyError) as exc:return {'error':str(exc)}


def commit(store,state,library,fields):
    import json
    data=context(store,state,library)
    if str(data['revision'])!=fields.get('revision') or data['receipts']!=fields.get('receipts'):
        raise ValueError('Sổ nhận trước đã đổi. Tải lại trước khi lưu.')
    if fields.get('consent')!='yes':raise ValueError('Xác nhận lượng này chưa nằm trong các phiếu REC.')
    values=json.loads(fields.get('quantities','{}'))
    sources={str(p.resolve()):digest(p) for p in state['images']}
    return save(data['path'],data['oid'],'PR nhận trước',data['lines'],values,fields.get('before',''),fields.get('person',''),fields.get('reason',''),[],data['revision'],data['receipts'],sources,dict(index=str((Path(library)/'index.json').resolve()),identity=data['identity'],items_hash=data['items_hash']))
