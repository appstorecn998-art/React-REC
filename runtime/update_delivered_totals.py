from pathlib import Path
import sys,tempfile,os
sys.path.insert(0,'C:/Users/Fenn/Desktop/Auto')
from openpyxl import load_workbook
import AutoWatcher as aw
from multi_delivery import output_lock
from received_amounts import apply_delivered_total,DELIVERED_TOTAL_HEADER
root=Path(__file__).resolve().parent;p=root/'TongHopNhieuPhieuGiaoHang.xlsx'
with output_lock(p):
 digest=aw.delivery_report_digest(p)
 book=load_workbook(p);temporary=None
 try:
  before={s.title:[[c.value for c in row] for row in s] for s in book}
  updated=sum(apply_delivered_total(s) for s in book)
  if not updated:print('Tổng đã có, không cần ghi lại.');raise SystemExit(0)
  for s in book:
   for r,row in enumerate(before[s.title],1):
    for c,value in enumerate(row,1):assert s.cell(r,c).value==value,(s.title,r,c)
  book.calculation.calcMode='auto';book.calculation.fullCalcOnLoad=True;book.calculation.forceFullCalc=True
  with tempfile.NamedTemporaryFile(dir=p.parent,suffix='.xlsx',delete=False) as h:temporary=Path(h.name)
  book.save(temporary);book.close()
  assert aw.delivery_report_digest(p)==digest,'TongHop changed, no overwrite'
  backup=root/'.autowatcher-backups'/('delivered-total-'+aw.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))/p.name
  aw.atomic_copy_file(p,backup)
  os.replace(temporary,p)
  print('Updated',updated,'sheets; existing values/formulas unchanged; backup:',backup)
 finally:
  book.close()
  if temporary is not None:temporary.unlink(missing_ok=True)
