"""Tìm ứng viên toàn danh mục, chuẩn hóa quy cách mà không tạo mã mới."""
from collections import Counter
from decimal import Decimal
import math
import re
from supplier_rules import normalize_name

STOP={'pro','sf','food','foods','the','and','of','bag','pack','pkt','box','dong','goi','gr','g','kg','ml','l','pcs','pc','each'}

CATALOG_FIRST_PROMPT = """
THỨ TỰ ĐỐI CHIẾU: tìm mã và tên trong DanhMucGoc theo chính mặt hàng trước.
Candidates đã tìm trên toàn danh mục, không bị cắt theo NCC hoặc nhóm OCR.
Kiểm tên Việt/Anh, nhãn hiệu, giống, trạng thái tươi/khô/đóng hộp/nước ép,
quy cách, kích cỡ, xuất xứ và đơn vị. Không dùng sản phẩm gần giống để lấp mã.
Sau đó mới xem supplier_context và PR để bổ trợ; nhóm NCC/OCR có thể không
trùng nhóm thực trong danh mục. Không loại mã đúng chỉ vì khác nhóm NCC/OCR;
không chọn mã sai để vừa NCC. Mã in trên chứng từ chỉ là gợi ý cần kiểm tên.
Thiếu thông tin phân biệt nhiều SKU: để mã trống, needs_review=true, nêu các
mã cần người dùng xác nhận. Không chọn theo độ phổ biến hay độ giống chữ.
Chỉ trả catalog_code, confidence, needs_review và note cho đúng dòng; không
sửa số lượng, thực nhận, đơn giá, tên nguồn hay dữ liệu nghiệp vụ khác.
"""


def product_mismatch(source_name, catalog_name):
    """Reject explicit contradictory sizes/forms; absence of a detail is not proof."""
    source_sizes, catalog_sizes = sizes(source_name), sizes(catalog_name)
    shared_kinds = {kind for kind, _ in source_sizes} & {kind for kind, _ in catalog_sizes}
    for kind in shared_kinds:
        if not ({value for candidate_kind, value in source_sizes if candidate_kind == kind}
                & {value for candidate_kind, value in catalog_sizes if candidate_kind == kind}):
            return 'Quy cách số/dung lượng khác danh mục.'
    forms = {'juice': ('nuoc ep', 'juice'), 'syrup': ('siro', 'si ro', 'syrup'),
             'jam': ('mut', 'jam', 'marmalade'), 'dried': ('kho', 'say', 'dried'),
             'frozen': ('dong lanh', 'frozen'), 'fresh': ('tuoi', 'fresh')}
    def detect(value):
        normalized = ' ' + normalize_name(value) + ' '
        return {kind for kind, words in forms.items() if any(' '+word+' ' in normalized for word in words)}
    source_forms, target_forms = detect(source_name), detect(catalog_name)
    if not target_forms and normalize_name(catalog_name).startswith(('fruit ', 'fresh fruit ')):
        target_forms = {'fresh'}
    if source_forms and target_forms and not source_forms & target_forms:
        return 'Dạng sản phẩm khác danh mục (tươi/khô/nước ép/đóng hộp...).'
    return ''


def tokens(value):
    normalized=normalize_name(value)
    return {word for word in normalized.split() if word not in STOP and not word.isdigit()}


def sizes(value):
    result=set()
    for amount,unit in re.findall(r'(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|cl|litre|liter|l)\b',value.casefold()):
        number=Decimal(amount.replace(',','.'))
        kind='mass' if unit in {'kg','gr','g'} else 'volume'
        multiplier={'kg':1000,'gr':1,'g':1,'ml':1,'cl':10,'l':1000,'litre':1000,'liter':1000}[unit]
        result.add((kind,number*multiplier))
    return result


def ranked_candidates(name,catalog,limit=30):
    query=tokens(name);query_sizes=sizes(name)
    indexed=[(code,label,unit,tokens(label)) for code,(label,unit) in catalog.items()]
    frequency=Counter(word for _,_,_,words in indexed for word in words)
    weights={word:math.log(1+len(indexed)/(1+frequency[word])) for word in query}
    ranked=[]
    for code,label,unit,words in indexed:
        shared=query & words
        if not shared:continue
        score=sum(weights[w] for w in shared)/max(1,sum(weights.values()))
        score+=len(shared)/max(1,len(query|words))
        candidate_sizes=sizes(label)
        if query_sizes and candidate_sizes:
            if query_sizes & candidate_sizes:score+=0.8
            else:score-=1.5
        ranked.append((score,code,label,unit))
    ranked.sort(key=lambda row:(-row[0],row[1]))
    return [[code,label,unit] for score,code,label,unit in ranked[:limit]]
