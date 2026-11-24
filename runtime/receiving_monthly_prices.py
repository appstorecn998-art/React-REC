"""Read-only monthly repeated-purchase price checks; no model training or inferred units."""
from pathlib import Path
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from collections import defaultdict
from receiving_service import paths,snapshot
from rec_receipt_search import normalize

def number(value):
 if isinstance(value,bool) or value is None:return None
 try:
  from AutoWatcher import parse_invoice_amount
  value=Decimal(str(parse_invoice_amount(value)))
  return value if value.is_finite() and value>=0 else None
 except (ValueError,TypeError,InvalidOperation):return None

def item_key(row):
 name=str(row.get('Tên hàng trên phiếu (Ảnh)') or row.get('Tên chuẩn hệ thống') or '').strip()
 code=normalize(row.get('Mã vật tư'))
 unit=normalize(row.get('Đơn vị trên phiếu') or row.get('Đơn vị tính'))
 if not name or not unit:return None
 if code in ('','chua co ma','unknown','none'):code=''
 from receiving_pr_match import specification
 spec=tuple(sorted((key,tuple(sorted(str(v) for v in values))) for key,values in specification(row).items()))
 # Exact source name fallback; never merge similar names or apply cross-supplier conversion.
 return ('code',code,unit,spec) if code else ('name',normalize(name),unit,spec)

def stamp(root,destination,day):
 import calendar
 found=[]
 for n in range(1,calendar.monthrange(day.year,day.month)[1]+1):
  _,report=paths(root,date(day.year,day.month,n),destination)
  if report.is_file():
   st=report.stat();found.append((str(report),st.st_size,st.st_mtime_ns,st.st_ctime_ns))
 # PR metadata changes must invalidate the cached comparison too.
 from receiving_service import accounting_root
 library=accounting_root(destination)/'.receiving'/'pr-library'/'index.json'
 metadata=[library]
 for report,*_ in found:
  metadata.extend((Path(report).parent/'.receiving'/'.receiving'/'manual-pr-links').glob('*.json'))
  metadata.append(Path(report).parent/'.receiving'/'price-pr-references.json')
 for path in sorted(set(metadata)):
  if path.is_file():
   st=path.stat();found.append((str(path),st.st_size,st.st_mtime_ns,st.st_ctime_ns))
 return tuple(found)

def scan(root,destination,day):
 before=stamp(root,destination,day);groups=defaultdict(list);errors=[];pr_errors=[];excluded=0
 import calendar
 report_days={}
 for n in range(1,calendar.monthrange(day.year,day.month)[1]+1):
  saved=date(day.year,day.month,n);_,report=paths(root,saved,destination)
  report_days[str(report)]=saved
 from receiving_pr_library import load
 from receiving_service import accounting_root,day_images
 from receiving_price_pr import receipt_pr_numbers,manual_reference
 from receiving_service import sheet_signature
 library_error=''
 try:orders=load(accounting_root(destination)/'.receiving'/'pr-library')
 except (OSError,ValueError,KeyError,TypeError) as exc:
  orders={};library_error='Không đọc được thư viện PR: '+str(exc);pr_errors.append(library_error)
 for path,*_ in before:
  if not path.endswith('.xlsx'):continue
  report=Path(path);saved=report_days[path]
  try:
   _,data=snapshot(report)
   image_error=''
   try:images=day_images(report.parent)
   except (OSError,ValueError,KeyError,TypeError) as exc:images=[];image_error=str(exc)
   for sheet,rows in data:
    pr_error=library_error or image_error;pr_numbers=[]
    if not pr_error:
     try:pr_numbers=receipt_pr_numbers(sheet,rows,images,report.parent/'.receiving',orders)
     except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:pr_error=str(exc)
    if pr_error:pr_errors.append(report.name+' / '+sheet+': '+pr_error)
    for physical,row in rows:
     key=item_key(row);price=number(row.get('Đơn giá'));quantity=number(row.get('Thực nhận'))
     if key is None or price is None or quantity is None or quantity<=0:excluded+=1;continue
     # Same reported price basis only. Missing tax metadata is never a proof of tax-inclusive price.
     basis=tuple((k,normalize(row.get(k))) for k in ('VAT','Thuế suất','Chiết khấu','Loại giá') if row.get(k) not in (None,''))
     supplier=normalize(row.get('Nhà cung cấp'))
     if supplier in ('','chua ro','chua ro ncc','ncc chua ro'):excluded+=1;continue
     groups[(key,basis,supplier)].append(dict(report=str(report),sheet=sheet,row=physical,day=saved.isoformat(),name=str(row.get('Tên hàng trên phiếu (Ảnh)') or row.get('Tên chuẩn hệ thống')),code=str(row.get('Mã vật tư') or ''),unit=str(row.get('Đơn vị trên phiếu') or row.get('Đơn vị tính')),supplier=str(row.get('Nhà cung cấp') or 'Chưa rõ NCC'),price=str(price),quantity=str(quantity),pr_numbers=pr_numbers,pr_error=pr_error,source_signature=sheet_signature(sheet,rows),manual_pr=manual_reference(report.parent/'.receiving',sheet,rows)))
  except (OSError,ValueError,KeyError) as exc:errors.append(report.name+': '+str(exc))
 warnings=[]
 for (key,basis,supplier),entries in groups.items():
  receipts={(r['report'],r['sheet']) for r in entries};prices={Decimal(r['price']) for r in entries}
  if len(receipts)<2 or len(prices)<2:continue
  changes=price_changes(entries)
  if changes<2:continue
  low,high=min(prices),max(prices)
  warnings.append(dict(key=repr((key,basis,supplier)),changes=changes,name=entries[0]['name'],code=entries[0]['code'],unit=entries[0]['unit'],purchases=len(receipts),prices=[str(v) for v in sorted(prices)],increase=None if low==0 else str((high-low)*100/low),entries=sorted(entries,key=lambda r:(r['day'],r['sheet'],r['row']),reverse=True)))
 after=stamp(root,destination,day)
 if before!=after:raise ValueError('Dữ liệu tháng đang thay đổi. Tải lại cảnh báo giá để kiểm tra bản mới.')
 return dict(month=f'{day.month:02d}/{day.year}',warnings=sorted(warnings,key=lambda r:normalize(r['name'])),errors=errors,pr_errors=list(dict.fromkeys(pr_errors)),excluded=excluded,stamp=after)


def price_changes(entries):
 """Count chronological changes between purchases, excluding mixed-price receipts."""
 purchases=defaultdict(set)
 for row in entries:purchases[row['day']].add(Decimal(row['price']))
 previous=None;changes=0
 for _,prices in sorted(purchases.items()):
  if len(prices)!=1:previous=None;continue
  current=next(iter(prices))
  if previous is not None and previous!=current:changes+=1
  previous=current
 return changes
