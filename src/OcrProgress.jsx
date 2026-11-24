import React from 'react';
import {Check,Clock3,AlertCircle,ChevronDown,Image as ImageIcon} from 'lucide-react';
import {motion,useReducedMotion} from 'motion/react';
import {Button} from '@astryxdesign/core/Button';

const scanTransition={
 duration:2.5,
 ease:[0.175,0.885,0.32,1],
 times:[0,0.6,0.6,1],
 repeat:Infinity,
 repeatType:'mirror',
 repeatDelay:0.2,
};
const scanMask='inset(0 0% 0 0)';
const openScanMask='inset(0 100% 0 0)';

function AnalyzingImage(){
 const reduceMotion=useReducedMotion();
 return <span className="ocr-analyzing-image" aria-hidden="true">
  <svg viewBox="0 0 24 24" fill="none">
   <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" strokeWidth="1.5"/>
   <path fill="currentColor" d="M5 5h3v1H5zm10 0h2v2h-2zM9 8h1v2H9zm9 1h2v1h-2zM5 10h2v1H5zm8 0h1v2h-1zm-4 3h2v1H9zm7 0h2v2h-2zM5 15h2v2H5zm7 0h1v2h-1zm6 3h2v1h-2zM7 18h3v1H7zm7 0h2v1h-2z"/>
  </svg>
  <motion.span className="ocr-analyzing-mask" initial={false}
   animate={{clipPath:reduceMotion?scanMask:[scanMask,openScanMask,openScanMask,scanMask]}}
   transition={reduceMotion?{duration:0}:scanTransition}>
   <ImageIcon strokeWidth={1.5}/>
  </motion.span>
  {!reduceMotion&&<motion.span className="ocr-analyzing-line"
   animate={{left:['100%','0%','0%','100%']}} transition={scanTransition}/>}
 </span>;
}

