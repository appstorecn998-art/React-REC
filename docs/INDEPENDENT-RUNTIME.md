# Bản web độc lập

Mã nguồn dùng lại được sao chép một lần từ REC vào `runtime/`. Từ đây mọi thay đổi mới chỉ áp dụng tại dự án này. Không tự đồng bộ ngược về REC thật.

- `local_runtime.py`: đường dẫn chung cho server và worker.
- `runtime/`: bản sao mã Python và mẫu phiếu; có sửa hàng đợi OCR riêng.
- `local-profile/`: bản sao danh mục, quy tắc, mẫu và khóa Gemini; dữ liệu riêng, không đưa vào Git. Không sao chép khóa Google Sheets.
- `local-data/receipts/`: bản sao báo cáo và ảnh để web dùng độc lập; các liên kết kho ảnh đã trỏ sang bản sao.
- `runtime-origin.json`: hash mã nguồn ban đầu dùng để truy vết, không phải cơ chế cập nhật.

Chạy `python -X utf8 server.py` từ thư mục này để mở cổng8768. Trang thử OCR chạy `python -X utf8 ocr_test_server.py` ở cổng8769.

OCR mới và thao tác lưu từ web chỉ ghi vào dữ liệu riêng. Báo cáo web sẽ không tự cập nhật vào REC thật. Những báo cáo tạo thêm trong REC sau khi sao chép cũng không tự xuất hiện ở web.

Khóa Gemini được sao chép để tiếp tục dùng cấu hình hiện có: phí API vẫn thuộc cùng tài khoản Google. Cách ly phần mềm không tạo tài khoản hay hạn mức API riêng.

Hàng đợi: thử lại lỗi tạm thời tối đa3lần, tiếp tục ảnh khác sau lỗi; giữ trang quanh lỗ hổng chưa chắc ranh giới. Đọc lại cùng nhóm tận dụng cache và bỏ qua phiếu đã lưu. Giao diện giới hạn30ảnh vẫn chưa sửa theo yêu cầu làm logic trước.
