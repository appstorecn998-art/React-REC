"""Nhận diện chứng từ đầu vào và ghép trang bằng dữ kiện đọc trên giấy."""
import re
from supplier_rules import normalize_name

DOCUMENT_TYPES_PROMPT = """
Phân loại theo nội dung chứng từ, không chỉ theo chữ trong tiêu đề:
- pr: yêu cầu mua hàng nội bộ/PR, chưa phải chứng từ của bên bán. Tiêu đề rõ
  PHIẾU ĐỀ NGHỊ MUA HÀNG / PURCHASE REQUEST là PR, dù có cột NCC và chữ ký duyệt.
- po: đơn đặt hàng của bên mua, tiêu đề ĐƠN HÀNG / PURCHASE ORDER hoặc
  có Số PO của chính chứng từ. reference_id là Số PO; Số PR ghi riêng vào
  pr_reference_id. Ngày giao dự kiến, cột số lượng/giá/thuế/tiền và chữ ký
  duyệt đơn không phải bằng chứng thực nhận. received_quantity luôn rỗng.
- delivery: phiếu giao/xuất hàng, hóa đơn bán hàng, hoặc đề nghị/thông báo
  thanh toán của NHÀ CUNG CẤP có các dòng hàng/dịch vụ và số tiền cụ thể.
  Đề nghị thanh toán dịch vụ VNPT (hóa đơn điện tử, chữ ký số), phí kiểm nghiệm
  Intertek cũng thuộc đầu vào delivery; document_kind="service_payment".
  Tên loại delivery là nhóm xử lý đầu vào, không khẳng định hàng đã được giao.
- other: không có dòng hàng/dịch vụ đủ căn cứ để đọc, báo giá thuần túy hoặc tài liệu khác.
Ngoại lệ: tờ mẫu BẢNG BÁO GIÁ được dùng làm chứng từ giao hàng thực tế, có lượng
thực nhận viết tay rõ ràng theo từng dòng và dấu hiệu xác nhận nhận hàng, là delivery.
Chỉ có chữ ký/ghi chú chung không đủ để chuyển báo giá thành phiếu giao.
Giữ quantity là lượng in sẵn; received_quantity chỉ lấy lượng thực nhận viết tay đọc rõ,
receipt_mark theo bằng chứng thực nhận. Thiếu/không rõ thì rỗng và receipt_mark="unclear";
không lấy lượng báo giá làm lượng đã nhận, không tự đổi gói sang cái nếu chưa có
quy đổi xác nhận. Ghi chú như “16 gói 50, 4 gói 49” giữ nguyên trong specification,
không cộng gói/cái lẫn nhau. Ngày báo giá chỉ là document_date; không suy delivery_date.
Trang tiếp theo có thể thuộc PR, PO hoặc phiếu giao. Không mặc định bảng thiếu tiêu đề
là PR. Dựa vào các dấu hiệu thực tế; thiếu căn cứ thì other, không tự đổi loại.
Với giao hàng thông thường document_kind="goods". Giữ từng dòng dịch vụ, kể cả
dòng miễn phí. Không thêm dòng Tổng cộng/VAT vào danh sách mặt hàng. Chỉ chép
số lượng, đơn vị, đơn giá, thành tiền có trên giấy; thiếu để rỗng, không tự gán 1
hay lấy số tiền làm đơn giá. Dấu '-' ở tiền để rỗng, không tự coi bằng 0.
Phiếu dịch vụ không chứng minh thực nhận: receipt_mark="not_applicable",
received_quantity=""; không bịa ngày giao từ ngày hóa đơn/ngày đề nghị thanh toán.
document_date là ngày lập/đề nghị thanh toán nhìn thấy trên giấy; với dịch vụ,
delivery_date luôn rỗng. Không lấy Ngày HĐ làm ngày giao hàng.
Đọc STT IN TRÊN GIẤY vào source_stt cho từng dòng; không tự đánh số từ vị trí
trong ảnh. Giữ STT lặp như giấy; không có/không rõ thì rỗng. Không gộp dòng lặp.
has_stt_column=false khi bảng không có cột STT/số thứ tự của dòng hàng (ví dụ
bảng Intertek chỉ có Ngày HĐ, Số Hóa Đơn, Công việc, Người mua, Loại tiền, Số tiền).
Khi đó source_stt của TẤT CẢ dòng phải rỗng, kể cả chỉ có một dòng dịch vụ.
Đọc page_number nếu có số trang, không có thì rỗng. has_total=true chỉ khi ảnh
có dòng tổng kết cuối phiếu; cộng chuyển trang/cộng mang sang không phải cuối.
reference_id phải là số của CHỨNG TỪ HIỆN TẠI, không lấy số PR/PO tham chiếu
thay số phiếu giao. Số PR tham chiếu chỉ để trong pr_reference_id.
"""


def stt_number(value):
    raw = str(value or "").strip()
    return int(raw) if re.fullmatch(r"\d{1,6}", raw) and int(raw) > 0 else None


def page_number(value):
    return stt_number(str(value or '').partition('/')[0])


