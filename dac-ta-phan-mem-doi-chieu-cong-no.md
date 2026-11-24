# Đặc tả nghiệp vụ phần mềm đối chiếu công nợ

## 1. Mục tiêu sản phẩm

Phần mềm giúp kế toán đối chiếu công nợ phải thu và phải trả nhanh, dễ hiểu, giảm việc kiểm tra thủ công trên Excel và tạo bằng chứng đối chiếu rõ ràng với khách hàng hoặc nhà cung cấp.

Mục tiêu chính:

- Nhập dữ liệu từ nhiều nguồn: phần mềm kế toán, Excel, CSV, sao kê ngân hàng hoặc bảng xác nhận của đối tác.
- Tự động ghép các khoản phát sinh giữa hai bên.
- Hiển thị ngay số đã khớp, chưa khớp, lệch số tiền, lệch ngày và chứng từ còn thiếu.
- Cho phép kế toán xử lý ngoại lệ nhanh trên cùng một màn hình.
- Lưu lại lịch sử, người xử lý và bằng chứng cho từng lần đối chiếu.
- Xuất biên bản đối chiếu công nợ và danh sách cần xử lý.

## 2. Nguyên tắc thiết kế để đối chiếu nhanh

Giao diện và quy trình cần tuân thủ năm nguyên tắc:

1. **Tóm tắt trước, chi tiết sau:** người dùng nhìn thấy kết quả tổng quan trước khi mở từng chứng từ.
2. **Một màn hình xử lý:** hạn chế chuyển qua nhiều trang; danh sách đối chiếu, chi tiết và thao tác xử lý nằm trong cùng một luồng.
3. **Màu sắc có ý nghĩa rõ ràng:** xanh là đã khớp, vàng là cần xem xét, đỏ là có chênh lệch hoặc thiếu dữ liệu, xám là chưa đủ điều kiện đối chiếu.
4. **Ưu tiên ngoại lệ:** mặc định đưa các khoản chưa khớp hoặc có giá trị lớn lên đầu.
5. **Mọi thao tác đều có thể giải thích:** hệ thống phải cho biết vì sao hai dòng được ghép hoặc vì sao không được ghép.

## 3. Đối tượng sử dụng và phân quyền

### 3.1. Nhân viên kế toán

Được nhập dữ liệu, chạy đối chiếu, xem chi tiết, đề xuất ghép thủ công, ghi chú và xuất báo cáo trong phạm vi đơn vị được phân công.

### 3.2. Kế toán trưởng

Có toàn quyền xem dữ liệu, duyệt các ghép thủ công, xác nhận kỳ đối chiếu, khóa biên bản và mở lại kỳ khi cần.

### 3.3. Người phê duyệt hoặc quản lý

Được xem dashboard, xem các khoản chênh lệch lớn, phê duyệt biên bản và theo dõi tiến độ xử lý; không được sửa dữ liệu gốc.

### 3.4. Quản trị hệ thống

Quản lý người dùng, danh mục, quy tắc đối chiếu, kết nối dữ liệu, nhật ký hệ thống và cấu hình ngưỡng cảnh báo.

## 4. Phạm vi phiên bản đầu tiên

Phiên bản đầu tiên nên tập trung vào đối chiếu công nợ theo đối tác và kỳ kế toán, gồm:

- Công nợ phải thu khách hàng.
- Công nợ phải trả nhà cung cấp.
- Đối chiếu số dư đầu kỳ, phát sinh trong kỳ, thanh toán và số dư cuối kỳ.
- Đối chiếu theo số hóa đơn, số chứng từ, mã đối tác, ngày chứng từ và số tiền.
- Ghép tự động, ghép bán tự động và ghép thủ công.
- Theo dõi khoản chưa xử lý và xuất biên bản.

Các chức năng như dự báo dòng tiền, thu hồi nợ tự động, OCR hóa đơn nâng cao hoặc tích hợp ngân hàng sâu có thể để ở giai đoạn sau.

## 5. Quy trình nghiệp vụ chuẩn

### Bước 1: Tạo kỳ đối chiếu

Người dùng chọn loại đối chiếu, đơn vị, đối tác hoặc nhóm đối tác, kỳ kế toán và loại tiền tệ. Hệ thống kiểm tra xem kỳ này đã có phiên đối chiếu hay chưa.

Một phiên đối chiếu gồm: mã phiên, kỳ đối chiếu, bên đối chiếu, người phụ trách, trạng thái, thời gian bắt đầu, thời gian hoàn tất và ngày chốt dữ liệu.

