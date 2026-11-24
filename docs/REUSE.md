# REC React: thay giao diện, giữ nghiệp vụ hiện tại

Yêu cầu người dùng: REC cũ đã hết lag khi chuyển phiếu, bấm bảng và đối chiếu PR. Không viết lại hoặc thay thế những tối ưu này chỉ vì chuyển UI.

## Đã tái sử dụng trực tiếp

`server.py` import `receiving_service.snapshot`, `day_images`, `invoice_pages` từ REC_Software/App. Không sao chép thuật toán hoặc thay đổi báo cáo. Cầu nối chỉ đọc, cache snapshot theo mtime/size và chỉ cấp ảnh được ghép đúng bằng logic REC. UI lấy một snapshot, đổi phiếu và chọn hàng không đọc lại Excel hoặc gọi OCR. React giữ viewer ổn định qua memo và key phiếu; sửa metadata/chọn hàng không tháo lắp viewer. Chuẩn bị ảnh lân cận bằng cache trình duyệt; không xử lý lại ảnh gốc.

## Các điểm phải nối lại khi triển khai nghiệp vụ đầy đủ

| REC cũ | Cách giữ lại |
|---|---|
| `receiving_qt.ReceivingWindow.select_receipt/select_sheet` | Giữ ID worksheet và kiểm tra rời PR/bản nháp; tách điều phối khỏi widget nếu cần, không tái tạo quy tắc trong React |
| `rec_receipt_page.prefetch_next`, `receiving_qt.ImagePreview.prefetch/cache` | Giữ chuẩn bị ảnh nền, cache bounded, tránh giải mã ảnh trên luồng chính. Qt pixmap không chuyển nguyên sang DOM; dùng logic định danh/cache và ảnh đã xử lý của Python |
| `receiving_pr.compare` | Gọi hàm Python hiện tại khi đã chọn đúng PR. Không viết lại ghép tên, quy đổi hoặc multi-lot trong JavaScript |
| `receiving_qt._review_tab_changed`, `_leave_pr` | Chỉ tính khi PR thay đổi, giữ lưu nháp và kiểm tra rời màn |
| `rec_debt_review` model role cache / atomic mutations | Tiếp tục dùng cache và các hàm ghi gốc; React chỉ gửi payload nghiệp vụ sau kiểm tra |

Thực tế Qt model/view, QTimer, QPixmap là UI-specific. Cần bộ nối thay phần widget mà vẫn giữ hành vi/thuật toán; không thể nhúng trực tiếp QWidget trong React. Chưa tuyên bố luồng PR và ghi Excel đã tích hợp trong bản mẫu này.

## Phạm vi hiện tại

React + Astryx v0.7.16 thật. Component dùng: Button, IconButton, TextInput, TimeInput và Theme Neutral. Bảng HTML ngữ nghĩa bốn cột vì đây là giao diện đọc/so sánh gọn, chưa cần engine data grid mới.

Nguồn so sánh ngày21/11/2026: Astryx Templates https://astryx.atmeta.com/templates ; shadcn Blocks https://ui.shadcn.com/blocks ; Radix Themes https://www.radix-ui.com/themes/playground . Astryx là component cài trực tiếp; shadcn và Radix chỉ tham khảo bố cục/mật độ, không cài chồng ba bộ UI.

Neutral và Warm đổi màu/không gian xem trên cùng dữ liệu để so sánh. Minh họa nhỏ trong hộp nguồn được vẽ bằng CSS để gợi nhắc bố cục, không phải screenshot của website.

Chỉ đọc 3 phiếu thực tế IMG5050/5058/5060 ngày17/11, không suy tổng cả ngày. Không có bảng kê NCC thì không đánh dấu khớp tổng. Giờ chụp không thay giờ nhận; giờ nhận trống khi nguồn chưa có. Metadata và đánh dấu kiểm chỉ là nháp trong phiên React.

Chạy Python `python server.py`, rồi `npm run dev`; mở http://127.0.0.1:8767 . `npm run build` đóng gói giao diện, có thể mở bản build qua Python tại http://127.0.0.1:8768 . Không dùng API key. Không cài vào REC cũ, không thay đổi code nguồn hoặc workbook.


## Hiệu năng đã giữ lại trong bản React

Bản React không đọc workbook khi chuyển phiếu hoặc chọn dòng. `server.py` gọi `receiving_service.snapshot` một lần và cache theo mtime/size; ảnh dùng `invoice_pages` của REC và browser cache. Viewer React được memo theo `doc.file`; đổi metadata hoặc chọn dòng không remount ảnh. Snapshot chỉ đọc 3 sheet thiết kế, không gọi OCR/PR.

Cần nối thêm trước khi dùng thật: endpoint Python cho `select_sheet`/cache ảnh lân cận, các luồng `pr_dirty`/`_leave_pr`, `receiving_pr.compare`, `rec_debt_review.mutate_receipt` và các hàm atomic save. Không đưa logic ghép PR hay ghi Excel vào client.

## Nguồn nhận hàng chính và bộ chọn ngày —21/11/2026

Người dùng xác nhận nguồn chính qua ảnh Settings: C:/Users/Fenn/Desktop/REC_Software/Data/Phieu giao hang hang thang. Đã bỏ nguồn REC_CongNo. Bộ chọn Ngày xem khám phá15live TongHopPhieuNgay từ03đến20/11; không dùng file xuất cuối hoặc workbook trong backup. Không đọc báo cáo cũ thiếu cấu trúc snapshot chỉ vì cùng đuôi Excel. Mặc định chọn ngày mới nhất đã có báo cáo, không giả định ngày hôm nay có dữ liệu.

Python gọi snapshot/day_images/invoice_pages nguyên bản theo report.parent. Ngày20:10phiếu70dòng;ngày19:20phiếu126dòng tại thời điểm kiểm. Chuyển phiếu không gọi API dữ liệu mới; cache mỗi ngày theo mtime/size, tối đa4ngày; Tải lại cưỡng chế đọc lại ảnh và dữ liệu. Yêu cầu chọn ngày mới hủy fetch cũ, chỉ kết quả mới nhất được áp dụng. Nháp NCC/giờ/bộphận và trạng thái kiểm tên dùng khóa ngày::worksheet, không dùng tên sheet đơn thuần.

Tọa độ demo IMG5050 làm từ nguồn công nợ trước đây không tự áp vào nguồn chính. Chức năng thử nghiệm tọa độ/căn ảnh trên nguồn chính chưa áp hàng loạt. Tất cả dữ liệu đọcchỉ, không gọi Gemini/Codex, không sửa workbook. Test all15days khớp trực tiếp snapshot, ảnh identity allowlist hợp lệ, SHA256 các báo cáo trước/sau không đổi, cache/tênngàyinvalid và identity qua ngày pass. Browser đã thử19->20, đổiphiếu, kiểm15option/ngày20có10phiếu và ảnh tảiđúng.

##21/11/2026: OCR từ React

Đã nối chọn nhóm ảnh/ngàynhận với Jobs -> receiving_service.import_images -> rec_launcher -> receiving_app.worker, truyền đúng selectedhashes, giữ incremental/saveguard/PRclassification gốc. Thêm tùychọn chuẩn bị3200px màu+safequad trong childprocess, fingerprint riêng và qualityaudit gồm cachehit. Không đổi code OCR cài trong App. Xem OCR-NOTES.md về kiểmtra và giới hạn; một ảnh thửthật IMG4979 ghi riêng workspace, ảnh/báocáogốc giữnguyên.
