import React,{useEffect,useRef,useState} from 'react';
import OcrProgress from './OcrProgress';
import {Button} from '@astryxdesign/core/Button';
import {DateInput} from '@astryxdesign/core/DateInput';
import {Upload,FileImage,ScanLine,ChevronDown,AlertCircle,CheckCircle2} from 'lucide-react';

const types=/\.(jpe?g|png|webp|heic|heif)$/i;
const busy=s=>['importing','running'].includes(s);
function localToday(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
const readFile=file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Không đọc được ảnh '+file.name));reader.readAsDataURL(file)});

export default function OcrPanel({onComplete,initialDay}){
 const [files,setFiles]=useState([]),[day,setDay]=useState(()=>initialDay||localToday()),[enhanced,setEnhanced]=useState(true),[state,setState]=useState(null),[phase,setPhase]=useState(''),[error,setError]=useState(''),[upload,setUpload]=useState(null);
 const input=useRef(null),handled=useRef(null),callback=useRef(onComplete);callback.current=onComplete;
 useEffect(()=>{let alive=true,timer;async function poll(){try{const r=await fetch('/api/ocr/status',{cache:'no-store'});if(!r.ok)throw new Error();const next=await r.json();if(!alive)return;setState(next);if(next.job?.status==='complete'&&handled.current!==next.job.id){handled.current=next.job.id;/* Stay on intake so results and warnings remain visible. */}}catch{if(alive)setError('Không kết nối được worker OCR. Tải lại trang để thử.')}finally{if(alive)timer=setTimeout(poll,1000)}}poll();return ()=>{alive=false;clearTimeout(timer)}},[]);
 const running=busy(state?.job?.status)||Boolean(phase);
 function choose(list){const next=[...list];setError('');if(!next.length)return;if(next.length>200||next.some(f=>!types.test(f.name)||f.size>20*1024*1024)||next.reduce((s,f)=>s+f.size,0)>80*1024*1024){setError('Chọn tối đa 200 ảnh JPG/PNG/WebP/HEIC. Mỗi ảnh ≤20 MB, cả nhóm ≤80 MB.');return}if(new Set(next.map(f=>f.name.toLowerCase())).size!==next.length){setError('Nhóm ảnh có tên trùng nhau. Đổi tên trước khi thêm.');return}setFiles(next);setUpload(null)}
 async function post(url,payload){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-REC-Token':state.token},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw new Error(data.error||'Tác vụ chưa hoàn tất.');return data}
 async function start(){if(!files.length||!state?.ready)return;setError('');try{setPhase('uploading');let staged=upload;if(!staged||staged.day!==day){const data=[];for(const file of files)data.push({name:file.name,content:await readFile(file)});staged=await post('/api/ocr/upload',{day,files:data});setUpload(staged)}setPhase('starting');const job=await post('/api/ocr/start',{uploadId:staged.uploadId,enhanced});setState(s=>({...s,job}));}catch(e){setError(e.message)}finally{setPhase('')}}
 const job=phase?null:state?.job;
 return <section className="ocr-panel" aria-labelledby="ocr-heading"><header className="ocr-intro"><div><h2 id="ocr-heading">Thêm ảnh & đọc phiếu</h2><p>Đọc ảnh gốc, kiểm tra số viết tay và lưu vào ngày nhận đã chọn trong bản web riêng.</p></div><div className="ocr-date"><DateInput label="Ngày nhận cho nhóm ảnh mới" size="sm" value={day} presentation="popover" format={iso=>iso.split('-').reverse().join('/')} onChange={v=>{if(v){setDay(v);setUpload(null)}}} isDisabled={running}/></div></header>
 <input ref={input} type="file" multiple accept=".jpg,.jpeg,.png,.webp,.heic,.heif" hidden onChange={e=>choose(e.target.files)}/>
 <div className="ocr-drop" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!running)choose(e.dataTransfer.files)}}><Upload size={28}/><h3>Kéo cả nhóm ảnh vào đây</h3><p>Tối đa 200 ảnh · Tổng tối đa 80 MB · Giữ ảnh gốc · Không đọc lại phiếu đã lưu</p><Button label={files.length?'Chọn nhóm ảnh khác':'Chọn ảnh trên máy'} size="sm" onClick={()=>input.current.click()} isDisabled={running}/></div>
 {files.length>0&&<div className="ocr-files">{files.map((f,i)=><div key={f.name}><FileImage size={16}/><span>{f.name}</span><small>{(f.size/1024/1024).toFixed(1)} MB</small></div>)}</div>}
 <div className="ocr-options"><label><input type="checkbox" checked={enhanced} disabled={running} onChange={e=>setEnhanced(e.target.checked)}/><span>Ưu tiên chữ nhỏ & số viết tay<small>Đọc ảnh gốc màu cùng 3 vùng chi tiết, tối đa 3200px; tốn thêm token. Ảnh đã căn chỉ dùng để xem.</small></span></label><Button label={running?'Đang xử lý…':`Đọc ${files.length||''} ảnh bằng Gemini`} icon={<ScanLine size={15}/>} size="sm" variant="primary" isDisabled={running||!files.length||!state?.ready} onClick={start}/></div>
 <p className="ocr-disclosure">Bấm đọc sẽ gửi các ảnh đã chọn tới Gemini theo khóa đã cấu hình trong REC, có thể tính phí API. Không gửi khóa vào trình duyệt.</p>
 {state&&!state.ready&&<p className="ocr-error">Bản web riêng chưa đủ khóa Gemini hoặc danh mục. Kiểm tra cấu hình của bản web.</p>}
 {error&&<p role="alert" className="ocr-error"><AlertCircle size={15}/>{error}</p>}
 {<OcrProgress job={job} phase={phase} day={day} count={files.length} onOpen={day=>callback.current(day)}/>}
 </section>
}
