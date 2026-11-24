"""Read-only ledger snapshot built outside the GUI thread."""
from pathlib import Path
from receiving_service import snapshot,sheet_signature
import receiving_ledger as ledger
from receiving_validation import check

def load(path,source,portable=False):
    order_catalog={oid:(oid,title,lines) for oid,title,lines in ledger.list_orders(path)}
    if portable:
        from rec_workspaces import ledger_source
        resolve=ledger_source(source)
    else:
        resolve=lambda record:record
    cache={};summary_rows,records=ledger.summary(path,lambda p:check(resolve(p),cache))
    if portable:
        records=[resolve(record) for record in records]
    supplier_by_order={}
    names={}
    for record in records:
        if not record['active']:continue
        name=str(record.get('supplier_name') or '').strip()
        if not name:
            try:
                report=record['report']
                if report not in cache:
                    _,data=snapshot(Path(report));cache[report]={n:sheet_signature(n,r) for n,r in data}
                else:_,data=snapshot(Path(report))
                candidates={str(v.get('Nhà cung cấp') or '').strip() for n,rr in data if n==record['sheet'] and sheet_signature(n,rr)==record['signature'] for _,v in rr if v.get('Nhà cung cấp')}
                name=next(iter(candidates)) if len(candidates)==1 else ''
            except (OSError,ValueError,KeyError):pass
        names.setdefault(record['order_id'],set()).add(name or 'Chưa xác định nhà cung cấp')
    from receiving_pr_library import load as load_library,library_path
    metadata=load_library(library_path(path))
    for oid in order_catalog:
        if oid not in names:
            supplier=str(metadata.get(oid,{}).get('supplier') or '').strip()
            if supplier:names[oid]={supplier}
    for r in summary_rows:
        values=names.get(r['order_id'],set())
        supplier_by_order[r['order_id']]=' / '.join(sorted(values)) if values else 'Chưa xác định nhà cung cấp'
    from receiving_register import collect
    all_records=collect(source,records)
    return order_catalog,summary_rows,records,supplier_by_order,all_records
