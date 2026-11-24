# API nhận diện NCC cho trang Công nợ

- GET /api/debt/suppliers?month=2026-11 trả danh mục và nhóm phiếu theo mã NCC hoặc code=null. Mỗi phiếu có ngày báo cáo, tên sheet để mở bản REC, version, tên OCR, căn cứ, gợi ý, tiền tạm tính và số dòng thiếu.
- POST /api/debt/supplier dùng X-REC-Token từ GET /api/ocr/status. Gửi id, version, code và reason để xác nhận riêng phiếu.
- Để lưu bí danh, thêm alias chọn từ rawNames. Lần đầu trả saved=false, affected và previewToken. Gửi lại nội dung cùng previewToken sau khi người dùng xem các phiếu bị ảnh hưởng. Nếu dữ liệu đổi thì hiển thị bản xem trước mới.
- Các giá trị provisional là chuỗi số. Kỳ hiện dựa trên ngày báo cáo, thể hiện ở periodBasis. Dùng day và sheet để mở phiếu gốc.
