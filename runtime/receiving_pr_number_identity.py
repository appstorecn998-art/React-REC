"""Separate PRs by confirmed document number and printed PR date."""
import re,unicodedata
from datetime import datetime

def document_key(record):
    number=''.join(c for c in unicodedata.normalize('NFKC',str(record.get('number') or '')).casefold() if c.isalnum())
    raw=str(record.get('date') or '').strip()
    raw=re.sub(r'\s*([/\-])\s*',r'\1',raw)
    parsed=None
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d'):
        try:parsed=datetime.strptime(raw,fmt).date().isoformat();break
        except ValueError:pass
    return (number,parsed) if number and parsed else None


def scoped_document_key(record):
    key=document_key(record)
    if not key:return None
    from supplier_rules import normalize_name
    from receiving_department_sheets import canonical
    supplier=normalize_name(str(record.get('supplier') or ''))
    raw=str(record.get('department') or '')
    department=canonical(raw) or normalize_name(raw)
    return key+(supplier,department) if supplier or department else key


def check_new_order(directory,path,identity,oid,orders,lines):
    from receiving_pr_library import load
    import receiving_ledger as ledger
    records=load(directory);record=records.get(identity,{})
    current=scoped_document_key(record)
    if not current:raise ValueError('PR thiếu Số PR/No hoặc ngày trên PR hợp lệ. Bổ sung trong thư viện PR trước khi ghi sổ.')
    existing={key for key,_,_ in orders};duplicates={key for key,_,old in orders if key!=oid and old==lines};same_content=bool(duplicates)
    for key,other in records.items():
        if key==identity:continue
        old_id=ledger.resolve_order(path,key)
        if old_id==oid or old_id not in existing:continue
        previous=scoped_document_key(other)
        if previous==current:raise ValueError('Trùng Số PR/No và ngày PR đã ghi sổ nhưng khác ảnh. Chọn PR đã lưu: '+str(other.get('number'))+' · '+str(other.get('date')))
        if old_id in duplicates and not previous:raise ValueError('Có PR cùng nội dung chưa đủ Số PR/No và ngày để phân biệt. Bổ sung thông tin PR cũ trong thư viện.')
    return 'PR riêng theo Số PR/No + ngày; nội dung hàng giống PR khác' if same_content else ''


def rank_suggestions(entries,context,rows,*,supplier_aliases=()):
    from rec_receipt_search import normalize
    target=scoped_document_key(context)
    supplier=normalize(' '.join(str(v.get('Nhà cung cấp') or '') for _,v in rows))
    aliases={normalize(value).replace(' ','') for value in supplier_aliases}-{''}
    terms=set(normalize(' '.join(str(v.get('Tên hàng trên phiếu (Ảnh)') or '') for _,v in rows)).split())
    for entry in entries:
        record=entry['record'];score=0;reasons=[]
        if target and scoped_document_key(record)==target:score+=1000;reasons.append('Trùng Số PR/No + ngày PR')
        name=normalize(record.get('supplier',''))
        if name and (name.replace(' ','') in aliases or supplier and (name in supplier or supplier in name)):
            score+=40;reasons.append('Cùng NCC')
        products=set(normalize(' '.join(str(i.get('item_name') or '') for i in record.get('items',[]))).split())
        overlap=len(terms&products)
        if overlap:score+=min(20,overlap);reasons.append('Có mặt hàng phù hợp')
        entry['suggestion_score']=score;entry['suggestion_reason']=' · '.join(reasons)
        entry['exact_document']=bool(target and scoped_document_key(record)==target)
    return sorted(entries,key=lambda e:(-e['suggestion_score'],e['complete'],e['title']))


def check_batch_document(directory,identity,oid,staged):
    from receiving_pr_library import load
    key=scoped_document_key(load(directory).get(identity,{}))
    if not key:raise ValueError('PR thiếu Số PR/No hoặc ngày hợp lệ.')
    if key in staged and staged[key]!=oid:
        raise ValueError('Hai bộ ảnh cùng Số PR/No + ngày trong đợt này. Chọn cùng PR đã lưu trước khi ghi để tránh tạo hai PR trùng.')
    return key
