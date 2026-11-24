"""Receipt confirmation requires an assigned department for every item row."""
def missing_departments(rows):
    missing=[]
    for row,value in rows:
        name=str(value.get('Tên hàng trên phiếu (Ảnh)') or '').strip()
        department=str(value.get('Bộ phận') or '').strip()
        if name and department.casefold() in ('','—','-','chưa chọn','chưa xác định','chưa chọn bộ phận'):
            missing.append((row,name))
    return missing

def department_message(rows):
    missing=missing_departments(rows)
    if not missing:return ''
    return 'Chưa chọn bộ phận cho '+str(len(missing))+' dòng hàng. Chọn bộ phận trước khi xác nhận:\n'+'\n'.join('Dòng '+str(row-1)+': '+name for row,name in missing[:12])+ ('\n…' if len(missing)>12 else '')

def require_departments(rows):
    message=department_message(rows)
    if message:raise ValueError(message)
