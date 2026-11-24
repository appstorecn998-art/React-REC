"""Explicit supplier-scoped equivalence; never converts mass to volume."""
import json,shutil
from datetime import datetime
from pathlib import Path
from receiving_link_memory import pair_key
from receiving_service import atomic_json

def equivalent(item,delivery,root=None):
    from rec_runtime import user_root
    try:
        rules=json.loads((Path(root or user_root())/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
        key=pair_key(item,delivery,rules)
        return any(r.get('key')==key and r.get('reason') for r in rules.get('pr_spec_equivalences',[]))
    except (OSError,ValueError,KeyError,TypeError):return False

def remember(root,item,delivery,reason):
    if not str(reason).strip():raise ValueError('Nhập căn cứ xác nhận cùng quy cách.')
    from multi_delivery import output_lock
    path=Path(root)/'NhaCungCap.json'
    with output_lock(path):
        original=path.read_bytes();rules=json.loads(original.decode('utf-8-sig'))
        key=pair_key(item,delivery,rules)
        records=rules.setdefault('pr_spec_equivalences',[])
        if any(r.get('key')==key for r in records):return
        records.append({'key':key,'reason':str(reason).strip(),'confirmed_at':datetime.now().astimezone().isoformat()})
        backup=Path(root)/'.autowatcher-backups'/('spec-equivalence-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup.mkdir(parents=True);shutil.copy2(path,backup/path.name)
        if path.read_bytes()!=original:raise ValueError('Quy tắc đã đổi. Thử lại.')
        atomic_json(path,rules)
