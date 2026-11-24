"""Căn cứ phân kho từ PR; không đoán người đề nghị từ NCC/người ký."""
from supplier_rules import normalize_name
import re

PR_HEADERS = ('Người đề nghị PR', 'Căn cứ PR phân kho')
VERIFIED_PR = 'ĐÃ GHÉP PR'
CONFIRM_PREFIX = '[XÁC NHẬN KHO]'
REQUESTER_PROMPT = '''
Tiêu đề rõ PHIẾU ĐỀ NGHỊ MUA HÀNG / PURCHASE REQUEST xác định document_type=pr,
kể cả bảng PR có cột Nhà cung cấp và chữ ký duyệt; không nhầm thành phiếu giao.
Trên PR, reference_id và pr_reference_id là Số/No ở đầu phiếu, giữ nguyên số 0 đầu
(ví dụ 02); không lấy STT dòng, số trang, mã vật tư hoặc số ngày ký làm số PR.
Trên PR, document_date là Ngày/Date in ở đầu phiếu, chuẩn YYYY-MM-DD; không lấy ngày
viết tay dưới chữ ký. department_name lấy mục Bộ phận/Department, không suy từ tên người.
Trên PR, supplier_name lấy đơn vị ở cột Nhà cung cấp/Supplier nếu mọi dòng cùng NCC;
nhiều NCC thì để rỗng, không lấy công ty đặt hàng ở tiêu đề làm NCC.
Trên PO, supplier_name lấy mục Nhà cung cấp/Supplier, document_date là ngày lập
đơn và department_name lấy Bộ phận đề xuất. Ngày giao dự kiến không thay ngày lập.
Trên phiếu giao, pr_date/pr_department chỉ đọc ngày PR/bộ phận tham chiếu được ghi rõ;
không thay bằng ngày giao hoặc đoán. Không thấy thì để rỗng.

requester_name: chỉ đọc mục Người đề nghị/Requested by/Requisitioned by trên PR hoặc PO.
Giữ đầy đủ dấu nếu đọc được; thiếu mục hoặc không rõ để "". Phiếu giao hàng
luôn để requester_name=""; không lấy người giao/nhận/ký/duyệt hay tự đoán từ bộ phận.
pr_reference_id: chỉ chép số PR/phiếu yêu cầu được ghi rõ trên chứng từ.
Trên PR dùng số PR. Trên phiếu giao chỉ điền nếu có nhãn tham chiếu PR rõ;
không lấy số hóa đơn/số phiếu giao/số PO độc lập làm số PR; thiếu thì để "".
'''


def pr_reference(document):
    value = document.get('pr_reference_id', '').strip()
    if not value:
        own_reference = document.get('reference_id', '').strip()
        if document.get('document_type') == 'pr' or re.match(r'(?i)^PR\s*[-:#/]?\s*\d', own_reference):
            value = own_reference
    value = re.sub(r'(?i)^PR\s*[-:#/]?\s*', '', value).strip()
    return str(int(value)) if value.isdigit() else normalize_name(value)


def pr_reference_conflict(pr_documents, delivery_documents):
    references = {pr_reference(document) for document in pr_documents + delivery_documents}
    references.discard('')
    return len(references) > 1


def row_pr_context(analysis, number):
    if not analysis:
        return '', 'KHÔNG CÓ PR'
    if analysis.get('reference_mismatch'):
        return '', 'PR KHÁC THAM CHIẾU — CẦN XÁC NHẬN'
    row = next((r for r in analysis.get('rows', []) if r.get('delivery_index') == number), None)
    if not row or not row.get('pr_index') or row.get('status') not in {'match', 'mismatch'}:
        return '', 'CHƯA GHÉP CHẮC CHẮN PR — CẦN XÁC NHẬN'
    names = row.get('requester_names', [analysis.get('pr_document', {}).get('requester_name', '')])
    if not names or any(not isinstance(name, str) or not normalize_name(name) for name in names):
        return '', 'PR THIẾU NGƯỜI ĐỀ NGHỊ — CẦN XÁC NHẬN'
    distinct = {normalize_name(name) for name in names}
    if len(distinct) != 1:
        return '', 'PR NHIỀU NGƯỜI ĐỀ NGHỊ — CẦN XÁC NHẬN'
    # Product/quantity warnings remain in their own comparison columns. They do
    # not erase the requester of the PR to which this delivery row was linked.
    return names[0].strip(), VERIFIED_PR


def requester_warehouse(record, directory, rules):
    routing = rules.get('requester_warehouses', {}) if rules else {}
    if record.get('pr_status') != VERIFIED_PR:
        reason = record.get('pr_status') or 'Chưa có căn cứ PR'
        return '', '', '', CONFIRM_PREFIX + ' ' + reason + '; cần bạn xác nhận kho.'
    key = normalize_name(record.get('requester_name', ''))
    matches = {code for name, code in routing.items() if normalize_name(name) == key}
    if len(matches) != 1:
        return '', '', '', CONFIRM_PREFIX + ' Người đề nghị PR chưa có quy tắc; cần bạn xác nhận kho.'
    code = next(iter(matches))
    if code not in directory:
        return '', '', '', CONFIRM_PREFIX + f' Kho {code} không có trong DanhMucKho; cần xác nhận.'
    return code, *directory[code], 'Phân kho theo người đề nghị trên PR đã ghép.'
