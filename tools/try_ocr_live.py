"""One explicitly scoped Gemini smoke test into a separate workspace output folder."""
import base64,hashlib,json,time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from ocr_jobs import Jobs

if __name__=='__main__':
    destination=ROOT/'output'/'ocr-live-4979'
    if destination.exists():raise SystemExit('Test output already exists; refusing another paid run.')
    day='2026-11-20';source=server.load(day)
    receipt=next(d for d in source['receipts'] if d['file']=='IMG_4979')
    image=server.allowed_images[receipt['pages'][0].rsplit('/',1)[-1]]
    before=hashlib.sha256(image.read_bytes()).hexdigest()
    report=server.available_days()[day];report_before=hashlib.sha256(report.read_bytes()).hexdigest()
    jobs=Jobs(destination,ROOT/'.ocr-jobs-live')
    upload=jobs.stage({'day':day,'files':[{'name':'IMG_4979.webp','content':base64.b64encode(image.read_bytes()).decode()}]})
    jobs.start({'uploadId':upload['uploadId'],'enhanced':True});last=None
    while True:
        job=jobs.public()['job']
        if job['message']!=last:print(job['message'],flush=True);last=job['message']
        if job['status'] in ('complete','error'):break
        time.sleep(1)
    result={'job':job,'source_rows':receipt['rows'],'original_image_unchanged':hashlib.sha256(image.read_bytes()).hexdigest()==before,'original_report_unchanged':hashlib.sha256(report.read_bytes()).hexdigest()==report_before}
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='source_rows'},ensure_ascii=False),flush=True)
    raise SystemExit(0 if job['status']=='complete' else 1)
