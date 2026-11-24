"""Resource and per-user paths shared by source and frozen REC processes."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

VERSION = '0.9.0-rc1'


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def user_root():
    return Path(os.environ.get('REC_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'REC')


def atomic_bytes(path, content):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name+'.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def initialize(legacy=None):
    root = user_root(); root.mkdir(parents=True, exist_ok=True)
    # Explicit data-dir requests are isolated: do not copy a real user's keys.
    legacy = Path(legacy) if legacy else resource_root()
    migrate = not os.environ.get('REC_DATA_DIR') and not getattr(sys, 'frozen', False)
    marker = root/'.receiving'/'migration-v1.json'
    if migrate and not marker.exists() and legacy.resolve()!=root.resolve():
        names = ['DanhMuc.xlsm', 'NhaCungCap.json', 'gemini_api_key.txt', 'google-sheets-key.json']
        names += ['.receiving/'+p.name for p in (legacy/'.receiving').glob('*.json')]
        for name in names:
            src, dst = legacy/name, root/name
            if src.is_file() and not dst.exists(): atomic_bytes(dst, src.read_bytes())
        atomic_bytes(marker, json.dumps({'version':1,'source':str(legacy)}, ensure_ascii=False).encode())
    for name in ['DanhMuc.xlsm','NhaCungCap.json','Phieu giao hang ngay X.xlsx']:
        if not (root/name).exists() and (resource_root()/name).is_file():
            atomic_bytes(root/name, (resource_root()/name).read_bytes())
    model = root/'models'; model.mkdir(exist_ok=True)
    bundled = resource_root()/'ocr_models'
    fallback = Path.home()/'.EasyOCR/model'
    for name in ['craft_mlt_25k.pth','latin_g2.pth']:
        dst = model/name
        src = bundled/name
        if not src.is_file() and migrate: src = fallback/name
        if not dst.exists() and src.is_file(): atomic_bytes(dst, src.read_bytes())
    return root


def process_command(kind, arguments, data_dir):
    if kind not in ('worker','locate'): raise ValueError('Unknown REC process')
    if getattr(sys,'frozen',False):
        return sys.executable, ['--rec-'+kind,'--data-root',str(data_dir),*map(str,arguments)]
    executable = Path(sys.executable)
    if executable.name.lower()=='pythonw.exe': executable=executable.with_name('python.exe')
    return str(executable), ['-B','-X','utf8','-u',str(resource_root()/'rec_launcher.py'),
                             '--rec-'+kind,'--data-root',str(data_dir),*map(str,arguments)]


def repair_models(root):
    import hashlib
    expected=json.loads((resource_root()/'models-manifest.json').read_text(encoding='utf-8'))
    sources={}
    for name,meta in expected.items():
        if Path(name).name!=name:raise ValueError('Invalid model filename')
        source=resource_root()/'ocr_models'/name
        if not source.is_file() and not getattr(sys,'frozen',False):source=Path.home()/'.EasyOCR/model'/name
        content=source.read_bytes()
        if hashlib.sha256(content).hexdigest()!=meta['sha256']:raise ValueError('Invalid model checksum')
        sources[name]=content
    for name,content in sources.items():atomic_bytes(Path(root)/'models'/name,content)


def config_check(root=None):
    root = Path(root or user_root()); checks={}
    try:
        from AutoWatcher import load_catalog_data
        cat, groups = load_catalog_data(root/'DanhMuc.xlsm')
        from supplier_rules import read_rules
        read_rules(root/'NhaCungCap.json',cat,groups)
        checks['catalog'] = {'ok':True,'rows':len(cat)}
    except Exception:
        checks['catalog']={'ok':False,'message':'Chọn DanhMuc.xlsm và kiểm tra NhaCungCap.json.'}
    key=os.environ.get('GEMINI_API_KEY','').strip()
    if not key:
        try:key=(root/'gemini_api_key.txt').read_text(encoding='utf-8-sig').strip()
        except OSError:pass
    checks['gemini']={'ok':bool(key),'message':'Đã cấu hình; chưa kiểm tra kết nối.' if key else 'Chưa nhập khóa Gemini.'}
    try:
        data=json.loads((root/'google-sheets-key.json').read_text(encoding='utf-8-sig'))
        from google.oauth2.service_account import Credentials
        Credentials.from_service_account_info(data,scopes=['https://www.googleapis.com/auth/spreadsheets'])
        checks['sheets']={'ok':True,'message':'Cấu hình hợp lệ; chưa kiểm tra quyền bảng thật.'}
    except Exception:
        checks['sheets']={'ok':False,'message':'Chưa có cấu hình Google Sheets hợp lệ.'}
    checks['template']={'ok':(root/'Phieu giao hang ngay X.xlsx').is_file(),'message':'Mẫu phiếu giao hàng19 cột.'}
    import hashlib
    try:
        expected=json.loads((resource_root()/'models-manifest.json').read_text(encoding='utf-8'))
        models_ok=bool(expected) and all((root/'models'/name).is_file() and hashlib.sha256((root/'models'/name).read_bytes()).hexdigest()==meta['sha256'] for name,meta in expected.items())
    except (OSError,ValueError,KeyError,TypeError):models_ok=False
    checks['ocr']={'ok':models_ok,
                   'message':'Model OCR cục bộ (không tự tải qua mạng).'}
    try:
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=root):pass
        checks['writable']={'ok':True}
    except OSError:checks['writable']={'ok':False,'message':'Không ghi được thư mục dữ liệu.'}
    return {'version':VERSION,'data_root':str(root),'checks':checks,'network_requests':0}
