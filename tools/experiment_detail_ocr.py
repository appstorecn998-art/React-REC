"""Isolated original + overlapping detail experiment on already authorized day20 images."""
import base64,io,json,time
from PIL import Image
from benchmark_ocr import OUT,aw,server

TARGET=OUT/'detail-v2-experiment'
from ocr_details import INSTRUCTION

def main():
    TARGET.mkdir(exist_ok=True)
    _,groups=aw.load_catalog_data(server.ocr_jobs.profile/'DanhMuc.xlsm')
    key=server.ocr_jobs._secrets()[0];original_examples=aw.receipt_example_content
    for name in ['IMG_4964.JPG.webp','IMG_4965.JPG.webp','IMG_4980.JPG.webp','IMG_4981.JPG.webp','IMG_4983.JPG.webp']:
        target=TARGET/(name+'.json')
        if target.exists():continue
        raw=(OUT/(name+'.original.jpg')).read_bytes();image=Image.open(io.BytesIO(raw));w,h=image.size
        details=[{'type':'text','text':INSTRUCTION}]
        for n,(top,bottom) in enumerate([(0,.42),(.30,.72),(.60,1)],1):
            crop=image.crop((0,round(h*top),w,round(h*bottom)))
            stream=io.BytesIO();crop.save(stream,'JPEG',quality=97)
            details.extend([{'type':'text','text':f'Chi tiết {n}, vị trí dọc {top:.0%}–{bottom:.0%} của cùng trang:'},{'type':'image','mime_type':'image/jpeg','data':base64.b64encode(stream.getvalue()).decode()}])
        aw.receipt_example_content=lambda:original_examples()+details+[{'type':'text','text':'Tiếp theo là ảnh TOÀN TRANG mục tiêu. Chỉ xuất danh sách một lần.'}]
        started=time.monotonic()
        try:
            document=aw.request_batch_document(key,aw.MODEL,raw,groups,150)
            aw.atomic_cache_json(target,{'document':document,'seconds':round(time.monotonic()-started,2),'strategy':'original + 3 overlapping details, same model'})
            print(name,len(document['items']),'ok',flush=True)
        except Exception as exc:print(name,type(exc).__name__,flush=True);return 2
    aw.receipt_example_content=original_examples
    return 0

if __name__=='__main__':raise SystemExit(main())
