"""Quy tắc thực nhận do người dùng xác nhận ngày 02/11/2026."""
import base64
import hashlib
from pathlib import Path

RECEIPT_MARK_SCHEMA = {"type": "string", "enum": [
    "written", "cross_with_number", "cross_without_number", "check", "unmarked",
    "unclear", "not_applicable",
]}

RECEIPT_RULES_PROMPT = """
Quy tắc THỰC NHẬN đã được người dùng xác nhận, chỉ áp dụng cho phiếu giao:
- quantity giữ nguyên số lượng giao in trên dòng, kể cả khi con số đó bị gạch.
- X hoặc một nét gạch chéo tại dòng/cột lượng có số sửa ghi bên cạnh:
  receipt_mark="cross_with_number", received_quantity là SỐ SỬA bên cạnh.
  Không lấy lại con số in đã bị gạch, số dòng, đơn giá hay số của dòng khác.
- X/gạch chéo không có số sửa bên cạnh: receipt_mark="cross_without_number";
  received_quantity="0". Phân biệt số không có với số có nhưng mờ không đọc được.
  Trước khi lấy số viết tay, xác định chính xác hai đường kẻ giới hạn dòng hàng
  theo phối cảnh nghiêng của bảng. Số ngay bên dưới đường kẻ thuộc DÒNG KẾ TIẾP,
  không phải số bên cạnh X. Nếu ô Thực Nhận của một dòng chỉ có X, còn ô ngay
  dưới có 15, dòng có X nhận 0 và dòng bên dưới nhận 15; tuyệt đối không kéo 15 lên.
- Dấu tích như chữ v, cạnh phải dài hơn: receipt_mark="check"; thực nhận bằng quantity.
- Dòng không đánh dấu/không bị gạch: receipt_mark="unmarked"; thực nhận bằng quantity.
- Nếu cột Thực Nhận có số ghi rõ riêng thì receipt_mark="written" và chép số đó
  vào received_quantity (giữ cả số 0); không thay bằng số lượng giao.
- Nếu dấu X có số sửa nhưng số đó mờ, không rõ đó là X hay tích, hoặc ghi chú
  không xác định thuộc dòng nào: receipt_mark="unclear", received_quantity="";
  không tự coi là 0 hay nhận đủ. Chỉ xét dấu thuộc dòng hàng, không xét chữ ký,
  con dấu, đường kẻ bảng hoặc dấu gạch trong tên/quy cách.
Phiếu giao KHÔNG CÓ cột Thực Nhận cũng áp dụng quy tắc trên: dòng không bị
gạch có receipt_mark="unmarked", thực nhận bằng quantity. Không dùng
not_applicable chỉ vì không có cột Thực Nhận.
CHỈ với PR/other: receipt_mark="not_applicable", received_quantity="".
"""

RECEIPT_EXAMPLES = [
    ("cross-number", "Mẫu đã xác nhận: số lượng in 5 bị X, ghi V 5 bên cạnh cùng dòng: cross_with_number, thực nhận 5."),
    ("cross-zero", "Mẫu đã xác nhận: dòng trên số lượng 10 có một gạch chéo, không có số sửa: cross_without_number, thực nhận 0. Số 15 nằm ở dòng DƯỚI, không thuộc gạch ở dòng trên."),
    ("check", "Mẫu đã xác nhận: dấu tích có cạnh phải dài là check, nhận đủ số lượng in bên cạnh."),
    ("unmarked", "Mẫu đã xác nhận: phiếu không có cột nhận và không đánh dấu: unmarked, dòng 24 nhận 24, dòng 2 nhận 2."),
]


def receipt_example_content():
    content = [{"type": "text", "text": "Các ảnh cắt sau CHỈ LÀ MẪU DẤU do người dùng xác nhận. Không thêm dòng hàng từ các mẫu vào kết quả."}]
    for name, label in RECEIPT_EXAMPLES:
        data = (Path(__file__).parent / "receipt_examples" / f"{name}.png").read_bytes()
        content.extend([{"type": "text", "text": label}, {"type": "image", "mime_type": "image/png",
                       "data": base64.b64encode(data).decode("ascii")}])
    content.append({"type": "text", "text": "HẾT MẪU. Chỉ đọc chứng từ mục tiêu được gửi sau đây; áp dụng cách hiểu dấu tương tự, không sao chép số từ mẫu."})
    return content


def receipt_rules_fingerprint():
    digest = hashlib.sha256((RECEIPT_RULES_PROMPT + repr(RECEIPT_EXAMPLES)).encode("utf-8"))
    for name, _ in RECEIPT_EXAMPLES:
        digest.update((Path(__file__).parent / "receipt_examples" / f"{name}.png").read_bytes())
    return digest.digest()


def apply_receipt_rules(item, parse_quantity):
    """AI nhận diện dấu; code quyết định số lượng từ dấu và số đã đọc."""
    mark = item.get("receipt_mark")
    if mark is None:  # Dữ liệu cũ không đủ bằng chứng để suy lại dấu trên ảnh.
        return item
    if mark not in RECEIPT_MARK_SCHEMA["enum"]:
        raise ValueError("Loại dấu xác nhận thực nhận không hợp lệ.")
    received = parse_quantity(item.get("received_quantity"))
    if "receipt_number_location" in item:
        number_location = item["receipt_number_location"]
        misplaced_cross = (
            mark in {"cross_with_number", "cross_without_number"}
            and item.get("receipt_mark_location") != "quantity"
        )
        unsupported_number = (
            mark in {"written", "cross_with_number"} and number_location != "same_row"
        )
        conflicting_number = (
            mark in {"cross_without_number", "check", "unmarked"}
            and number_location not in {"none", "other_row"}
        )
        if misplaced_cross or unsupported_number or conflicting_number:
            mark = item["receipt_mark"] = "unclear"
    note = ""
    if mark == "cross_without_number":
        received = parse_quantity("0")
        note = "Thực nhận 0: dấu gạch chéo không có số sửa bên cạnh."
    elif mark in {"check", "unmarked"}:
        received = parse_quantity(item.get("quantity"))
        note = "Thực nhận bằng số lượng giao: " + ("dấu tích." if mark == "check" else "dòng không đánh dấu.")
    elif mark == "cross_with_number":
        note = "Thực nhận theo số sửa bên cạnh dấu gạch chéo."
    elif mark in {"unclear", "not_applicable"}:
        received = None
    uncertain = received is None
    item["received_quantity"] = "" if uncertain else str(received)
    item["receipt_needs_review"] = uncertain
    item["receipt_note"] = ("Chưa đọc rõ thực nhận; kiểm tra dấu/ghi tay trên phiếu."
                            if uncertain else note)
    return item
