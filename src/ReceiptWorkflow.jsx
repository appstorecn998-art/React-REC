import React,{useEffect,useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import ConfirmationButton, {useConfirmation} from './ConfirmationButton';

async function request(url,payload){
 let options={cache:'no-store'};
 if(payload){const auth=await fetch('/api/ocr/status',options).then(r=>r.json());options={...options,method:'POST',headers:{'Content-Type':'application/json','X-REC-Token':auth.token},body:JSON.stringify(payload)}}
 const response=await fetch(url,options),data=await response.json();
 if(!response.ok)throw Error(data.error||'Chưa hoàn tất thao tác. Thử lại sau.');
 return data;
}

export function ReviewReceipt({data,doc,onSaved,onClose,Modal}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [confirmed,showSuccess]=useConfirmation();
 async function save(){if(busy)return;setBusy(true);setError('');try{await request('/api/receipt/review',{day:data.dayId,version:data.version,sheet:doc.file,sourceToken:doc.reviewToken,expectedReviewed:Boolean(doc.reviewed),reviewed:!doc.reviewed});await showSuccess();await onSaved();onClose()}catch(e){setError(e.message)}finally{setBusy(false)}}
 return <Modal title={doc.reviewed?'Bỏ xác nhận kiểm tra':'Xác nhận đã kiểm tra phiếu'} onClose={()=>{if(!busy)onClose()}} className="workflow-dialog"><div className="workflow-body"><p><strong>{doc.supplierNickname||doc.supplier}</strong> · {data.day}</p><p>{doc.reviewed?'Phiếu sẽ cần kiểm tra và xác nhận lại trước khi xuất chính thức.':'Xác nhận đã đối chiếu tên hàng, mã, đơn vị, giá, ngày nhận và số thực nhận với ảnh gốc.'}</p><p className="workflow-note">Sau khi kiểm phiếu, vào Sổ nhận hàng để Xác nhận ghi sổ. Google Sheets chỉ nhận dữ liệu khi bạn xem trước và bấm Xác nhận cập nhật trong mục Google Sheets.</p>{error&&<p role="alert" className="error-banner">{error}</p>}<div className="receipt-actions"><Button label="Để sau" variant="ghost" onClick={onClose} isDisabled={busy}/><ConfirmationButton label={doc.reviewed?'Bỏ xác nhận':'Xác nhận đã kiểm tra'} successLabel={doc.reviewed?'Đã bỏ xác nhận':'Đã kiểm tra'} onClick={save} busy={busy} confirmed={confirmed}/></div></div></Modal>
}

export function ExportReceipts({data,onClose,onBusyChange,Modal}){
 const [preview,setPreview]=useState(null),[error,setError]=useState(''),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[result,setResult]=useState(null);
 const [confirmed,showSuccess]=useConfirmation();
 useEffect(()=>{let alive=true;request('/api/export/preview?day='+data.dayId).then(v=>{if(alive)setPreview(v)}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}},[data.dayId]);
 async function save(){
  setBusy(true);onBusyChange?.(true);setError('');
  try{const exported=await request('/api/export',{day:data.dayId,version:preview.version,previewToken:preview.token,provisionalConsent:consent});await showSuccess();setResult(exported)}
  catch(e){setError(e.message)}
  finally{setBusy(false);onBusyChange?.(false)}
 }
 return <Modal title={'Xuất hồ sơ ngày '+data.day} onClose={()=>{if(!busy)onClose()}} className="workflow-dialog"><div className="workflow-body">
 {!preview&&!error&&<p role="status">Đang kiểm tra điều kiện xuất…</p>}
 {preview&&!result&&<><p><strong>{preview.reviewedCount} / {preview.receiptCount} phiếu đã kiểm tra</strong></p><div className="workflow-outputs">{['Phiếu giao hàng Excel và ảnh gốc','Báo cáo công việc hằng ngày','ZIP phiếu giao hàng kèm ảnh'].map((v,i)=><div key={v}><span>{i+1}</span>{v}</div>)}</div><p className="workflow-note">Lưu trong local-data của React REC. Giữ nguyên file đã được sửa riêng; không tự ghi đè bản của REC cũ.</p>{preview.pending.length>0&&<section aria-label="Phiếu chưa hoàn tất"><h3>Cần hoàn tất trước khi xuất chính thức</h3><ul>{preview.pending.map(v=><li key={v.sheet}><strong>{v.sheet}</strong> · {v.reason}</li>)}</ul></section>}{preview.notes.length>0&&<p>{preview.notes.join(' · ')}</p>}{preview.blockers.map(v=><p role="alert" key={v}>{v}</p>)}{preview.provisional&&<label className="workflow-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>Tôi xác nhận xuất BẢN TẠM; còn phiếu chưa hoàn tất.</label>}<p className="workflow-note">Xuất file không tự xác nhận kiểm tra, ghi sổ PR hoặc đồng bộ Sheets.</p></>}
 {result&&<section aria-label="Kết quả xuất hồ sơ"><p role="status"><strong>Đã tạo đủ ba đầu ra{result.provisional?' BẢN TẠM':''}.</strong></p>{result.files.map((file,i)=><div className="workflow-file" key={file.path}><a href={'/api/export/download?day='+data.dayId+'&file='+i} download={file.name}>{file.name}</a><small>{file.path}</small></div>)}</section>}
 {error&&<p role="alert" className="error-banner">{error}</p>}<div className="receipt-actions">{onClose&&<Button label="Đóng" variant="ghost" onClick={onClose} isDisabled={busy}/>}{preview&&!result&&<ConfirmationButton label={preview.provisional?'Xuất BẢN TẠM':'Xuất đủ ba đầu ra'} successLabel="Đã xuất hồ sơ" onClick={save} busy={busy} confirmed={confirmed} isDisabled={preview.blockers.length>0||(preview.provisional&&!consent)}/>}</div>
 </div></Modal>
}
