"""Read-only, explainable source validation for a recorded receipt."""
import json
from pathlib import Path
from receiving_service import snapshot,sheet_signature,digest

def inspect(payload):
    checks=[];rows=[]
    try:
        _,data=snapshot(payload['report']);rows=dict(data).get(payload['sheet'],[])
        valid=bool(rows) and sheet_signature(payload['sheet'],rows)==payload['signature']
        checks.append(('Dữ liệu phiếu Excel',valid,'Khớp lần ghi sổ' if valid else 'Phiếu đã sửa hoặc không còn trong báo cáo'))
    except (OSError,ValueError,KeyError) as e:checks.append(('Báo cáo Excel',False,str(e)))
    try:
        reviews=json.loads(Path(payload['reviews_path']).read_text(encoding='utf-8'));valid=reviews.get(payload['sheet'])==payload['signature']
        checks.append(('Xác nhận kiểm tra',valid,'Khớp lần ghi sổ' if valid else 'Bỏ xác nhận, chưa kiểm lại hoặc xác nhận cho phiên bản phiếu khác'))
    except (OSError,ValueError,KeyError) as e:checks.append(('Xác nhận kiểm tra',False,str(e)))
    try:
        valid=digest(payload['pr_link_path'])==payload['pr_link_hash'];checks.append(('Liên kết PR',valid,'Không đổi' if valid else 'Đã chọn lại PR sau khi ghi sổ'))
    except (OSError,ValueError,KeyError) as e:checks.append(('Liên kết PR',False,str(e)))
    for kind,key in [('Ảnh phiếu','source_images'),('Ảnh PR','pr_images')]:
        for name,expected in payload.get(key,{}).items():
            try:valid=Path(name).is_file() and digest(name)==expected
            except OSError:valid=False
            checks.append((kind+' · '+Path(name).name,valid,'Không đổi' if valid else 'Ảnh mất hoặc nội dung đổi'))
    old=payload.get('source_rows')
    if old and rows:
        old_values={r:v for r,v in old};new_values=dict(rows)
        changes=[]
        for r in set(old_values)|set(new_values):
            a,z=old_values.get(r,{}),new_values.get(r,{})
            for field in set(a)|set(z):
                if str(a.get(field,''))!=str(z.get(field,'')):changes.append('Dòng '+str(r-1)+' · '+field+': '+str(a.get(field,''))+' → '+str(z.get(field,'')))
        for detail in changes[:50]:checks.append(('Thay đổi so với lần ghi sổ',False,detail))
    elif not old:checks.append(('Chi tiết phiên bản cũ',True,'Lần ghi sổ cũ chưa lưu bản chụp từng dòng; không thể suy ra trường đã đổi.'))
    return checks,rows
