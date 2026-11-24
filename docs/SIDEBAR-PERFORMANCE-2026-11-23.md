# Điều hướng mới và tốc độ mở phiếu

Đã thay menu xổ khu vực bằng thanh điều hướng trái có thể thu gọn/mở rộng. Top bar giữ tên khu vực, tab nghiệp vụ và ngày. Mặc định thanh trái chỉ hiện biểu tượng để dành chỗ kiểm ảnh; nút bên trái top bar mở đủ nhãn. Chín khu vực và logic khóa điều hướng khi đang lưu được giữ.

Đo luồng đọc ngày 23/11 với 29 phiếu trên cùng máy: cách cũ 4,852 giây; dùng chung danh sách ảnh đã xác minh 0,921 giây. Kết quả trong `output/sidebar-performance.json`. Đây là thời gian xử lý backend, không phải thời gian toàn bộ khởi động Qt.

Nguyên nhân: mỗi review token gọi lại day_images, đọc và hash cả kho ảnh ngày đó. Giờ server truyền danh sách ảnh đã đọc vào review_token; thao tác xác nhận/lưu vẫn tự kiểm tra nguồn hiện tại.

Các lần mở PR trước đây phân tích lại workbook. get_rows nay dùng cache tối đa 4 phiên bản workbook, vẫn kiểm tra digest tệp mỗi lần và trả deepcopy để thao tác sửa không ảnh hưởng cache. Không bỏ kiểm tra ảnh, sổ hoặc phiên bản. PR vẫn có chi phí xác minh ảnh/sổ; bài đo khoảng 0,8–1,1 giây, không phải tải qua mạng.

Kiểm tra desktop: đủ 9 mục; mở rộng 208px; không tràn ngang cửa sổ; hiển thị 1/29 phiếu. Ảnh tại `output/sidebar-ui.png`. Build thành công. Kiểm thử cache bảo đảm dữ liệu trả về độc lập và từ chối workbook đã thay đổi.

Modern Web Guidance đã thử tìm responsive sidebar navigation, nhưng registry bị chặn EACCES; không có guide tải được để áp dụng. Không thêm thư viện mới.
