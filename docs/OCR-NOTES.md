# OCR React → Python REC — 21/11/2026

## Đã nối hoạt động

Vào Nhận phiếu, chọn từ1đến30ảnh (20MB/ảnh,80MB/nhóm), chọn ngày nhận (mặc định ngày Việt Nam hiện tại), bấm Đọc ảnh bằng Gemini. Ảnh được giữ tại `.ocr-jobs/<uploadId>/sources`, nhập qua `receiving_service.import_images`, rồi gọi `ocr_child.py` → launcher `rec_launcher.main()` → `receiving_app.worker()`. Không viết lại phân loại PR/giao/khác, nhóm trang, đối chiếu danh mục, số lượng, kho hoặc luồng ghi Excel.

Đích thật là `REC_Software/Data/Phieu giao hang hang thang`, hồ sơ cấu hình là `%LOCALAPPDATA%/REC` (hoặc REC_DATA_DIR). Chỉ ảnh được chọn được truyền qua `REC_SELECTED_IMAGE_HASHES`. Giữ quy tắc ảnh đã lưu thì không đọc lại/sửa kết quả đã được người dùng chỉnh. Không có khóa API trong React, file build hoặc API status. Nhóm ảnh mới sẽ gửi Gemini sau khi người dùng bấm đọc; thư mục chọn ngày đang xem không tự quyết định ngày nhận của nhóm mới.

Job chạy riêng, một tác vụ mỗi server; có log và trạng thái thật, không phần trăm đoán. Người dùng có thể sang Kiểm phiếu để xem dữ liệu cũ trong khi worker chạy. Phiếu lỗi giữ kết quả đã lưu; đọc lại nhóm ảnh sẽ tiếp tục theo cache của worker cũ. Job metadata cuối cùng ở `.ocr-jobs/<jobId>/status.json`. Nút mở kết quả chỉ có khi có báo cáo với dòng dữ liệu; PR/ảnh khác không tạo phiếu giao giả.

## Tối ưu mới có thể tắt

`ocr_quality.py` chỉ cài trong tiến trình OCR do web gọi, không sửa module cài đặt của REC desktop. Giữ màu và EXIF, không grayscale/tăng tương phản mặc định. Cạnh dài tối đa3200px, JPEG94; không phóng lớn ảnh nhỏ. Tăng chi tiết có thể tăng thời gian/chi phí so với2400px/JPEG92 cũ.

Nếu OpenCV nhận đúng một tứ giác giấy đủ bốn góc và có khoảng cách với biên ảnh, đạt tiêu chí kích thước/độ sáng, thì nắn phối cảnh với mép an toàn. Góc bị cắt, nhiều tờ, vùng không chắc hoặc thiếu OpenCV: giữ nguyên khung. Đây là cách bảo thủ; không bảo đảm tự nắn mọi ảnh (IMG4979 trong thử thật được giữ khung gốc). Ảnh gốc không thay đổi. Chưa có thuật toán sửa giấy cong và chưa bật giảm nhiễu/chuyển trắng đen.

Fingerprint OCR có phiên bản riêng để không nhầm cache cũ với cách chuẩn bị mới. Ảnh đã được ghi vào báo cáo vẫn giữ nguyên theo worker cũ. Cảnh báo STT lặp/đứt, thiếu giá/lượng và dấu thực nhận chưa rõ được lấy ở biên extract, gồm cả OCR cache hit; không tự thêm, gộp hoặc đổi số liệu. Các cảnh báo này không chứng minh OCR sai: STT ngắt có thể đúng trên ảnh và cần người xem.

## Bằng chứng đã kiểm

-11test của bridge/upload/quality/HTTP qua: giới hạn file/têntrùng/path, token và Origin, upload chỉ stage chưa ghi dữ liệu kế toán, đúng ảnh chọn, nhánhthànhcông/lỗi, giữnguyênnguồn, crop synthetic cómargin và fallback, chất lượngmàu3200px, audit không mutate và cachehit vẫn cảnhbáo;15ngày đọc khớp snapshot gốc.
-95test `test_autowatcher.py` và4test `test_receiving_inbox.py` của nguồn REC cũ qua.
- Đã chạy thử bộ test toàn App nhưng có lỗi UI/export hiện hữu trong những module không được chỉnh; bộ test dừng giữa chừng ở nhóm PR. Không tuyên bố toàn suite qua. Log `legacy-tests.log` giữ bằng chứng; không sửa các lỗi không thuộc tích hợp này.
- Build React qua. Có cảnh báo kích thước bundle và directive `use client` của dependency; chưa tối ưu bundle ở lượt này.
- Một lần Gemini thực tế với IMG4979, kết quả riêng ở `output/ocr-live-4979`. Khoảng84giây toànluồng; OCRkhoảng40giây, ghép mãkhoảng34giây, model hiệnhành `gemini-3.5-flash-lite`. Đọc3dòng;4trường tên hàng/thựcnhận/đơn giá/mã từngdòng khớp snapshot REC cũ, kểcả dòng thựcnhận0. SHA256 ảnh và báo cáo gốc không đổi.

File `output/ocr-live-4979/validation.json` lưu kết quả kiểm. Kết quả khớp snapshot hiện tại không phải benchmark độc lập hay bằng chứng tăng độ đúng từ80% lên một tỷ lệ mới. Chưa có bộ phiếu đã kiểm tay làm ground truth và chưa thử đủ NCC/loại chữ viết để chốt độ chính xác mới.

## Giới hạn hiện tại

Ghi metadata và gán PR bằng giao diện React vẫn là nháp/chưa nối; luồng OCR mới ghi báo cáo bằng chính worker Python gốc. Chuẩn bị ảnh nâng cao chỉ có trong worker web, không đổi OCR desktop. Bản preview có HTTP local server, chưa là REC.exe mới. Đóng trình duyệt không dừng worker; backend cần tiếp tục chạy đến khi tác vụ lưu xong. Chưa có nút hủy giữa chừng để tránh gián đoạn lưu workbook.

Nguồn phải chụp đủ mép/chữ rõ. Thêm xử lý ảnh không khôi phục được chữ đã nhòe hoặc bị che. Không tự lưu quy tắc NCC từ đề xuất AI.
