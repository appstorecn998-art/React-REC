"""Verified WebP receipt archive. Originals are never deleted here."""
from pathlib import Path
import hashlib, json, os, tempfile
from threading import RLock
ARCHIVE_LOCK=RLock()
from PIL import Image, ImageOps
from receiving_capture_time import captured_at

EXT={'.jpg','.jpeg','.png','.webp','.heic','.heif'}
def image_name(path):
    name=Path(path).name.casefold()
    if name.endswith('.webp') and Path(name[:-5]).suffix in EXT:
        return name[:-5]
    return name

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def entries(folder):
    path=Path(folder)/'image-manifest.json'
    return json.loads(path.read_text(encoding='utf-8')).get('files',[]) if path.exists() else []

def source_digest(path):
    path=Path(path)
    for entry in entries(path.parent):
        if entry['target']==path.name:
            if sha(path)!=entry['target_sha256']:raise ValueError('Ảnh lưu trữ đã thay đổi: '+str(path))
            return entry['source_sha256']
    return sha(path)

def archive_image(source,folder):
    source=Path(source);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    if source.suffix.lower() in {'.heic','.heif'}:
        try:
            from pillow_heif import register_heif_opener
        except ImportError as exc:
            raise ValueError('Chưa có bộ đọc HEIC/HEIF trong REC. Cần cài pillow-heif.') from exc
        with ARCHIVE_LOCK:register_heif_opener()
    original_hash=sha(source);key=source_digest(source)
    with ARCHIVE_LOCK:
        records=entries(folder)
        for entry in records:
            if entry['source_sha256']==key:
                target=folder/entry['target']
                if not target.is_file() or sha(target)!=entry['target_sha256']:raise ValueError('Bản ảnh lưu trữ thiếu hoặc sai hash: '+str(target))
                return target,False
        target=folder/(source.name+'.webp')
        if target.exists() or any(e['original'].casefold()==image_name(source) for e in records):
            raise ValueError('Tên ảnh trùng nhưng nội dung khác: '+source.name)
    fd,tmp=tempfile.mkstemp(dir=folder,suffix='.webp');os.close(fd)
    try:
        with Image.open(source) as raw:
            im=ImageOps.exif_transpose(raw).convert('RGB')
            im.save(tmp,'WEBP',quality=82,method=2,icc_profile=raw.info.get('icc_profile',b''))
            dimensions=im.size
        with Image.open(tmp) as check:
            check.load()
            if check.size!=dimensions:raise ValueError('Sai kích thước ảnh sau nén')
        # Retain original encoding when compression would increase storage.
        compression='webp-q82'
        if source.suffix.lower() not in {'.heic','.heif'} and Path(tmp).stat().st_size>=source.stat().st_size:
            target=folder/source.name
            if target.exists():raise ValueError('Ảnh đích đã tồn tại: '+str(target))
            Path(tmp).write_bytes(source.read_bytes());compression='original'
        if sha(source)!=original_hash:raise ValueError('Ảnh nguồn thay đổi trong khi nén')
        record=dict(original=source.name,target=target.name,source_sha256=key,target_sha256=sha(tmp),source_bytes=source.stat().st_size,target_bytes=Path(tmp).stat().st_size,dimensions=dimensions,compression=compression,captured_at=captured_at(source))
        # Encoding runs in parallel; publish image and manifest serially.
        with ARCHIVE_LOCK:
            records=entries(folder)
            for entry in records:
                if entry['source_sha256']==key:
                    existing=folder/entry['target']
                    if not existing.is_file() or sha(existing)!=entry['target_sha256']:raise ValueError('Bản ảnh lưu trữ thiếu hoặc sai hash: '+str(existing))
                    return existing,False
            if target.exists() or any(e['original'].casefold()==image_name(source) for e in records):
                raise ValueError('Tên ảnh trùng nhưng nội dung khác: '+source.name)
            os.replace(tmp,target)
            records.append(record)
            try:atomic_json(folder/'image-manifest.json',dict(version=1,files=records))
            except Exception:
                target.unlink(missing_ok=True);raise
        return target,True
    finally:Path(tmp).unlink(missing_ok=True)

def archive_directory(destination,day):
    from receiving_service import accounting_root
    root=accounting_root(destination)
    if root.name==str(day.year):root=root.parent
    return root/'AnhPhieu'/str(day.year)/f'Thang {day.month}'/f'Ngay {day.day:02d}'

def archived_images(directory):
    directory=Path(directory);link=directory/'.receiving'/'image-archive.json'
    if not link.exists():return []
    data=json.loads(link.read_text(encoding='utf-8'))
    folders=data.get('directories') or [data['directory']]
    result=[]
    for folder in map(Path,folders):
        folder = (link.parent / folder).resolve()
        if not (folder/'image-manifest.json').is_file():raise ValueError('Thiếu manifest ảnh: '+str(folder))
        for entry in entries(folder):
            p=folder/entry['target']
            if not p.is_file() or sha(p)!=entry['target_sha256']:raise ValueError('Ảnh lưu trữ thiếu hoặc sai hash: '+str(p))
            if p not in result:result.append(p)
    return result

def link_archive(directory,folder):
    link=Path(directory)/'.receiving'/'image-archive.json'
    data=json.loads(link.read_text(encoding='utf-8')) if link.exists() else {}
    folders=data.get('directories') or ([data['directory']] if data.get('directory') else [])
    target = Path(folder).resolve()
    if target in {(link.parent / path).resolve() for path in folders}:
        return
    # Keep an archive relative when on the same drive. Windows requires an absolute
    # path when the report and archive are on different drives.
    value = os.path.relpath(target, link.parent) if target.drive == link.drive else str(target)
    folders.append(value)
    atomic_json(link,{'directories':folders})
