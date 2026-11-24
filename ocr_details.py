"""Original pixels in overlapping strips; no perspective warp or invented content."""
import base64,io
from PIL import Image

INSTRUCTION='''Các ảnh CHI TIẾT là các dải chồng lấn của CÙNG chứng từ mục tiêu,
không phải trang mới. Chỉ xuất mỗi dòng một lần theo STT ảnh toàn trang cuối cùng.
Xác định cột số lượng IN và cột THỰC NHẬN riêng biệt trước khi đọc.
Chép số viết tay trong cột thực nhận, kể cả phần thập phân; không mặc định nhận đủ.
Chỉ coi là gạch lượng khi nét nằm trong ô lượng hoặc ô thực nhận của đúng dòng.
Nét trong tên, hạn dùng, dấu ngoặc, chữ ký, con dấu không phải dấu gạch lượng.
Không kéo số viết tay sang dòng kế bên. Không tự sửa lượng để khớp thành tiền in.
Phiếu không có cột giá: để unit_price và line_amount trống, không suy từ ghi chú.
Không đọc chắc thì dùng unclear, received_quantity rỗng thay vì đoán.
'''

def content(raw):
    from ocr_events import emit
    image=Image.open(io.BytesIO(raw)).convert('RGB');w,h=image.size
    emit('details','Đang tạo 3 dải chi tiết từ ảnh gốc.',width=w,height=h,overlap='30–42% và 60–72%',perspective_warp=False)
    result=[{'type':'text','text':INSTRUCTION}]
    for n,(top,bottom) in enumerate([(0,.42),(.30,.72),(.60,1)],1):
        crop=image.crop((0,round(h*top),w,round(h*bottom)))
        stream=io.BytesIO();crop.save(stream,'JPEG',quality=97)
        emit('detail_ready',f'Đã tạo dải chi tiết {n}/3.',top_pixel=round(h*top),bottom_pixel=round(h*bottom),width=crop.width,height=crop.height,jpeg_bytes=len(stream.getvalue()),jpeg_quality=97)
        result.extend([{'type':'text','text':f'Chi tiết {n}, vị trí dọc {top:.0%}–{bottom:.0%} của cùng trang:'},
                       {'type':'image','mime_type':'image/jpeg','data':base64.b64encode(stream.getvalue()).decode()}])
    result.append({'type':'text','text':'Tiếp theo là ảnh TOÀN TRANG mục tiêu. Chỉ xuất danh sách một lần.'})
    return result

def install(aw):
    # Workers may read images concurrently; evidence must stay local to each call.
    from contextvars import ContextVar
    details=ContextVar('ocr_details',default=())
    examples=aw.receipt_example_content;request=aw.request_batch_document
    aw.receipt_example_content=lambda:examples()+list(details.get())
    def read(api_key,model,image_bytes,catalog_groups,timeout):
        token=details.set(content(image_bytes))
        try:return request(api_key,model,image_bytes,catalog_groups,timeout)
        finally:details.reset(token)
    aw.request_batch_document=read
