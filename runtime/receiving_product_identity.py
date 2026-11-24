"""Conservative identity evidence for positional matching across product groups."""
import re
from receiving_review import normalized

# Linguistic equivalents only: never supplier-specific SKU/size conversions.
EQUIVALENTS=(('thit ba roi','thit ba chi'),('ba roi','ba chi'),('thit lon','thit heo'),('dau phong','lac'),('hat lac','lac'),('bap ngo','ngo'),('bap','ngo'),('dua leo','dua chuot'),('ngò rí','rau mui'),('ngo ri','rau mui'),('rau mui ta','rau mui'),('mi chinh','bot ngot'),('kho qua','muop dang'))
GENERIC={'thit','rau','cu','qua','trai','hat','dau','nuoc','sot','sauce','fresh','veg','vegetable','food','tuoi','kho','dong','lanh','nguyen','lam','sach','goi','hop','chai','tui','bich','kg','g','gr','ml','l','pcs','pack','bag','box','can','lon','loai','cao','cap','dac','biet'}

def canonical(value):
    text=' '+normalized(value)+' '
    for source,target in EQUIVALENTS:text=text.replace(' '+normalized(source)+' ',' '+normalized(target)+' ')
    return text.strip()

def source(item):return str(item.get('item_name') or item.get('Tên hàng trên phiếu (Ảnh)') or '')

def identity_words(item):
    text=re.sub(r'\d+(?:[.,]\d+)?\s*(?:kg|gr|g|ml|l)\b',' ',canonical(source(item)))
    return {w for w in text.split() if not w.isdigit()}-GENERIC

def positional_identity(a,b):
    # A common generic "meat/oil/dried" token is insufficient. Unsupported
    # regional/translated names remain unassigned, never forced by STT.
    x,y=identity_words(a),identity_words(b)
    return bool(x and y and x&y and (x<=y or y<=x))

def linguistic_parts(value):return canonical(value)
