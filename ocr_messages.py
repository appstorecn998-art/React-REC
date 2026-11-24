"""Plain Vietnamese errors; exception classes belong only in technical logs."""
def reading_error(name,kind='',message='',status=None):
    text=str(message).lower()
    if status in (401,403):reason='Chưa có quyền sử dụng dịch vụ đọc ảnh. Kiểm tra khóa Gemini và quyền của tài khoản.'
    elif status==429:reason='Dịch vụ đọc ảnh đang giới hạn lượt sử dụng. Chờ một lúc rồi thử lại.'
    elif status in (500,502,503,504):reason='Dịch vụ đọc ảnh đang gặp sự cố. Chương trình sẽ thử lại nếu còn lượt.'
    elif 'timeout' in kind.lower() or 'timed out' in text:reason='Dịch vụ đọc ảnh phản hồi quá lâu, chưa nhận được kết quả.'
    elif 'connection' in kind.lower() or 'network' in text:reason='Không kết nối được dịch vụ đọc ảnh. Kiểm tra mạng rồi thử lại.'
    elif 'không đọc được dòng hàng' in text:reason='Chưa đọc rõ các dòng hàng trong ảnh. Kiểm tra ảnh có đủ bảng hàng, chữ rõ và không bị che.'
    elif any(x in text for x in ('loại phiếu','loại chứng từ')):reason='Chưa xác định được đây là loại phiếu gì. Kiểm tra ảnh có đủ tiêu đề và nội dung phiếu.'
    elif any(x in text for x in ('sai kiểu','metadata','json','cấu trúc','không hợp lệ')):reason='Kết quả dịch vụ trả về chưa đầy đủ hoặc chưa đúng dạng, nên chưa thể lưu. Hãy thử đọc lại ảnh.'
    elif 'thay đổi' in text:reason='Ảnh thay đổi trong lúc đang đọc. Chờ chép ảnh xong rồi thử lại.'
    elif 'permission' in kind.lower():reason='Chưa mở hoặc lưu được tệp. Kiểm tra quyền thư mục và đóng báo cáo đang mở.'
    else:reason='Chưa đọc được nội dung phiếu. Chưa có đủ thông tin để xác định nguyên nhân; hãy thử đọc lại và kiểm tra ảnh.'
    return f'Ảnh {name}: {reason}'


def invoice_error(kind, message, status):
    if kind == 'PermissionError' or any(word in message for word in ('Excel/WPS', 'WPS/Excel')):
        return 'Chưa lưu được phiếu. Đóng báo cáo trong Excel/WPS rồi thử lại.'
    if status in {401, 403, 429, 500, 502, 503, 504} or 'Timeout' in kind:
        return reading_error('', kind, message, status).removeprefix('Ảnh : ')
    if isinstance(message, str) and message.startswith(('Ảnh ', 'Số dòng ', 'Phiếu ', 'File này ')):
        return message
    return 'Chưa đối chiếu hoặc lưu được phiếu. Các phiếu đã lưu được giữ để tiếp tục khi thử lại.'
