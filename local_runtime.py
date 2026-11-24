"""Locate the external REC data bundle without moving business logic."""
import json,os,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
APP=ROOT/'runtime'

def _data_bundle(root):
    root=Path(root)
    if (root/'local-data').is_dir():
        data=root/'local-data';profile=root/'local-profile'
    elif (root/'receipts').is_dir():
        data=root;profile=root/'profile'
    else:
        return None
    if not (data/'receipts').is_dir():return None
    return data,profile

def locate_data():
    candidates=[]
    configured=os.environ.get('REC_DATA_ROOT')
    if configured:candidates.append(Path(configured))
    location=ROOT/'data-location.json'
    if location.exists():
        try:
            value=json.loads(location.read_text(encoding='utf8')).get('path')
            if value:
                configured_path=Path(value)
                candidates.append(configured_path if configured_path.is_absolute() else ROOT/configured_path)
        except (OSError,ValueError,TypeError):pass
    candidates.extend([ROOT/'data',ROOT,ROOT.parent/'data',ROOT.parent/'React REC Data'])
    for drive in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        candidates.extend([Path(f'{drive}:/React REC Data'),Path(f'{drive}:/REC_DATA')])
    for candidate in candidates:
        bundle=_data_bundle(candidate)
        if bundle:return candidate.resolve(),bundle[0].resolve(),bundle[1].resolve()
    raise FileNotFoundError('Không tìm thấy dữ liệu REC. Đặt thư mục dữ liệu cạnh app hoặc cấu hình REC_DATA_ROOT/data-location.json.')

DATA_ROOT,DATA,PROFILE=locate_data()
STORE=DATA/'receipts'

def activate():
    os.environ['REC_DATA_DIR']=str(PROFILE)
    os.environ['REC_DATA_ROOT']=str(DATA_ROOT)
    if str(APP) not in sys.path:sys.path.insert(0,str(APP))
    return APP
