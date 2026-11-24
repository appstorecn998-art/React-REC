"""Document identities survive verified compression and library copies."""
import json,sqlite3
from contextlib import closing
from pathlib import Path
from receiving_image_archive import image_name,source_digest,sha
from receiving_ledger import fingerprint


def page_ids(images):
    pages={}
    for p in images:
        name=image_name(p)
        if name in pages:raise ValueError('Các trang ảnh trùng tên; cần chọn lại bộ ảnh.')
        pages[name]=source_digest(p)
    if not pages:raise ValueError('Thiếu ảnh chứng từ.')
    if len(set(pages.values()))!=len(pages):raise ValueError('Có trang ảnh bị chọn lặp lại.')
    return pages


def library_identity(images,directory=None):
    images=list(map(Path,images));ids=page_ids(images)
    key=fingerprint(sorted(ids.values()))
    candidates=[]
    if directory is not None:candidates.append(Path(directory))
    for p in images:
        if (p.parent.parent/'index.json').is_file():candidates.append(p.parent.parent)
    for directory in dict.fromkeys(candidates):
        file=directory/'index.json'
        if not file.exists():continue
        data=json.loads(file.read_text(encoding='utf-8'))
        matches=[]
        for existing,record in data.get('orders',{}).items():
            stored=record.get('source_ids')
            if stored:
                if sorted(stored.values())==sorted(ids.values()):matches.append(existing)
                continue
            paths=list(map(Path,record.get('images',{})))
            # Exact stored file set, including raw hashes, proves a legacy key.
            if len(paths)==len(images) and {str(p.resolve()) for p in paths}=={str(p.resolve()) for p in images} and all(sha(p)==record['images'][str(p)] for p in paths):matches.append(existing);continue
            if not stored and sorted(record.get('images',{}).values())==sorted(sha(p) for p in images):matches.append(existing)
        if len(set(matches))>1:raise ValueError('Có nhiều PR trùng bộ ảnh. Cần xử lý liên kết trùng trước.')
        if matches:return matches[0]
    return key


def receipt_identity(images,path):
    images=list(map(Path,images));ids=page_ids(images)
    canonical=fingerprint(sorted(set(ids.values())))
    if not Path(path).exists():return canonical
    variants={image_name(p):{sha(p),source_digest(p)} for p in images}
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='receipts'").fetchone():return canonical
        records=list(conn.execute('SELECT id,payload,active FROM receipts'))
    matches=[]
    for rid,raw,active in records:
        sources=json.loads(raw).get('source_images',{})
        if len(sources)!=len(variants):continue
        matched=set();valid=True
        for name,value in sources.items():
            choices=[key for key,values in variants.items() if value in values and key not in matched]
            if not choices:
                old=Path(name)
                if old.is_file() and sha(old)==value:
                    source=source_digest(old)
                    choices=[key for key,content in ids.items() if source==content and key not in matched]
            if len(choices)!=1:valid=False;break
            matched.add(choices[0])
        if valid:matches.append((rid,bool(active)))
    active=[rid for rid,enabled in matches if enabled]
    candidates=active or [rid for rid,_ in matches]
    if len(set(candidates))>1:raise ValueError('Có nhiều lần nhận cùng bộ ảnh; cần xử lý ghi trùng trước.')
    return candidates[0] if candidates else canonical
