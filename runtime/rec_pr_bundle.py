"""Explicit confirmation for headerless PR continuations with stray OCR headers."""
import hashlib,json
from pathlib import Path
from receiving_service import digest,atomic_json

def bundle_path(folder,images):
    key=hashlib.sha256(json.dumps([(Path(p).name,digest(p)) for p in images]).encode()).hexdigest()
    return Path(folder)/'.receiving'/'pr-bundles'/(key+'.json')

def continuation(documents):
    from receiving_review import normalized
    if len(documents)<2:return False
    def numbers(d):
        values=[str(i.get('source_stt','')).strip() for i in d['document'].get('items',[])]
        return [int(v) for v in values] if values and all(v.isdigit() for v in values) else []
    first=documents[0]['document']
    if not first.get('reference_id') or not first.get('supplier_name'):return False
    if not numbers(documents[0]) or numbers(documents[0])[0]!=1:return False
    for left,right in zip(documents,documents[1:]):
        a,b=numbers(left),numbers(right)
        if left['document'].get('has_total') is not False or not a or not b or b[0]!=a[-1]+1:return False
        if any(y!=x+1 for x,y in zip(a,a[1:])) or any(y!=x+1 for x,y in zip(b,b[1:])):return False
        if normalized(right['document'].get('supplier_name',''))!=normalized(first['supplier_name']):return False
    return True

def apply_confirmed(folder,images,documents):
    path=bundle_path(folder,images)
    if not path.exists():return documents
    saved=json.loads(path.read_text(encoding='utf-8'))
    if not continuation(documents) or saved.get('documents')!=[digest_document(d) for d in documents]:return documents
    first=documents[0]['document'];result=[]
    for index,page in enumerate(documents,1):
        doc=dict(page['document'])
        for key in ['reference_id','document_date','department_name','requester_name']:doc[key]=first.get(key,'')
        result.append(dict(page,document=doc))
    return result

def digest_document(d):return hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def cached_documents(root,folder,images):
    import AutoWatcher as aw
    from receiving_pr import VERSION
    _,groups=aw.load_catalog_data(Path(root)/'DanhMuc.xlsm');result=[]
    for p in images:
        sha=digest(p);key=hashlib.sha256((VERSION+aw.MODEL+sha+json.dumps(groups,sort_keys=True,default=str)).encode()).hexdigest()
        doc=aw.validate_batch_document(json.loads((Path(folder)/'.receiving'/'pr-documents'/(key+'.json')).read_text(encoding='utf-8')))
        if doc.get('document_type')!='pr':return []
        result.append({'image':Path(p).name,'sha256':sha,'document':doc})
    return result

def offer(w,folder,images):
    from PySide6.QtWidgets import QMessageBox
    try:docs=cached_documents(w.root,folder,images)
    except (OSError,ValueError,KeyError,TypeError):return False
    if not continuation(docs):return False
    lines=[]
    for d in docs:
        doc=d['document'];items=doc['items']
        lines.append(d['image']+' · số nhận diện '+str(doc.get('reference_id',''))+' · STT '+str(items[0].get('source_stt'))+'–'+str(items[-1].get('source_stt')))
    text='\n'.join(lines)+'\n\nCác dòng liên tiếp và cùng NCC; số trên trang tiếp có thể thuộc chứng từ phía sau ảnh.\nBạn xác nhận đây là các trang của cùng PR '+str(docs[0]['document']['reference_id'])+'? Chỉ xác nhận sau khi kiểm ảnh nguồn.'
    if QMessageBox.question(w,'Xác nhận trang tiếp của PR',text,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return False
    atomic_json(bundle_path(folder,images),{'version':1,'documents':[digest_document(d) for d in docs]})
    return True
