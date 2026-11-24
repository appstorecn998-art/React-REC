"""Per-profile display preferences, independent of business supplier identity."""
import json
from pathlib import Path
from receiving_service import atomic_json
from receiving_review import normalized

def read(root):
    try:
        d=json.loads((Path(root)/'.receiving/ui-preferences.json').read_text(encoding='utf-8'))
        return d if isinstance(d,dict) else {}
    except (OSError,ValueError):return {}

def update(root,**values):
    data=read(root);data.update(values);atomic_json(Path(root)/'.receiving/ui-preferences.json',data)

def nickname(root,name):return read(root).get('supplier_names',{}).get(normalized(name),'')

def set_nickname(root,name,label):
    if not normalized(name):raise ValueError('Chọn phiếu có NCC trước.')
    data=read(root);names=dict(data.get('supplier_names',{}))
    if label.strip():names[normalized(name)]=label.strip()
    else:names.pop(normalized(name),None)
    update(root,supplier_names=names)

def restore_window(w):
    from PySide6.QtCore import QByteArray
    data=read(w.root)
    if not data.get('remember_window',True):return
    raw=data.get('window_geometry','')
    try:
        if raw:w.restoreGeometry(QByteArray.fromBase64(raw.encode('ascii')))
    except (ValueError,TypeError,UnicodeError):pass

def save_window(w):
    if read(w.root).get('remember_window',True):update(w.root,window_geometry=bytes(w.saveGeometry().toBase64()).decode('ascii'))
