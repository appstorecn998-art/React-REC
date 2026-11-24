# Ảnh căn chỉnh và vị trí mặt hàng

Ảnh gốc được giữ nguyên. Bản JPEG đã căn lưu tại `output/straightened`, tối đa 3200 px. Khóa cache dựa trên SHA-256 nội dung ảnh, phiên bản xử lý và góc xoay đã xác nhận. Di chuyển thư mục không làm mất hiệu lực nếu mang theo thư mục cache. Nội dung ảnh, góc xoay hoặc thuật toán thay đổi thì tạo bản khác.

OCR nâng cao và giao diện dùng cùng byte ảnh JPEG đã lưu. OCR thường có thể thu nhỏ đồng đều về 2400 px, không cắt hoặc xoay thêm. Tọa độ dùng tỉ lệ 0–1 của bản ảnh chung. Mỗi kết quả OCR được gắn khóa của đúng bản ảnh đã gửi; tọa độ cũ không được gắn sang ảnh xoay mới.

Lần OCR mới có thêm trường tùy chọn `row_box` cho từng mặt hàng: `top,left,bottom,right`, thang 0–1000 trên toàn trang mục tiêu. Trường này đi kèm cuộc gọi OCR sẵn có, không có cuộc gọi trả phí riêng để lấy tọa độ. Nếu không chắc, trường để rỗng. Không tự chạy lại OCR đã có, nhưng fingerprint mới khiến một lần người dùng chủ động đọc lại có thể không dùng cache OCR cũ.

Các vùng ảnh được kiểm tra giới hạn, đối chiếu tên hàng với hàng đã lưu, loại vùng chồng lấn và trường hợp tên trùng hoặc gần giống tại nhiều vị trí. Chưa xác định được thì hiển thị thông báo, không chia đều trang hoặc suy từ thứ tự hàng để vẽ khung. Tọa độ do mô hình trả về vẫn có thể sai; cần người dùng kiểm tra ảnh, chúng không phải bằng chứng kiểm toán hay kết luận sai lệch kế toán.

Với phiếu cũ thiếu tọa độ, hệ thống thử Tesseract cục bộ nếu đã cài và có dữ liệu ngôn ngữ `eng`. Không tự tải mô hình hay gọi dịch vụ mạng. Trên Windows, tìm trong PATH, `Program Files/Tesseract-OCR/tesseract.exe` hoặc thư mục người dùng tương ứng. Kết quả với chữ Việt, tên viết tắt và ảnh kém có thể không đủ; các dòng đó giữ trạng thái chưa định vị. Không có Tesseract thì vẫn đọc phiếu, ảnh và dùng tọa độ OCR đã lưu bình thường.

API `/api/receipts` chỉ đăng ký đường dẫn ảnh, không căn tất cả ảnh trước khi trả bảng. `/api/receipt/locations` xử lý riêng phiếu đang mở; kiểm tra phiên bản workbook và nội dung/hướng ảnh trước khi trả tọa độ. Tọa độ và neo tên lưu trong `output/straightened/row-locations`. Chỉ sau khi đúng ảnh chuẩn đã tải xong, frontend mới vẽ khung, chuyển trang và cuộn tới vùng chọn. Trên ảnh gốc khung được ẩn vì hệ tọa độ khác.

Khởi động lại bằng `Mo REC.cmd` để server Python nạp các thay đổi; launcher chờ OCR đang chạy hoàn tất thay vì dừng ngang. Địa chỉ duy nhất là `http://127.0.0.1:8771/`.

Kiểm thử cục bộ bao phủ cache khi đổi vị trí, nội dung cùng kích thước/thời gian, góc xoay, byte ảnh OCR, vùng ngoài ảnh, tên trùng, cạnh tranh mơ hồ và API từ chối tọa độ sai phiên bản. Chưa đánh giá độ chính xác `row_box` bằng OCR cloud thực tế trong lần triển khai này; không phát sinh chi phí OCR khi kiểm thử.