### Bước 2: Nạp dữ liệu hai bên

Người dùng nạp dữ liệu bên nội bộ và dữ liệu bên đối tác. Hệ thống phải hỗ trợ kéo-thả tệp, mẫu Excel chuẩn và lưu lại tên tệp, thời điểm nạp, người nạp, số dòng và trạng thái kiểm tra.

Trước khi nạp chính thức, hệ thống hiển thị bản xem trước 20 dòng, tự nhận diện cột và yêu cầu người dùng xác nhận ánh xạ trường dữ liệu.

### Bước 3: Kiểm tra dữ liệu

Hệ thống kiểm tra các lỗi: thiếu mã đối tác, thiếu ngày, số tiền không hợp lệ, trùng số chứng từ, sai định dạng tiền tệ, dòng tổng cộng bị nhập nhầm như một giao dịch và chứng từ nằm ngoài kỳ.

Các dòng lỗi không bị xóa. Chúng được đưa vào nhóm “Cần làm sạch dữ liệu” để người dùng sửa hoặc loại trừ có lý do.

### Bước 4: Chạy đối chiếu tự động

Hệ thống chạy các quy tắc theo thứ tự từ chắc chắn đến linh hoạt. Sau mỗi lần chạy, hệ thống ghi lại phiên bản bộ quy tắc và thời điểm chạy.

Kết quả được phân nhóm: khớp hoàn toàn, khớp có sai số trong ngưỡng, một-nhiều, nhiều-một, chưa khớp, chênh lệch số tiền, chênh lệch ngày và thiếu chứng từ đối ứng.

### Bước 5: Xử lý ngoại lệ

Người dùng lọc các trường hợp cần xử lý, xem hai bên cạnh nhau, chọn hành động đề xuất và ghi chú. Các thao tác gồm ghép thủ công, tách ghép, xác nhận chênh lệch, đánh dấu chờ đối tác, loại trừ có lý do hoặc chuyển người xử lý.

### Bước 6: Gửi xác nhận và khóa kỳ

Sau khi xử lý, người dùng xuất biên bản đối chiếu hoặc gửi yêu cầu xác nhận cho đối tác. Khi được duyệt, phiên đối chiếu chuyển sang “Đã xác nhận” và dữ liệu bị khóa chỉnh sửa; mọi thay đổi sau đó phải tạo phiên điều chỉnh.

## 6. Màn hình chính đề xuất

### 6.1. Dashboard đối chiếu

Dashboard cần trả lời ngay bốn câu hỏi: còn bao nhiêu khoản chưa khớp, tổng giá trị chênh lệch là bao nhiêu, khoản nào có rủi ro cao nhất và tiến độ của từng nhân viên hoặc từng đối tác.

Các thẻ tổng quan nên gồm: tổng số dòng, đã khớp, cần xử lý, chênh lệch ròng, tỷ lệ hoàn thành và số ngày còn lại đến hạn.

Biểu đồ nên đơn giản: tỷ lệ trạng thái theo màu và danh sách “Top 10 khoản chênh lệch lớn nhất”. Không nên dùng quá nhiều biểu đồ trang trí.

### 6.2. Màn hình danh sách đối chiếu

Bảng chính gồm các cột: trạng thái, đối tác, số chứng từ nội bộ, số chứng từ đối tác, ngày, số tiền nội bộ, số tiền đối tác, chênh lệch, lý do và người xử lý.

Bộ lọc cố định phía trên gồm: kỳ, đối tác, trạng thái, mức chênh lệch, loại tiền, người xử lý và khoảng giá trị. Có nút “Chỉ xem việc của tôi” và “Chỉ xem khoản quá hạn”.

Mặc định sắp xếp theo mức độ ưu tiên: chênh lệch lớn, quá hạn, thiếu chứng từ, sau đó đến chênh lệch nhỏ.

### 6.3. Màn hình xử lý một khoản

Khi chọn một dòng, mở bảng chi tiết bên phải thay vì chuyển trang. Bên trái là dữ liệu nội bộ, bên phải là dữ liệu đối tác, giữa hai bên là kết quả so sánh từng trường.

Mỗi trường hiển thị một trong ba trạng thái: trùng, khác nhưng nằm trong ngưỡng, hoặc khác cần xử lý. Ngay dưới đó là lý do hệ thống đề xuất ghép.

Các nút hành động chính phải nổi bật: “Xác nhận khớp”, “Ghép thủ công”, “Tách ghép”, “Đánh dấu chờ đối tác”, “Xác nhận chênh lệch” và “Chuyển xử lý”.