const seconds=value=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(value||0);
export default function OcrProgress({job,phase,day,count,onOpen}){
 const events=job?.events||[],running=Boolean(phase)||['importing','running'].includes(job?.status);
 const analyzing=!phase&&job?.status==='running'&&job?.stage==='read';
 const preview = phase ? null : job?.preview;
 const definitions=[['Nhận ảnh',['import'],['import_done']],['Chuẩn bị ảnh',['prepare'],['prepare_done']],['Đọc nội dung',['read'],['match','saved','complete']],['Đối chiếu & lưu phiếu',['match','saved'],['complete']]];
 let failed=false;
 const steps=definitions.map(([title,start,end])=>{const finish=events.find(e=>end.includes(e.stage));const begun=events.find(e=>start.includes(e.stage));let status=finish?'done':begun?'active':'pending';if(job?.status==='error'&&!finish&&!failed){status='error';failed=true}return{title,status,finish,begun}});
 const title=!job&&!phase?'Sẵn sàng đọc phiếu':phase==='uploading'?'Đang nhận ảnh từ máy của bạn':phase==='starting'?'Đang khởi động đọc phiếu':job?.status==='complete'?'Đã xử lý xong nhóm ảnh':job?.status==='error'?'Nhóm ảnh chưa hoàn tất':job?.stage==='match'?'Đang đối chiếu mặt hàng':job?.stage==='save'?'Đang lưu các phiếu đã đủ dữ liệu':job?.stage==='prepare'?'Đang chuẩn bị ảnh':'Đang đọc nội dung phiếu';
 return <section className={'ocr-workflow '+(job?.status||'')} aria-label="Tiến độ đọc phiếu">
  <header><div><span className="ocr-kicker">TIẾN ĐỘ XỬ LÝ</span><h3 className="ocr-workflow-title" role="status">{analyzing&&<AnalyzingImage/>}{title}</h3><p>Ngày {job?.day||day} · {job?.count||count} ảnh đã chọn · {job?.status==='error'||job?.status==='complete'?'Tổng thời gian':'Đã chạy'} {seconds(job?.elapsed)} giây</p></div>{running&&<span className="ocr-eta"><Clock3 size={14}/>{job?.remaining>0?`Ước tính còn ${Math.ceil(job.remaining)} giây`:job?.remaining===0?'Đang lâu hơn dự kiến':'Đang ước tính thời gian'}{job?.estimateSamples>0&&<small>Dựa trên {job.estimateSamples} nhóm đã hoàn tất</small>}</span>}</header>
  {running&&<progress aria-label="Đang xử lý nhóm phiếu"/>}
  <ol className="ocr-steps" aria-label="Các bước đọc phiếu">{steps.map((step,index)=><React.Fragment key={step.title}><li className={step.status} aria-current={step.status==='active'?'step':undefined}><span className="ocr-step-icon">{step.status==='done'?<Check size={14}/>:step.status==='error'?<AlertCircle size={14}/>:index+1}</span><div><b>{step.title}</b><small>{step.finish?`Giây ${seconds(step.finish.seconds)}: đã hoàn tất`:step.status==='error'?'Có lỗi cần kiểm tra':step.status==='active'?'Đang thực hiện':'Chờ bước trước'}</small></div></li>{index<steps.length-1&&<li className={'ocr-step-connector '+(step.status==='done'?'done':'')} aria-hidden="true"/>}</React.Fragment>)}</ol>
  <div className="ocr-counters"><span><b>{job?.imagesRead||0}</b> ảnh đã đọc nội dung</span><span><b>{job?.savedCount||0}</b> phiếu vừa lưu</span>{job?.imagesFailed>0&&<span className="ocr-counter-warning"><b>{job.imagesFailed}</b> ảnh chưa đọc được</span>}</div>
  <section className="ocr-preview-progress" aria-label="Cắt mép và căn thẳng">
    <strong>Cắt mép &amp; căn thẳng ảnh xem trước</strong>
    {preview ? <>
      <p role="status">{preview.processed}/{preview.total} ảnh đã xử lý
        {preview.status === 'running' && preview.file ? ` · Đang xử lý ${preview.file}` : ''}
        {preview.status === 'complete' ? ' · Hoàn tất' : ''}
        {preview.status === 'interrupted' ? ' · Đã gián đoạn' : ''}
      </p>
      <progress aria-label="Số ảnh xem trước đã xử lý" value={preview.processed} max={preview.total}/>
      {preview.processed > 0 && <p>
        Đã cắt mép {preview.cropped} · Chỉ căn thẳng {preview.straightened} · Giữ ảnh gốc {preview.original}
        {preview.failed > 0 && ` · Lỗi ${preview.failed}, dùng ảnh gốc`}
      </p>}
    </> : <p>{job?.status === 'complete' || job?.status === 'error'
      ? 'Lượt này chưa có tiến độ ảnh xem trước.'
      : 'Chờ xác minh nhóm ảnh. Sau đó, ảnh xem trước được xử lý song song với đọc phiếu.'}</p>}
  </section>
  {running&&job?.currentImage&&<p className="ocr-current-image"><strong>Ảnh đang xử lý:</strong> {job.currentImage}. Khi đang chờ Gemini, chưa có kết quả từng dòng.</p>}
  <ol className="ocr-readable-events">{events.filter(e=>!['detail','import','prepare','read','match'].includes(e.stage)).slice(-12).map((event,index)=><li key={index} className={event.stage}><time>{seconds(event.seconds)} giây</time><span>{event.message}</span></li>)}</ol>
  {job?.status==='error'&&<p role="alert" className="ocr-error"><AlertCircle size={16}/>{job.message}</p>}
  {job?.hasReport&&['complete','error'].includes(job.status)&&<Button label={job.status==='error'?'Xem các phiếu đã lưu':'Mở kết quả ngày này'} size="sm" onClick={()=>onOpen(job.day)}/>}
  {job?.warnings?.length>0&&<div className="ocr-quality-warnings"><strong>Những chỗ cần kiểm lại</strong>{job.warnings.map((w,i)=><div key={i}><b>{w.reference||'Phiếu đã đọc'}</b><ul>{w.warnings.map((s,k)=><li key={k}>{s}</li>)}</ul></div>)}</div>}
  {job?.poWarnings?.length>0&&<div className="ocr-quality-warnings">
   <strong>PO cần đối chiếu danh mục</strong>
   <ul>{job.poWarnings.map((warning,index)=><li key={index}>{warning}</li>)}</ul>
  </div>}
  {job?.logs?.length>0&&<details><summary>Thông tin kỹ thuật khi cần kiểm tra lỗi <ChevronDown size={12}/></summary><pre>{job.logs.join('\n')}</pre></details>}
 </section>;
}
