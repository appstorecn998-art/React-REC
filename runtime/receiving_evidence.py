"""Immutable local image evidence shared by confirmation forms."""
import hashlib,copy
from pathlib import Path
from datetime import datetime,timezone

def validate(refs):
 for ref in refs or []:
  path=Path(ref['path'])
  if not path.is_absolute() or path.suffix.lower()!='.png' or not path.is_file():raise ValueError('Ảnh bằng chứng đã mất hoặc đường dẫn không hợp lệ.')
  if hashlib.sha256(path.read_bytes()).hexdigest()!=ref.get('sha256'):raise ValueError('Ảnh bằng chứng đã thay đổi so với bản đã lưu.')
 return True

def strip(rule):return {k:v for k,v in rule.items() if k not in ('attachments','attachment_history')}

def attach(rule,refs,old=None):
 value=copy.deepcopy(rule);previous=old or {}
 if refs:value['attachments']=copy.deepcopy(refs)
 events=copy.deepcopy(previous.get('attachment_history',[]))
 if refs or previous.get('attachments'):
  events.append(dict(time=datetime.now(timezone.utc).isoformat(),attachments=copy.deepcopy(refs),rule={k:v for k,v in rule.items() if k not in ('attachments','attachment_history','history')}))
 if events:value['attachment_history']=events
 if value.get('history') and refs:value['history'][-1]['attachments']=copy.deepcopy(refs)
 return value



def audit_images(path,subject):
 import json,sqlite3
 from contextlib import closing
 if not Path(path).is_file():return {}
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as conn:
  events=[]
  for stamp,raw in conn.execute('SELECT time,after_json FROM audit WHERE receipt_id=? ORDER BY time',(subject,)):
   event=json.loads(raw)
   if event.get('attachments'):events.append(dict(time=stamp,attachments=event['attachments']))
 return dict(attachment_history=events)


def confirmation_path(w,kind,row,item,delivery):
 import json
 if callable(getattr(w,'ledger_path',None)):directory=Path(w.ledger_path()).parent/'approval-evidence/history'
 elif getattr(w,'root',None):directory=Path(w.root)/'.receiving/approval-evidence/history'
 else:return None
 context=[str(getattr(w,'report','')),getattr(w,'current_sheet',''),kind,row,{k:item.get(k) for k in ('item_name','unit','specification','pr_reference_id','pr_document_date')},delivery.get('Nhà cung cấp')]
 key=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
 return directory/(key+'.json')

def with_history(w,kind,row,item,delivery,old):
 import json
 value=copy.deepcopy(old or {});path=confirmation_path(w,kind,row,item,delivery)
 if path and path.exists():
  try:
   data=json.loads(path.read_text(encoding='utf-8'))
   if data.get('version')!=1 or not isinstance(data.get('events'),list):raise ValueError('Lịch sử ảnh xác nhận không hợp lệ; chưa ghi đè.')
   value['attachment_history']=[*value.get('attachment_history',[]),*data['events']]
  except (OSError,ValueError):value['_evidence_history_error']='Không đọc được lịch sử ảnh. Bản cũ được giữ; cần kiểm tra tệp lịch sử trước khi ghi tiếp.'
 return value

def journal(w,kind,row,item,delivery,rule,action='approve'):
 import json,uuid
 path=confirmation_path(w,kind,row,item,delivery)
 if path is None:return
 refs=(rule or {}).get('attachments',[])
 if not refs and not path.exists() and not (rule or {}).get('attachment_history'):return
 if action=='approve':validate(refs)
 from multi_delivery import output_lock
 from receiving_service import atomic_json
 path.parent.mkdir(parents=True,exist_ok=True)
 with output_lock(path):
  data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(version=1,events=[])
  if data.get('version')!=1 or not isinstance(data.get('events'),list):raise ValueError('Lịch sử ảnh xác nhận không hợp lệ; chưa ghi đè.')
  event=dict(id=uuid.uuid4().hex,time=datetime.now(timezone.utc).isoformat(),action=action,stage='confirmation_in_comparison',kind=kind,row=row,item=item.get('item_name'),supplier=delivery.get('Nhà cung cấp'),attachments=copy.deepcopy(refs),rule={k:v for k,v in (rule or {}).items() if k not in ('attachments','attachment_history','history')})
  data['events'].append(event);atomic_json(path,data)