## 7. Quy tắc đối chiếu tự động

### 7.1. Khớp chắc chắn

Được xem là khớp chắc chắn khi mã đối tác, số hóa đơn hoặc số chứng từ, loại tiền và số tiền đều trùng; ngày chứng từ có thể lệch trong khoảng cấu hình nếu nghiệp vụ cho phép.

### 7.2. Khớp theo khóa kết hợp

Nếu thiếu số hóa đơn, hệ thống dùng tổ hợp mã đối tác + ngày chứng từ + số tiền + mã tham chiếu. Nếu có nhiều kết quả, hệ thống không tự xác nhận mà đưa vào nhóm “Cần xem xét”.

### 7.3. Khớp một-nhiều và nhiều-một

Hệ thống cho phép một khoản thanh toán khớp với nhiều hóa đơn hoặc nhiều khoản thanh toán khớp với một hóa đơn. Tổng số tiền sau khi ghép phải bằng nhau trong ngưỡng sai số.

### 7.4. Sai số cho phép

Người quản trị cấu hình ngưỡng sai số theo số tiền tuyệt đối, tỷ lệ phần trăm, loại tiền và loại giao dịch. Không được mặc định tự xác nhận các khoản sai số vượt ngưỡng.

### 7.5. Chênh lệch ngày

Ngày được chia thành ba mức: trùng ngày, lệch trong ngưỡng cho phép và lệch cần xem xét. Hệ thống phải hiển thị rõ số ngày lệch và không làm mất ngày gốc của mỗi bên.

### 7.6. Trùng dữ liệu

Nếu một dòng có khả năng ghép với nhiều dòng, hệ thống đánh dấu “Nghi trùng” và yêu cầu người dùng chọn. Không tự động ghép khi mức độ tin cậy thấp.

## 8. Mô hình trạng thái

Một dòng đối chiếu có thể đi qua các trạng thái: Mới nhập, Lỗi dữ liệu, Chưa khớp, Đề xuất khớp, Đã khớp tự động, Đã khớp thủ công, Chênh lệch cần xử lý, Chờ đối tác, Đã xác nhận, Đã loại trừ và Đã khóa.

Mỗi lần chuyển trạng thái phải lưu người thực hiện, thời điểm, trạng thái cũ, trạng thái mới, lý do và ghi chú. Không cho phép xóa lịch sử.

## 9. Dữ liệu cốt lõi

### 9.1. Đối tác

Mã đối tác, tên đối tác, mã số thuế, loại đối tác, đơn vị tiền tệ, người liên hệ, email nhận xác nhận, điều khoản thanh toán và trạng thái hoạt động.

### 9.2. Giao dịch công nợ

Mã dòng, mã đối tác, loại giao dịch, số chứng từ, số hóa đơn, ngày chứng từ, ngày đến hạn, số tiền trước thuế, thuế, tổng tiền, đã thanh toán, còn lại, loại tiền, tài khoản kế toán, mô tả và nguồn dữ liệu.

### 9.3. Kết quả ghép

Mã ghép, các dòng bên nội bộ, các dòng bên đối tác, phương pháp ghép, điểm tin cậy, chênh lệch tiền, chênh lệch ngày, trạng thái, người duyệt và lý do xử lý.

### 9.4. Phiên đối chiếu

Mã phiên, kỳ, đơn vị, danh sách đối tác, ngày chốt, tổng số dòng, số dòng đã xử lý, tổng chênh lệch, người phụ trách, người phê duyệt, trạng thái và tệp biên bản.

## 10. Điểm tin cậy và ưu tiên xử lý

Mỗi đề xuất ghép có điểm tin cậy từ 0 đến 100. Số chứng từ trùng có trọng số cao nhất; mã đối tác, số tiền, ngày và mã tham chiếu có trọng số tiếp theo.

Điểm từ 95 trở lên có thể tự động xác nhận nếu không có cảnh báo trùng. Điểm từ 75 đến 94 đưa vào danh sách đề xuất. Điểm dưới 75 không đề xuất ghép tự động mà chỉ hiển thị các dòng có khả năng liên quan.

Mức ưu tiên xử lý nên dựa trên chênh lệch tuyệt đối, tuổi công nợ, ngày quá hạn, rủi ro đối tác và số lần bị điều chỉnh.

## 11. Báo cáo và đầu ra

Hệ thống cần có các đầu ra sau:

- Biên bản đối chiếu công nợ theo đối tác và kỳ.
- Danh sách hóa đơn hoặc chứng từ chưa khớp.
- Danh sách chênh lệch theo nguyên nhân.
- Báo cáo tuổi công nợ sau đối chiếu.
- Nhật ký thay đổi và lịch sử phê duyệt.
- Bảng tổng hợp tiến độ theo nhân viên, đối tác và đơn vị.

Biên bản cần có số dư đầu kỳ, phát sinh tăng, phát sinh giảm, số đã thanh toán, số dư cuối kỳ của hai bên, số chênh lệch, giải trình, người lập, người kiểm tra và phần xác nhận của đối tác.

## 12. Tích hợp và nhập liệu

Giai đoạn đầu nên hỗ trợ Excel và CSV bằng mẫu chuẩn. Sau đó tích hợp API hoặc cơ sở dữ liệu với phần mềm kế toán đang sử dụng. Tất cả nguồn dữ liệu phải có mã nguồn và mã lần nạp để truy ngược.

Khi nhập lại cùng một tệp, hệ thống phải phát hiện khả năng trùng và cho phép người dùng chọn: bỏ qua, cập nhật, tạo phiên bản mới hoặc nhập bổ sung.

## 13. Kiểm soát và bảo mật

Phân quyền theo vai trò, đơn vị, tài khoản kế toán và phạm vi đối tác. Dữ liệu nhạy cảm phải được giới hạn theo nguyên tắc cần biết.

Cần có nhật ký đăng nhập, nạp dữ liệu, sửa dữ liệu, ghép thủ công, tách ghép, xác nhận, xuất báo cáo và thay đổi cấu hình ngưỡng.

Các kỳ đã khóa không được sửa trực tiếp. Mọi điều chỉnh phải tạo dấu vết liên kết với phiên gốc.

## 14. Chỉ số đánh giá hiệu quả

Sau khi triển khai, theo dõi các chỉ số: thời gian trung bình để hoàn tất một kỳ đối chiếu, tỷ lệ ghép tự động, tỷ lệ ghép đúng, số dòng xử lý mỗi giờ, số khoản tồn quá hạn, giá trị chênh lệch chưa giải quyết và số lần phải mở lại kỳ.

Mục tiêu tham khảo cho phiên bản đầu tiên là giảm ít nhất 50% thời gian đối chiếu thủ công, tự động xử lý phần lớn giao dịch có khóa rõ ràng và giúp người dùng tìm được khoản chênh lệch lớn trong dưới một phút.

## 15. Lộ trình triển khai đề xuất

### Giai đoạn 1: Nền tảng đối chiếu

Xây dựng danh mục đối tác, nhập Excel/CSV, tạo phiên đối chiếu, đối chiếu hai chiều, bộ lọc, ghép tự động cơ bản, ghép thủ công, ghi chú và xuất Excel.

### Giai đoạn 2: Kiểm soát và phê duyệt

Bổ sung phân quyền, phê duyệt, khóa kỳ, biên bản PDF, nhật ký đầy đủ, thông báo việc tồn và dashboard quản trị.

### Giai đoạn 3: Tự động hóa nâng cao

Bổ sung kết nối trực tiếp phần mềm kế toán, nhận diện chứng từ, đề xuất ghép thông minh, email xác nhận đối tác và phân tích nguyên nhân chênh lệch.

## 16. Tiêu chí nghiệm thu quan trọng

Một phiên bản đạt yêu cầu khi người dùng có thể tạo một kỳ đối chiếu, nạp hai tệp, xem lỗi dữ liệu, chạy đối chiếu, lọc riêng các khoản chưa khớp, xử lý một khoản một-nhiều, ghi chú và xuất biên bản mà không cần rời khỏi luồng chính.

Hệ thống phải bảo toàn dữ liệu gốc, giải thích được mọi kết quả ghép, không tự động xác nhận trường hợp mơ hồ, lưu đầy đủ lịch sử thao tác và cho phép đối chiếu lại cùng một kỳ mà không tạo dữ liệu trùng.

## 17. Đề xuất trải nghiệm người dùng ngắn gọn

Luồng được khuyến nghị là: **Chọn kỳ → Nạp dữ liệu → Kiểm tra lỗi → Chạy đối chiếu → Xử lý ngoại lệ → Gửi xác nhận → Khóa kỳ**.

Trên giao diện, chỉ nên có một nút hành động chính ở mỗi bước. Các thông tin nâng cao như điểm tin cậy, khóa ghép và nhật ký được đặt trong vùng chi tiết mở rộng để người mới không bị quá tải, nhưng kế toán trưởng vẫn có đủ thông tin kiểm tra.