def missing_pages(entries):
    documents = [entry['document'] for entry in entries]
    pages = [page_number(doc.get('page_number')) for doc in documents]
    numbered = [page for page in pages if page is not None]
    first_rows = numbers(entries[0])
    if (pages[0] and pages[0] > 1) or (not pages[0] and first_rows and first_rows[0] > 1):
        return 'Thiếu trang đầu hoặc phần đầu bảng hàng.'
    if any(b > a + 1 for a, b in zip(numbered, numbered[1:])):
        return 'Có khoảng thiếu giữa các số trang.'
    expected = {total for doc in documents
                if (total := stt_number(doc.get('page_number', '').partition('/')[2]))}
    if expected and (len(expected) != 1 or len(set(numbered)) != min(expected) or max(numbered, default=0) != min(expected)):
        return 'Chưa đủ số trang in trên phiếu.'
    return ''


def numbers(entry):
    return [n for item in entry['document']['items']
            if (n := stt_number(item.get('source_stt'))) is not None]


def comparison_value(field, value):
    if field in ('delivery_date', 'document_date'):
        from datetime import datetime
        for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try: return datetime.strptime(str(value).strip(), pattern).date().isoformat()
            except ValueError: pass
    return normalize_name(value or '')


def continuation_candidate(previous, current):
    left, right = previous['document'], current['document']
    if any(d.get('document_type') != 'delivery' for d in (left,right)) or left.get('has_total'):
        return False
    for field in ('supplier_name','reference_id','delivery_date','document_kind','pr_reference_id'):
        a,b = comparison_value(field,left.get(field,'')),comparison_value(field,right.get(field,''))
        if a and b and a != b: return False
    if left.get('document_kind') == 'service_payment':
        a,b = comparison_value('document_date',left.get('document_date','')),comparison_value('document_date',right.get('document_date',''))
        if a and b and a != b: return False
    before,after = numbers(previous),numbers(current)
    p,q = page_number(left.get('page_number')),page_number(right.get('page_number'))
    if p and q and q != p+1: return False
    if before and after: return after[0] == before[-1]+1 and after[0] != 1
    return bool(p and q and q == p+1)


def continues_invoice(previous, current):
    """Chỉ xét ảnh liên tiếp; không ghép theo NCC đơn thuần."""
    left, right = previous['document'], current['document']
    if left.get('document_type')!='delivery' or right.get('document_type')!='delivery':return False
    for field in ('supplier_name','reference_id','delivery_date','document_kind','pr_reference_id'):
        a,b=comparison_value(field,left.get(field,'')),comparison_value(field,right.get(field,''))
        if a and b and a!=b:return False
    before,after=numbers(previous),numbers(current)
    p,q=page_number(left.get('page_number')),page_number(right.get('page_number'))
    if left.get('has_total',False):return False
    # Supplier, STT and page numbering may all repeat on separate invoices.
    # An explicit shared delivery-document number is mandatory for auto-merge.
    ref=normalize_name(left.get('reference_id',''))
    if not ref or ref!=normalize_name(right.get('reference_id','')):return False
    if after and after[0]==1:return False
    if before and after and after[0]<=before[-1]:return False
    if p and q and q!=p+1:return False
    if before and after:
        return after[0]==before[-1]+1
    # Without item numbering, require exactly consecutive printed page numbers.
    return bool(p and q and q==p+1)


def ambiguous_continuation(previous,current):
    """Only a review hint; never a reason to merge or discard either image."""
    left,right=previous['document'],current['document']
    if left.get('document_type')!='delivery' or right.get('document_type')!='delivery':return False
    if left.get('has_total',False):return False
    for field in ('supplier_name','reference_id','delivery_date','document_kind','pr_reference_id'):
        a,b=comparison_value(field,left.get(field,'')),comparison_value(field,right.get(field,''))
        if a and b and a!=b:return False
    supplier=normalize_name(left.get('supplier_name',''))
    if not supplier or supplier!=normalize_name(right.get('supplier_name','')):return False
    before,after=numbers(previous),numbers(current)
    p,q=page_number(left.get('page_number')),page_number(right.get('page_number'))
    return bool((before and after and after[0]>before[-1]) or (p and q and q==p+1))



def sequence_warnings(entries):
    values = [stt_number(item.get('source_stt')) for entry in entries
              for item in entry['document']['items']]
    warnings = []
    if any(value is None for value in values):
        warnings.append('Có dòng không đọc được STT; chưa kiểm đủ thiếu/trùng dòng.')
    seen = set()
    duplicates = set()
    missing = []
    previous = 0
    for value in values:
        if value is None:
            continue
        if value in seen:
            duplicates.add(value)
        elif value > previous + 1:
            missing.append(str(previous + 1) if value == previous + 2 else f'{previous + 1}–{value - 1}')
        elif value < previous:
            warnings.append('STT không tăng theo thứ tự ảnh; kiểm lại thứ tự trang.')
        seen.add(value)
        previous = max(previous, value)
    if missing:
        warnings.append('STT có khoảng thiếu: ' + ', '.join(missing[:12]) + '; kiểm lại ảnh.')
    if duplicates:
        warnings.append('STT lặp: ' + ', '.join(map(str, sorted(duplicates)[:12]))
                        + '; giữ mọi dòng để rà phần ảnh chồng nhau.')
    pages = [page_number(entry['document'].get('page_number')) for entry in entries]
    if any(a and b and b > a + 1 for a, b in zip(pages, pages[1:])):
        warnings.append('Số trang có khoảng thiếu; kiểm lại ảnh.')
    return list(dict.fromkeys(warnings))
