# React REC

- `src/` và `public/` chứa giao diện React và tài nguyên giao diện.
- `server.py` chạy bản web đã dựng trong `dist/`. Logic phiếu và báo cáo nằm trong `runtime/`.
- `local-data/` chứa ảnh và báo cáo. `local-profile/` chứa danh mục và cấu hình cục bộ.
- `docs/` chứa tài liệu. `tests/` chứa kiểm thử. `tools/` chứa các tiện ích và thử nghiệm.
- `output/` chứa ảnh xem trước và kết quả xử lý được tạo khi chạy.

Mở `Mo REC.cmd` hoặc `Mo REC Desktop.vbs` trong thư mục này để dùng [React REC](http://127.0.0.1:8771/). Cả hai launcher đều mở giao diện bằng trình duyệt hệ thống qua server cục bộ. Địa chỉ cố định là `http://127.0.0.1:8771/`, không tự chuyển cổng. Trình mở dùng lại server đúng thư mục nếu đã chạy; chỉ đóng server REC cũ trên 8768/8771 sau khi xác minh đó là Python REC và không có OCR đang xử lý. Tiến trình không xác định sẽ không bị dừng. Cửa sổ server Python cần được giữ mở khi sử dụng.

Chạy thủ công: `python -B -X utf8 server.py` từ thư mục này, cũng dùng cổng 8771. Đọc ảnh mới cần cấu hình khóa Gemini cục bộ.

Khi lấy mã nguồn từ GitHub, chạy `npm ci` và `npm run build` để tạo lại `dist/`. Cấu hình thư mục dữ liệu REC bằng biến môi trường `REC_DATA_ROOT` hoặc tệp cục bộ `data-location.json` có khóa `path`. Nhập mã Google Sheets trong **Quản trị** và đặt khóa dịch vụ `google-sheets-key.json` trong thư mục hồ sơ cục bộ nếu dùng đồng bộ.
