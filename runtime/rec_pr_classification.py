"""Presentation-only PR categories; unknown values never infer supplier/department."""
from supplier_rules import normalize_name
UNKNOWN='Chưa phân loại'
def category(record,field):
 raw=str(record.get(field) or '').strip()
 unknown={'','unknown','none','null','n a','na','khong ro','chua ro','chua xac dinh','chua phan loai','khong doc duoc','khong xac dinh'}
 key=normalize_name(raw)
 if key in unknown or key in {'chua ro ncc','chua ro bo phan'}:return UNKNOWN
 if field=='department':
  from receiving_department_sheets import canonical,TABS
  code=canonical(raw)
  if code:return TABS[code]
 return raw.upper() if field=='supplier' else raw

def unclassified(record):return any(category(record,f)==UNKNOWN for f in ('supplier','department'))
