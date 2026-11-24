import React,{useState,useEffect,useRef,memo,useMemo,useCallback} from 'react';
import {createRoot} from 'react-dom/client';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {Button} from '@astryxdesign/core/Button';
import {IconButton} from '@astryxdesign/core/IconButton';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Selector} from '@astryxdesign/core/Selector';
import {DateInput} from '@astryxdesign/core/DateInput';
import {TimeInput} from '@astryxdesign/core/TimeInput';
import {ScanLine,ChevronLeft,ChevronRight,ChevronDown,Search,Plus,Minus,Expand,PanelLeft,Columns2,Check,Copy,FileImage,ArrowUpRight,Sparkles,X,GripVertical,Clock3,ArrowDownToLine,LayoutDashboard,LibraryBig,BookOpen,Wallet,ChartNoAxesCombined,Sheet,Database,Settings} from 'lucide-react';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import './style.css';
import OcrPanel from './OcrPanel';
import KnowledgePage from './KnowledgePage';
import RowContextMenu from './RowContextMenu';
import ReceiptHistory from './ReceiptHistory';
import BusinessPage, {businessPages} from './BusinessPages';
import RecAssistant from './RecAssistant';
import {ReviewReceipt,ExportReceipts} from './ReceiptWorkflow';
import CommandButton from './CommandButton';
import HoldButton from './HoldButton';
import ConfirmationButton, {useConfirmation} from './ConfirmationButton';

const numberFormatter=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const money=v=>typeof v==='number'&&Number.isFinite(v)?numberFormatter.format(v):'Chưa rõ';
const amount=r=>typeof r['Thực nhận']==='number'&&typeof r['Đơn giá']==='number'?r['Thực nhận']*r['Đơn giá']:null;

function CompactTimeInput({value,onChange,isDisabled}){
 const [open,setOpen]=useState(false),[draft,setDraft]=useState(value||'');
 useEffect(()=>{if(!open)setDraft(value||'')},[value,open]);
 const [hour='09',minute='00']=draft.split(':');
 const apply=()=>{onChange(draft||undefined);setOpen(false)};
 return <div className="compact-time-field"><label>Giờ nhận</label><button type="button" className="compact-time-control" aria-label="Mở chọn giờ nhận" disabled={isDisabled} onClick={()=>setOpen(v=>!v)}><Clock3 size={14}/><span>{value||'HH:MM'}</span></button>
  {open&&<div className="compact-time-popover" role="dialog" aria-label="Chọn giờ nhận"><div className="compact-time-selects"><select aria-label="Giờ" value={hour} onChange={e=>setDraft(`${e.target.value}:${minute}`)}>{Array.from({length:24},(_,i)=>String(i).padStart(2,'0')).map(v=><option key={v}>{v}</option>)}</select><span>:</span><select aria-label="Phút" value={minute} onChange={e=>setDraft(`${hour}:${e.target.value}`)}>{Array.from({length:60},(_,i)=>String(i).padStart(2,'0')).map(v=><option key={v}>{v}</option>)}</select></div><div className="compact-time-actions"><input aria-label="Nhập giờ theo định dạng HH:MM" inputMode="numeric" placeholder="HH:MM" maxLength={5} value={draft||''} onChange={e=>setDraft(e.target.value.replace(/[^0-9:]/g,'').slice(0,5))}/><button type="button" onClick={()=>setOpen(false)}>Hủy</button><button type="button" onClick={apply}>Lưu</button></div></div>}
  </div>;
}

function SaveStatus({busy,message}){
 const success=Boolean(message)&&!busy;
 return <div className={'save-status '+((busy||message)?'is-visible ':'')+(success?'is-success':'')} role="status" aria-live="polite"><span className="save-status-icon" aria-hidden="true">{success?'✓':''}</span><span>{busy?'Đang cập nhật…':message}</span></div>;
}

function Tool({label,icon,onClick,disabled=false}){return <IconButton label={label} tooltip={label} icon={icon} size="sm" variant="ghost" onClick={onClick} isDisabled={disabled}/>}
function ReceiptNavButton({label,icon,onClick,disabled=false}){return <button type="button" className="receipt-nav-button" aria-label={label} title={label} onClick={onClick} disabled={disabled}>{icon}</button>}
function Modal({title,children,onClose,className=''}){const ref=useRef(null);useEffect(()=>{ref.current.showModal();return ()=>ref.current?.close()},[]);return <dialog ref={ref} className={"modal "+className} aria-labelledby="dialog-title" onCancel={event=>{event.preventDefault();onClose()}}><header><h2 id="dialog-title">{title}</h2><Tool label="Đóng" icon={<X/>} onClick={onClose}/></header>{children}</dialog>}

const Viewer=memo(function Viewer({doc,expanded,onExpand,prPages,prLabel,receiptNavigation}){
 const [deliveryPage,setDeliveryPage]=useState(0),[prSelection,setPrSelection]=useState(null);
 const prKey=prPages?.length?prPages.join(','):null;
 const showingPr=Boolean(prKey&&prSelection?.key===prKey);
 const pages=showingPr?prPages:doc.pages;
 const page=Math.max(0,Math.min(showingPr?prSelection.page:deliveryPage,pages.length-1));
 const file=showingPr?prLabel:doc.file;
 const [zoom,setZoom]=useState(100),[fit,setFit]=useState('width'),[copyStatus,setCopyStatus]=useState('');
 const zoomTarget=useRef(100),zoomFrame=useRef(null);
 const changeZoom=delta=>{zoomTarget.current=Math.max(50,Math.min(300,zoomTarget.current+delta));if(zoomFrame.current)return;zoomFrame.current=requestAnimationFrame(()=>{zoomFrame.current=null;setZoom(zoomTarget.current)})};
 const resetZoom=()=>{zoomTarget.current=100;setZoom(100)};
 useEffect(()=>()=>{if(zoomFrame.current)cancelAnimationFrame(zoomFrame.current)},[]);
 const canvas=useRef(null),image=useRef(null),drag=useRef(null);const [width,setWidth]=useState(0);
 const [showCorrected,setShowCorrected]=useState(false);
 // The preview and locator use the same prepared pixels. Keep the image URL stable as coordinates arrive.
 const correctedPages=showingPr?null:doc.correctedPages;
 const corrected=showCorrected&&Boolean(correctedPages);
 const documentImage=useRef(null);const [loadedSrc,setLoadedSrc]=useState('');
 const imageSrc=(corrected?correctedPages:pages)[page];
 useEffect(()=>{const node=canvas.current;const size=()=>{const img=image.current;let w=node.clientWidth-32;if(fit==='page'&&img?.naturalWidth)w=Math.min(w,(node.clientHeight-32)*img.naturalWidth/img.naturalHeight);setWidth(Math.max(1,w))};const observer=new ResizeObserver(size);observer.observe(node);size();image.current?.addEventListener('load',size);return ()=>{observer.disconnect();image.current?.removeEventListener('load',size)}},[fit,imageSrc]);
 useEffect(()=>{const el=canvas.current;const wheel=e=>{if(e.ctrlKey){e.preventDefault();changeZoom(e.deltaY<0?10:-10)}};el.addEventListener('wheel',wheel,{passive:false});return ()=>el.removeEventListener('wheel',wheel)},[]);
 async function copyImage(){
  const source=image.current;
  if(!source?.complete||!source.naturalWidth){setCopyStatus('error');return}
  try{
   const bitmap=await createImageBitmap(source);const surface=document.createElement('canvas');surface.width=bitmap.width;surface.height=bitmap.height;surface.getContext('2d').drawImage(bitmap,0,0);bitmap.close();
   const blob=await new Promise(resolve=>surface.toBlob(resolve,'image/png'));
   if(!blob||!navigator.clipboard?.write||!window.ClipboardItem)throw Error('clipboard-unavailable');
   await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);setCopyStatus('success');setTimeout(()=>setCopyStatus(''),1600);
  }catch{setCopyStatus('error');setTimeout(()=>setCopyStatus(''),2200)}
 }
 function start(e){if(e.button!==0)return;drag.current={x:e.clientX,y:e.clientY,l:canvas.current.scrollLeft,t:canvas.current.scrollTop};e.currentTarget.setPointerCapture(e.pointerId)}
 function pan(e){const d=drag.current;if(d){canvas.current.scrollLeft=d.l-(e.clientX-d.x);canvas.current.scrollTop=d.t-(e.clientY-d.y)}}
 return <section className={'viewer '+(expanded?'viewer-expanded':'')} aria-label={showingPr?"Ảnh PR":"Chứng từ gốc"}><header className="viewer-top">{receiptNavigation}<div><Button className={'copy-image-button '+(copyStatus==='success'?'is-success':'')} label={copyStatus==='success'?'Đã sao chép':copyStatus==='error'?'Không sao chép được':'Sao chép ảnh'} size="sm" variant="ghost" icon={copyStatus==='success'?<Check/>:<Copy/>} onClick={copyImage}/><Tool label="Thu nhỏ ảnh" icon={<Minus/>} onClick={()=>changeZoom(-25)}/><output>{zoom}%</output><Tool label="Phóng to ảnh" icon={<Plus/>} onClick={()=>changeZoom(25)}/><span className="v-sep"/>{correctedPages&&<Button label={corrected?'Xem ảnh gốc':'Xem ảnh đã căn'} size="sm" variant="ghost" onClick={()=>{setShowCorrected(v=>!v);resetZoom()}}/>}<Button label={fit==='width'?'Vừa ngang':'Cả trang'} size="sm" variant="ghost" onClick={()=>{setFit(f=>f==='width'?'page':'width');resetZoom()}}/><Tool label={expanded?'Đóng ảnh lớn':'Mở ảnh lớn'} icon={expanded?<X/>:<Expand/>} onClick={onExpand}/></div></header>

 <div className="document-canvas" ref={canvas} tabIndex={0} role="region" aria-label="Ảnh phiếu, kéo để di chuyển" onPointerDown={start} onPointerMove={pan} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null} onLostPointerCapture={()=>drag.current=null}>{!pages.length&&<p className="no-image">Phiếu này chưa có ảnh liên kết trong REC.</p>}<div className="mapped-document" ref={documentImage} style={{width:width||undefined,zoom:zoom/100}}><img ref={image} src={imageSrc||undefined} alt={(showingPr?'Ảnh PR ':'Phiếu REC ')+file} draggable={false} onLoad={()=>setLoadedSrc(imageSrc)}/></div></div>
 <footer className="viewer-footer">
  <div className="document-page-groups">
   <div className="document-page-group" role="group" aria-label="Trang phiếu giao">
    <strong>Phiếu giao</strong>
    <div className="image-pages">{doc.pages.map((src,i)=>
     <button key={src} type="button" aria-label={'Phiếu giao trang '+(i+1)}
      aria-pressed={!showingPr&&i===page}
      onClick={()=>{setPrSelection(null);setDeliveryPage(i);resetZoom()}}>
      <img alt="" src={src}/><span>Trang {i+1}</span>
     </button>)}</div>
   </div>
   {prKey&&<div className="document-page-group" role="group" aria-label="Trang PR">
    <strong>PR</strong>
    <div className="image-pages">{prPages.map((src,i)=>
     <button key={src} type="button" aria-label={'PR trang '+(i+1)}
      aria-pressed={showingPr&&i===page}
      onClick={()=>{setPrSelection({key:prKey,page:i});resetZoom()}}>
      <img alt="" src={src}/><span>Trang {i+1}</span>
     </button>)}</div>
   </div>}
  </div>
  <span>{pages.length?page+1:0} / {pages.length} trang <span className="desktop-hint">· Ctrl + cuộn để thu phóng</span></span>
 </footer></section>
});

const searchable=value=>String(value??'').toLowerCase().normalize('NFD').replace(/\p{M}/gu,'').replace(/đ/g,'d').replace(/[^\p{L}\p{N}]+/gu,' ').trim();

const invoiceName='Tên hàng trên phiếu (Ảnh)';
const itemCode='Mã vật tư';
const matchedName=row=>{
 const code=String(row[itemCode]??'').trim();
 return code&&code!=='CHUA CO MA' ? row['Tên chuẩn hệ thống']||row['Tên vật tư chuẩn']||'' : '';
};
const editableFields=[
 [invoiceName,'Tên hàng trên phiếu'],
 [itemCode,'Mã vật tư'],
 ['Đơn vị tính','Đơn vị tính'],
 ['Số lượng','SL giao','decimal'],
 ['Thực nhận','SL nhận','decimal'],
 ['Đơn giá','Đơn giá','decimal']
];

function CellEditor({row,column,onCommit,onCancel}){
 const [field,label,numeric]=editableFields[column];
 const initial=field===itemCode&&row[field]==='CHUA CO MA'?'':String(row[field]??'');
 const [value,setValue]=useState(initial),[busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const input=useRef(null),editor=useRef(null),submitting=useRef(false);
 useEffect(()=>{
  input.current?.focus();
  input.current?.select();
 },[]);
 async function commit(direction){
  if(submitting.current)return;
  submitting.current=true;
  setBusy(true);setError('');
  const next=numeric?value.trim().replace(',','.'):value;
  try{
   await onCommit(next===initial?{}:{[field]:next},direction);
  }catch(error){
   setError(error.message);
   if(direction!=='outside')requestAnimationFrame(()=>input.current?.focus());
  }finally{
   submitting.current=false;
   setBusy(false);
  }
 }
 useEffect(()=>{
  function handleOutside(event){
   if(!editor.current?.contains(event.target))commit('outside');
  }
  document.addEventListener('pointerdown',handleOutside,true);
  return ()=>document.removeEventListener('pointerdown',handleOutside,true);
 });
 return <div ref={editor} className="cell-editor" aria-busy={busy}>
  <input ref={input} aria-label={label} aria-invalid={error?true:undefined} inputMode={numeric}
   value={value} readOnly={busy} onChange={event=>setValue(event.target.value)} onKeyDown={event=>{
    if(event.nativeEvent.isComposing||!['Escape','Enter','Tab'].includes(event.key))return;
    event.preventDefault();event.stopPropagation();
    if(event.key==='Escape'){if(!submitting.current)onCancel();return}
    commit(event.key==='Enter'?'down':event.shiftKey?'previous':'next');
   }}/>
  {busy&&<span role="status">Đang lưu…</span>}
  {error&&<span role="alert">{error}</span>}
 </div>
}

function PrAssignment({items,rows,defaultIndex,defaultRow,onSave,expanded=false,onClose}){
 const [index,setIndex]=useState(defaultIndex==null?'':String(defaultIndex));
 const [targets,setTargets]=useState(()=>defaultRow==null?[]:[defaultRow]);
 const [remember,setRemember]=useState(false);
 const item=items.find(entry=>String(entry.index)===index);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [confirmed,showSuccess]=useConfirmation();
 const [activeTarget,setActiveTarget]=useState('');
 const Container=expanded?'section':'details';
 async function save(payload){
  if(busy)return;
  setBusy(true);setError('');
  setActiveTarget(payload.target===null?'missing':payload.target==='auto'?'auto':'match');
  try{await onSave({...payload,throwOnError:true});await showSuccess();onClose?.()}
  catch(error){setError(error.message)}
  finally{setBusy(false)}
 }
 function select(value){
  setIndex(value);
  setRemember(false);
  const next=items.find(entry=>String(entry.index)===value);
  setTargets(next?.lotRows?.length?next.lotRows:next?.row!=null?[next.row]:[]);
 }
 return <Container className={"pr-assignment "+(expanded?"pr-assignment-expanded":"")} aria-busy={busy}>
  {!expanded&&<summary>Sửa ghép dòng PR</summary>}
  {expanded&&<p className="pr-form-intro">Chọn mặt hàng PR và dòng giao tương ứng. Có thể chọn nhiều dòng nếu hàng được giao thành nhiều lô.</p>}
  <label>Mặt hàng trên PR
   <select value={index} onChange={event=>select(event.target.value)}>
    <option value="">Chọn mặt hàng PR</option>
    {items.map(entry=><option key={entry.index} value={entry.index}>{entry.index+1}. {entry.name} · {entry.code||'Chưa có mã'} · {entry.unit||'Chưa có ĐVT'}</option>)}
   </select>
  </label>
  <div className="pr-target-field">
   <span>Dòng giao <small>Chọn một hoặc nhiều lô</small></span>
   <div className="pr-target-list" role="group" aria-label="Dòng giao (có thể chọn nhiều lô)">
    {rows.map((row,i)=><label className="pr-target-option" key={row.sourceRow}>
     <input type="checkbox" checked={targets.includes(row.sourceRow)} onChange={event=>{setRemember(false);setTargets(current=>event.target.checked?[...current,row.sourceRow]:current.filter(value=>value!==row.sourceRow))}}/>
     <span><strong>{i+1}. {row[invoiceName]}</strong><small>{row[itemCode]||'Chưa có mã'} · {row['Đơn vị tính']||'Chưa có ĐVT'}</small></span>
    </label>)}
   </div>
  </div>
  <label style={{display:'flex',alignItems:'center',gap:8}}>
   <input type="checkbox" checked={remember} disabled={!item||targets.length!==1} onChange={event=>setRemember(event.target.checked)}/>
   Ghi nhớ cặp này cho nhà cung cấp
  </label>
  {error&&<p role="alert">{error}</p>}
  <div className="receipt-actions pr-form-footer">
   <ConfirmationButton label="Lưu ghép" successLabel="Đã lưu ghép" busy={busy&&activeTarget==='match'} confirmed={confirmed&&activeTarget==='match'} isDisabled={busy||!item||!targets.length} onClick={()=>save({action:'assign',index:item.index,target:targets,remember})}/>
   <ConfirmationButton label="Chưa giao lần này" busy={busy&&activeTarget==='missing'} confirmed={confirmed&&activeTarget==='missing'} isDisabled={busy||!item} onClick={()=>save({action:'assign',index:item.index,target:null})}/>
   <ConfirmationButton label="Trả về ghép tự động" successLabel="Đã lưu" busy={busy&&activeTarget==='auto'} confirmed={confirmed&&activeTarget==='auto'} isDisabled={busy||!item} onClick={()=>save({action:'assign',index:item.index,target:'auto'})}/>
  </div>
 </Container>
}

const prMenuGroups=[
 ['Ghép và nhận diện',[['assign','Sửa cặp PR ↔ dòng giao…'],['spec','Rà quy cách · Xác nhận cùng hàng…']]],
 ['Đơn vị và số lượng',[['conversion','Quy đổi đơn vị…'],['correction','Xác nhận NCC ghi sai lượng…'],['pr_quantity','Sửa lượng đọc từ ảnh PR…'],['stop_topup','Ngừng giao bù…'],['reopen_topup','Tiếp tục giao bù…']]],
 ['Duyệt ngoại lệ mua hàng',[['substitution','Duyệt hàng thay thế…'],['packaging','Duyệt mua nguyên gói…'],['overreceipt','Duyệt nhận dư…']]],
 ['Giá, thuế và cọc',[['vat','Tách VAT / khôi phục giá gốc…'],['price','Duyệt giá Purchase…'],['deposit','Xác nhận / bỏ cọc vỏ ngoài PR…']]]
];
function prQuery(data,doc){
 return new URLSearchParams({day:data.dayId,sheet:doc.file,version:data.version});
}

async function fetchPr(query,signal){
 const response=await fetch('/api/receipt/pr?'+query,{signal,cache:'no-store'});
 const result=await response.json();
 if(!response.ok)throw new Error(result.error);
 return result;
}

function PrActionDialog({action,doc,pr,onClose,onSave}){
 const item=pr.prItems?.find(i=>i.index===action.index);
 const [fields,setFields]=useState({remember:'yes',revision:String(pr.opening?.revision||0),receipts:pr.opening?.receipts||'',quantities:JSON.stringify(Object.fromEntries((pr.opening?.lines||[]).map(line=>[String(line.index),pr.opening?.quantities?.[String(line.index)]||'0']))),before:pr.opening?.before||'',consent:'',value:action.kind==='packaging'?item?.packaging?.value||'':'',reason:action.kind==='packaging'?item?.packaging?.reason||'':'',date:new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())});
 const [preview,setPreview]=useState(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [confirmed,showSuccess]=useConfirmation();
 const title=prMenuGroups.flatMap(([,items])=>items).find(([key])=>key===action.kind)?.[1]||(action.kind==='opening'?'Lượng nhận trước khi dùng REC':'Thao tác PR');
 const labels={conversion:`1 đơn vị giao = bao nhiêu ${item?.unit||'đơn vị PR'}?`,packaging:`Lượng trong 1 gói (${item?.unit||'ĐVT PR'})`,pr_quantity:`Số lượng đúng trên PR (${item?.unit||''})`,correction:'Số gói thực nhận',price:`Giá Purchase duyệt / ${item?.unit||'ĐVT PR'}`};
 function input(key,label,type='text'){return <label key={key}>{label}<input required type={type} value={fields[key]||''} onChange={event=>{setPreview(null);setFields(v=>({...v,[key]:event.target.value}))}}/></label>}
 async function submit(event){
  event.preventDefault();if(busy)return;setBusy(true);setError('');
  try{
   const result=await onSave({action:'row_action',kind:action.kind,index:action.index,row:action.row.sourceRow,preview:action.kind==='packaging'&&!preview,fields:preview?{...fields,confirmed_quantity:preview.approved,confirmed_cost:preview.extra_cost}:fields});
   if(result?.preview){setPreview(result.preview);return}
   await showSuccess();onClose()
  }
  catch(error){setError(error.message)}finally{setBusy(false)}
 }
 if(action.kind==='assign')return <Modal className="pr-dialog pr-dialog-wide" title="Ghép với dòng giao" onClose={onClose}><PrAssignment expanded onClose={onClose} items={pr.prItems||[]} rows={doc.rows} defaultIndex={action.index} defaultRow={action.row.sourceRow} onSave={onSave}/></Modal>;
 return <Modal className="pr-dialog" title={title?.replace(/…$/,'')} onClose={()=>{if(!busy)onClose()}}><form onSubmit={submit} className="pr-assignment pr-action-form">
  <div className="pr-action-context"><span>ĐANG XỬ LÝ</span><strong>{item?.name||action.row[invoiceName]}</strong><small>Phiếu giao: {action.row[invoiceName]}</small></div>
  {labels[action.kind]&&input('value',labels[action.kind])}
  {action.kind==='correction'&&<><p>Chỉ dùng khi NCC ghi sai lượng: xác nhận số gói × gram/gói, PR phải dùng kg/g. Để sửa số đã nhập thông thường, nhấp đúp trực tiếp ô SL nhận trong bảng.</p>{input('grams','Khối lượng mỗi gói (g)')}</>}
  {action.kind==='substitution'&&input('department','Bộ phận / người duyệt thay thế')}
  {['substitution','price','overreceipt','opening'].includes(action.kind)&&input('person','Người xác nhận / Purchase')}
  {['substitution','price'].includes(action.kind)&&input('date','Ngày xác nhận','date')}
  {action.kind==='opening'&&<>
   {pr.opening?.error&&<p role="alert">{pr.opening.error}</p>}
   {input('before','Đã nhận trước ngày','date')}
   {(pr.opening?.lines||[]).map(line=><label key={line.index}>{line.name} ({line.unit})<input inputMode="decimal" required value={JSON.parse(fields.quantities)[String(line.index)]||'0'} onChange={event=>setFields(v=>({...v,quantities:JSON.stringify({...JSON.parse(v.quantities),[String(line.index)]:event.target.value.replace(',','.')})}))}/></label>)}
   <label><input type="checkbox" required checked={fields.consent==='yes'} onChange={event=>setFields(v=>({...v,consent:event.target.checked?'yes':''}))}/>Đây là lượng trước mốc, chưa nằm trong các phiếu đã nhập REC.</label>
  </>}
  {input('reason',['stop_topup','reopen_topup'].includes(action.kind)?'Người/bộ phận xác nhận và lý do':'Căn cứ / lý do xác nhận')}
  {['stop_topup','reopen_topup'].includes(action.kind)&&<p>Quyết định được lưu trên phiếu và áp dụng khi ghi sổ nhận hàng.</p>}
  {['conversion','packaging'].includes(action.kind)&&<label><input type="checkbox" checked={fields.remember==='yes'} onChange={event=>setFields(v=>({...v,remember:event.target.checked?'yes':''}))}/>Ghi nhớ quy cách cho đúng nhà cung cấp và mặt hàng này</label>}
  {action.kind==='packaging'&&<p>Lượng mua sẽ làm tròn lên nguyên gói. Kiểm tra lượng và chi phí tăng trước khi xác nhận.</p>}
  {action.kind==='spec'&&<p>Chỉ xác nhận hai cách ghi là cùng sản phẩm, cùng quy cách. Không tự quy đổi lượng hay giá.</p>}
  {preview&&<p>Lượng PR đang dùng: {preview.requested} {preview.unit} · Mua nguyên gói: {preview.approved} {preview.unit} · Tăng: {preview.extra} {preview.unit} · Chi phí tăng: {money(preview.extra_cost)} đ</p>}
  {error&&<p role="alert">{error}</p>}
  <div className="receipt-actions pr-form-footer"><Button label="Hủy" variant="ghost" onClick={onClose} isDisabled={busy}/><ConfirmationButton type="submit" label={action.kind==='packaging'&&!preview?'Xem lượng và chi phí':'Xác nhận và lưu'} successLabel="Đã lưu" busy={busy} confirmed={confirmed}/></div>
 </form></Modal>
}

function UnreceivedDialog({pr,onSave,onClose}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [confirmed,showSuccess]=useConfirmation();
 const items=pr.pendingUnreceived||[];
 async function confirm(){if(busy)return;setBusy(true);try{await onSave({action:'mark_unreceived',indices:items.map(i=>i.index),throwOnError:true});await showSuccess();onClose()}catch(error){setError(error.message);setBusy(false)}}
 return <Modal className="pr-dialog" title="Các món còn lại chưa giao lần này" onClose={()=>{if(!busy)onClose()}}><div className="pr-assignment">
  <p>Xác nhận {items.length} món dưới đây không có trong phiếu giao đang mở. Các món đã ghép và số đã nhận trước được giữ nguyên; các món này vẫn được theo dõi giao bù.</p>
  <ul className="pr-unreceived-list">{items.map(item=><li key={item.index}>{item.index+1}. {item.name}</li>)}</ul>
  {(error||pr.unreceivedBlocked)&&<p role="alert">{error||pr.unreceivedBlocked}</p>}
  <div className="receipt-actions pr-form-footer"><Button label="Hủy" variant="ghost" onClick={onClose} isDisabled={busy}/><ConfirmationButton label="Xác nhận chưa giao lần này" busy={busy} confirmed={confirmed} isDisabled={!items.length||Boolean(pr.unreceivedBlocked)} onClick={confirm}/></div>
 </div></Modal>
}

function PrThumbnail({itemKey}){
 const [failed,setFailed]=useState(false);
 return <span className="pr-picker-thumbnail" aria-hidden="true">
  {failed?<FileImage size={21}/>:<img src={'/api/pr/thumbnail/'+encodeURIComponent(itemKey)}
   alt="" width="64" height="80" loading="lazy" decoding="async" onError={()=>setFailed(true)}/>}
 </span>;
}

function PrCompareImage({title,pages,empty}){
 const [page,setPage]=useState(0),[zoom,setZoom]=useState(false),[failed,setFailed]=useState('');
 const src=pages[page];
 return <section className="pr-compare-image">
  <header><h3>{title}</h3>
   {src&&<button type="button" aria-pressed={zoom} onClick={()=>setZoom(!zoom)}>{zoom?'Vừa khung':'Phóng to'}</button>}
  </header>
  <div className="pr-compare-canvas">
   {src&&failed!==src?<img className={zoom?'is-zoomed':''} src={src} alt={title+' · trang '+(page+1)}
    onError={()=>setFailed(src)}/>:<p>{src?'Không tải được ảnh.':empty}</p>}
  </div>
  {pages.length>1&&<div className="pr-compare-pages" aria-label={'Chuyển trang '+title}>
   <ReceiptNavButton label={'Trang trước · '+title} icon={<ChevronLeft size={16}/>} disabled={page===0} onClick={()=>setPage(page-1)}/>
   <span>{page+1} / {pages.length}</span>
   <ReceiptNavButton label={'Trang sau · '+title} icon={<ChevronRight size={16}/>} disabled={page===pages.length-1} onClick={()=>setPage(page+1)}/>
  </div>}
 </section>;
}

function PrPicker({linked,onSave,onClose,busy,day,sheet,version,receiptPages}){
 const [query,setQuery]=useState(''),[items,setItems]=useState([]),[error,setError]=useState('');
 const [selected,setSelected]=useState(null),[loading,setLoading]=useState(true),[saveError,setSaveError]=useState('');
 const [confirmed,showSuccess]=useConfirmation();
 const [preview,setPreview]=useState(null),[deliveryId,setDeliveryId]=useState('');
 const selectedKey=selected?.key;
 useEffect(()=>{
  if(!selectedKey)return;
  const controller=new AbortController();
  const params=new URLSearchParams({key:selectedKey,day,sheet,deliveries:'1'});
  fetch('/api/workspace/pr-images?'+params,{signal:controller.signal}).then(async response=>{
   const data=await response.json();
   if(!response.ok)throw Error(data.error||'Không tải được ảnh PR.');
   if(!controller.signal.aborted)setPreview({key:selectedKey,...data});
  }).catch(error=>{
   if(!controller.signal.aborted)setPreview({key:selectedKey,error:error.message});
  });
  return ()=>controller.abort();
 },[selectedKey,day,sheet]);
 const currentPreview=preview?.key===selectedKey?preview:null;
 const deliveries=currentPreview?.deliveries||[];
 const delivery=deliveries.find(item=>item.id===deliveryId);
 useEffect(()=>{
  const controller=new AbortController();
  const timer=setTimeout(async()=>{
   try{
    const response=await fetch('/api/pr/library?'+new URLSearchParams({q:query,day,sheet,version}),{signal:controller.signal});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Chưa mở được thư viện PR.');
    if(!controller.signal.aborted){setItems(result.items);setError('')}
   }catch(error){if(!controller.signal.aborted){setItems([]);setError(error.message)}}
   finally{if(!controller.signal.aborted)setLoading(false)}
  },query.trim()?180:0);
  return ()=>{clearTimeout(timer);controller.abort()};
 },[query,day,sheet,version]);
 const suggestions=query.trim()?[]:items.filter(item=>item.suggestion).slice(0,3);
 const suggestedKeys=new Set(suggestions.map(item=>item.key));
 const library=items.filter(item=>!suggestedKeys.has(item.key));
 function renderItem(item){
  return <button type="button" className="pr-picker-option" aria-pressed={selected?.key===item.key}
   disabled={busy} key={item.key} onClick={()=>{setSelected(item);setDeliveryId('');setSaveError('')}}>
   <PrThumbnail itemKey={item.key}/>
   <span className="pr-picker-option-text"><strong>{item.label}</strong><small>{item.count} dòng{item.sample.length>0&&' · '+item.sample.join(' · ')}</small>
    {item.suggestion&&suggestedKeys.has(item.key)&&<span className="pr-picker-reason">{item.suggestion}</span>}</span>
   {selected?.key===item.key&&<Check size={17}/>}
  </button>;
 }
 return <Modal className="pr-picker-dialog" title={linked?'Đổi PR đã ghép':'Chọn PR'} onClose={()=>{if(!busy&&!confirmed)onClose()}}>
  <div className="pr-picker-body">
   <p className="pr-picker-context">{sheet}</p>
   <TextInput type="search" label="Số PO/PR, NCC, ngày hoặc bộ phận" value={query} isDisabled={busy}
    onChange={value=>{if(value!==query){setQuery(value);setLoading(true);setSelected(null);setSaveError('')}}} hasClear/>
   {error&&<p role="alert">{error}</p>}
   <div className="pr-picker-workspace">
   <div className="pr-picker-results" aria-busy={loading}>
    {loading?<p role="status">Đang tìm PR…</p>:<>
     {suggestions.length>0&&<section><h3>Gợi ý cho phiếu này</h3>{suggestions.map(renderItem)}</section>}
     {library.length>0&&<section><h3>{query.trim()?'Kết quả tìm kiếm':'Thư viện PR'}</h3>{library.map(renderItem)}</section>}
     {!error&&!items.length&&<p>Không tìm thấy PR.</p>}
    </>}
   </div>
   <div className="pr-picker-comparison">
    <PrCompareImage key={selectedKey||'unselected'} title="PR / PO" pages={currentPreview?.pages||[]}
     empty={currentPreview?.error||(selectedKey?'Đang tải ảnh PR…':'Chọn PR để xem ảnh.')}/>
    <div className="pr-picker-delivery">
     {deliveries.length>0&&<select aria-label="Chọn phiếu giao hàng" value={delivery?.id||''} onChange={event=>setDeliveryId(event.target.value)}>
      <option value="">Phiếu đang kiểm · {sheet}</option>
      {deliveries.map(item=><option key={item.id} value={item.id}>Đã giao · {item.day.split('-').reverse().join('/')} · {item.sheet}</option>)}
     </select>}
     <PrCompareImage key={delivery?.id||sheet} title={delivery?'Phiếu giao đã ghi sổ':'Phiếu giao đang kiểm'}
      pages={delivery?.pages||receiptPages} empty="Phiếu này chưa có ảnh khả dụng."/>
    </div>
   </div>
   </div>
   {saveError&&<p role="alert" className="error-banner">{saveError}</p>}
   <div className="pr-picker-footer">
    <Button label="Hủy" variant="secondary" isDisabled={busy||confirmed} onClick={onClose}/>
    <ConfirmationButton label="Ghép PR đã chọn" successLabel="Đã ghép PR" busy={busy} confirmed={confirmed} isDisabled={!selected||loading} onClick={async()=>{
     try{await onSave({action:'choose',key:selected.key,throwOnError:true});await showSuccess();onClose()}
     catch(error){setSaveError(error.message)}
    }}/>
   </div>
  </div>
 </Modal>
}

const ReceiptReviewSummary=memo(function ReceiptReviewSummary({pr,rows}){
 if(pr?.status!=='ready')return null;
 const seen=new Set();const deficits=[];const review=[];
 for(const row of rows){const value=pr.rows?.[row.sourceRow];if(!value||value.method==='lot')continue;const key=value.prIndex??'row'+row.sourceRow;if(seen.has(key))continue;seen.add(key);
  if(value.delta<0)deficits.push({name:row[invoiceName],quantity:-value.delta,unit:value.unit});
  else if(value.attention&&value.method==='conflict')review.push(row[invoiceName]);
 }
 const pending=(pr.unmatchedItems||[]).filter(item=>!item.confirmed).length;
 if(!deficits.length&&!review.length&&!pending)return null;
 return <div className="receipt-review-summary" role="status">
  {deficits.length>0&&<span><strong>{deficits.length} món thiếu so với PR:</strong> {deficits.slice(0,3).map(item=>item.name+' '+money(item.quantity)+' '+item.unit).join(' · ')}{deficits.length>3?' · …':''}.</span>}
  {(review.length>0||pending>0)&&<span>{[review.length>0?review.length+' dòng cần rà quy cách / mã':'',pending>0?pending+' món PR chưa xác định dòng giao':''].filter(Boolean).join(' · ')}.</span>}
 </div>;
});

const ReceiptMetadata=memo(function ReceiptMetadata({doc,draft,departments,itemQuery,rowSaving,actions}){
 const selectedDepartment=draft?.warehouseCode??doc.warehouseCode??'__mixed';
 const options=[{value:'',label:'Chưa gán bộ phận'},...(departments||[]).map(({code,department,name})=>({
  value:code,label:name||department||'Chưa đặt tên',description:department&&department!==name?`Bộ phận ${department}`:undefined
 }))];
 if(selectedDepartment&&!options.some(option=>option.value===selectedDepartment)){
   options.push({value:selectedDepartment,label:selectedDepartment==='__mixed'?'Phiếu có nhiều bộ phận':'Bộ phận chưa có trong danh mục',description:'Đang giữ mã kho đã lưu',disabled:true});
 }
 return <div className="metadata">
  <TextInput label="Nhà cung cấp" value={draft?.supplierName??doc.supplier??''}
   onChange={value=>actions.current.saveMetadata('supplierName',value)} isDisabled={rowSaving} placeholder="Tên nhà cung cấp…" size="sm"/>
  <CompactTimeInput value={(draft?.receiptTime??doc.receiptTime)||''}
   onChange={value=>actions.current.saveMetadata('receiptTime',value?value.slice(0,5):'')}
   isDisabled={rowSaving}/>
  <Selector label="Bộ phận nhận hàng" size="sm" isDisabled={rowSaving||!departments?.length} options={options} value={selectedDepartment}
   onChange={value=>{if(typeof value==='string')actions.current.saveMetadata('warehouseCode',value)}}
   searchPlaceholder="Tìm bộ phận / kho…"/>
 </div>;
});

function PrResultDetails({doc,row,comparison,pr,onSave,onClose}){
 const [editing,setEditing]=useState(false);
 const item=pr.prItems?.find(item=>item.index===comparison?.prIndex);
 const quantity=value=>value==null?'—':money(value);
 if(editing)return <Modal className="pr-dialog pr-dialog-wide" title="Ghép với dòng giao" onClose={onClose}><PrAssignment expanded onClose={onClose} items={pr.prItems||[]} rows={doc.rows} defaultIndex={comparison?.prIndex} defaultRow={row.sourceRow} onSave={onSave}/></Modal>;
 return <Modal className="pr-dialog pr-dialog-wide pr-result-dialog" title="Kết quả nhận hàng" onClose={onClose}>
  <div className="pr-assignment pr-result-details">
   <div className="pr-result-heading"><span>MẶT HÀNG TRÊN PR</span><h3>{comparison?.prName||item?.name||'Chưa xác định mặt hàng PR'}</h3>
    <small>{[comparison?.prLine&&'Dòng PR '+comparison.prLine,comparison?.prCode&&'Mã '+comparison.prCode].filter(Boolean).join(' · ')}</small>
   </div>
   <div className="pr-result-outcome" style={{color:comparison?.outcomeColor}}>{comparison?.outcome||'Cần rà lại'}</div>
   <dl className="pr-result-metrics">
    {[['Đặt trên PR',comparison?.ordered],['Đã nhận trước',comparison?.previous],['Nhận lần này',comparison?.received],['Còn lại',comparison?.remaining]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{quantity(value)}<small>{comparison?.unit||item?.unit||''}</small></dd></div>)}
   </dl>
   <dl className="pr-result-facts">
    <div><dt>Trên phiếu giao</dt><dd>{row[invoiceName]}</dd></div>
    <div><dt>Số lượng ghi trên phiếu</dt><dd>{quantity(row['Số lượng'])} {row['Đơn vị trên phiếu']||row['Đơn vị tính']||''}</dd></div>
    {comparison?.reason&&<div><dt>Căn cứ ghép</dt><dd>{comparison.reason}</dd></div>}
    {comparison?.status&&<div><dt>Chi tiết đối chiếu</dt><dd>{comparison.status}</dd></div>}
   </dl>
   <div className="receipt-actions pr-form-footer"><Button label="Đóng" variant="ghost" onClick={onClose}/><Button label="Sửa ghép dòng PR" variant="primary" onClick={()=>setEditing(true)}/></div>
  </div>
 </Modal>
}

const DataRow=memo(function DataRow({row,index,doc,pr,selected,editing,prDetail,handlers}){
 const comparing=pr?.status==='ready';
 const onSelect=(...args)=>handlers.current.onSelect(...args),onEdit=(...args)=>handlers.current.onEdit(...args),onContext=(...args)=>handlers.current.onContext(...args),onCancel=()=>handlers.current.onCancel(),commit=(...args)=>handlers.current.commit(...args),focusCell=(...args)=>handlers.current.focusCell(...args),setPrDetail=(...args)=>handlers.current.setPrDetail(...args);
    const comparison=pr?.rows?.[row.sourceRow];
    const showDetail=pr?.status==='ready'&&prDetail===doc.id+'::'+row.sourceRow;
    const values=[
     <><span className="row-number">{String(index+1).padStart(2,'0')}</span><span>{row[invoiceName]}</span></>,
     matchedName(row)?<span>{matchedName(row)}<small>{row[itemCode]}</small></span>:<span className="unmatched-item">Chưa khớp mã</span>,
    ];
    function renderEditor(column,value,unit=false){
     if(editing?.row===row.sourceRow&&editing.column===column){
      return <CellEditor row={row} column={column}
       onCommit={(changes,direction)=>commit(index,column,changes,direction)}
       onCancel={()=>{onCancel();focusCell(index,column)}}/>;
     }
     return <button type="button" className={unit?'cell-button receipt-unit':'cell-button'}
      data-column={column} aria-label={unit?'Đơn vị tính: '+value:undefined}
      title="Nhấp đúp hoặc F2 để sửa"
      onDoubleClick={()=>onEdit(index,column)} onKeyDown={event=>{
       if(event.key==='F2'||event.key==='Enter'){event.preventDefault();onEdit(index,column)}
      }}>{value}</button>;
    }
    return <React.Fragment key={row.sourceRow}><tr data-line={index} onClick={event=>{
     if(!event.target.closest('input,select,textarea,a,[contenteditable],button:not(.cell-button)'))onSelect(index);
    }} onContextMenu={event=>{if(!event.target.closest('input')){event.preventDefault();onContext(event,row,index)}}} className={[selected?'selected':'',comparison?.delta<0?'receiving-short':''].filter(Boolean).join(' ')}>
     <th scope="row">{renderEditor(0,values[0])}
      <div className="receipt-unit-wrap">{renderEditor(2,row['Đơn vị tính']||'Chưa có ĐVT',true)}</div>
     </th>
     <td>{renderEditor(1,values[1])}</td>
     <td className="line-number-cell">
      {comparison?.ordered==null?'—':money(comparison.ordered)}
      {comparison?.unit&&<small>{comparison.unit}</small>}
     </td>
     <td className="line-number-cell">{renderEditor(4,money(row['Thực nhận']))}</td>
     <td className="line-number-cell">{renderEditor(5,money(row['Đơn giá']))}</td>
     <td className="pr-outcome">{comparing?
      <button type="button" className="pr-line-detail" aria-haspopup="dialog"
       style={{color:comparison?.outcomeColor}}
       onClick={()=>setPrDetail(showDetail?null:doc.id+'::'+row.sourceRow)}>
       <span className={'receiving-badge '+(comparison?.delta<0?'is-short':comparison?.delta>0?'is-over':comparison?.method==='conflict'?'is-review':'is-neutral')}>{(comparison?.outcome||'Chưa gán PR').split(' · ')[0]}</span>
       {comparison?.outcome?.includes(' · ')&&<span className="receiving-followup">{comparison.outcome.split(' · ').slice(1).join(' · ')}</span>}
       <small>{{manual:'Đã gán',code:'Cùng mã',remembered:'Theo cặp đã duyệt',suggested:'Gợi ý ghép',conflict:'Cần rà'}[comparison?.method]||''}</small>
      </button>:'—'}</td>
    </tr>
    </React.Fragment>
   

});

const DataTable=memo(function DataTable({doc,visibleRows,selected,onSelect,editing,onEdit,onSave,onCancel,onContext,pr,onPrSave}){
 const table=useRef(null);
 const [prDetail,setPrDetail]=useState(null);
 const handlers=useRef(null);
 handlers.current={onSelect,onEdit,onContext,onCancel,commit,focusCell,setPrDetail};
 const columns=[0,2,1,4,5];
 function focusCell(index,column){
  requestAnimationFrame(()=>table.current?.querySelector(`[data-line="${index}"] [data-column="${column}"]`)?.focus());
 }
 async function commit(index,column,changes,direction){
  if(Object.keys(changes).length)await onSave(doc.rows[index].sourceRow,changes);
  if(direction==='outside'){onCancel();return}
  const position=visibleRows.findIndex(entry=>entry.index===index);
  let nextPosition=position,nextColumn=column;
  if(direction==='down')nextPosition++;
  else{
   const step=direction==='next'?1:-1;
   const flat=position*columns.length+columns.indexOf(column)+step;
   nextPosition=Math.floor(flat/columns.length);
   nextColumn=columns[(flat+columns.length)%columns.length];
  }
  const nextRow=visibleRows[nextPosition];
  if(nextRow)onEdit(nextRow.index,nextColumn);
  else{onCancel();focusCell(index,column)}
 }
 return <div ref={table} className="data-scroll receipt-lines" tabIndex={0} role="region" aria-label="Bảng hàng hóa REC">
  <table><caption>Hàng hóa từ báo cáo REC, sheet {doc.file}</caption>
   <colgroup>{[26,23,10,10,12,19].map((width,index)=><col key={index} style={{width:width+'%'}}/>)}</colgroup>
   <thead><tr>{['Tên trên phiếu','Tên hệ thống','SL PR','SL nhận','Đơn giá','Kết quả nhận hàng'].map((label,index)=>
    <th key={label} className={index>=2&&index<=4?'line-number-cell':index===5?'pr-outcome':''} scope="col">{label}</th>)}</tr></thead>
   <tbody>{visibleRows.map(({row,index})=><DataRow key={row.sourceRow} row={row} index={index} doc={doc} pr={pr} selected={selected===index} editing={editing?.row===row.sourceRow?editing:null} prDetail={prDetail===doc.id+'::'+row.sourceRow?prDetail:null} handlers={handlers}/>)}
   {visibleRows.length===0&&<tr><td colSpan={6}>Không tìm thấy hàng hóa phù hợp.</td></tr>}</tbody>
  </table>
  {pr?.status==='ready'&&doc.rows.filter(row=>prDetail===doc.id+'::'+row.sourceRow).map(row=><PrResultDetails key={doc.id+'::'+row.sourceRow} doc={doc} row={row} comparison={pr.rows?.[row.sourceRow]} pr={pr} onSave={onPrSave} onClose={()=>setPrDetail(null)}/>)}
 </div>
});

const receiptCommands=[
 ['vat','Tách VAT 8% / 10%…'],['lookup','Tra mã cho dòng…'],['delete','Xóa dòng…'],
 ['no_po','Không có PR/PO — theo dõi thủ công…'],
 ['nickname','Đặt tên NCC ngắn gọn…'],['merge','Ghép trang…'],['remove_receipt','Gỡ phiếu nhập nhầm…'],['capture_time','Đổi giờ chụp hàng loạt…'],['rotate_source','Xoay ảnh nguồn…'],['unreceived','Các món còn lại chưa giao lần này…'],['opening','Nhận trước REC…']
];

function ReceiptActions({action,doc,receipts,pr,onClose,onApply}){
 const [value,setValue]=useState(action.kind==='nickname'?doc.supplierNickname||'':'');
 const [items,setItems]=useState([]);
 const [captureSheets,setCaptureSheets]=useState([doc.file]);
 const [sourcePage,setSourcePage]=useState(0);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [confirmed,showSuccess]=useConfirmation();
 useEffect(()=>{
  if(action.kind!=='lookup'||!value.trim()){setItems([]);return}
  const controller=new AbortController();
  const timer=setTimeout(async()=>{
   try{
    const response=await fetch('/api/catalog/search?'+new URLSearchParams({q:value}),{signal:controller.signal});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error);
    setItems(result.items);setError('');
   }catch(error){if(!controller.signal.aborted)setError(error.message)}
  },180);
  return ()=>{clearTimeout(timer);controller.abort()};
 },[action.kind,value]);
 async function apply(fields){
  if(busy)return;
  setBusy(true);setError('');
  try{await onApply(fields,showSuccess)}
  catch(error){setError(error.message);setBusy(false)}
 }
 return <Modal className={action.kind==='vat'?'pr-dialog':''} title={receiptCommands.find(entry=>entry[0]===action.kind)[1].replace(/…$/,'')} onClose={()=>{if(!busy)onClose()}}>
  <div className={action.kind==='vat'?'receipt-command-body pr-assignment':'receipt-command-body'}>
   {action.kind==='vat'&&<>
    <div className="pr-action-context"><span>ĐƠN GIÁ PHIẾU GIAO</span><strong>{action.row[invoiceName]}</strong><small>Đang lưu: {money(action.row['Đơn giá'])} đ / {action.row['Đơn vị tính']}</small></div>
    <p>Chọn thuế suất khi giá NCC đã gồm VAT. REC giữ giá gốc để bạn có thể khôi phục.</p>
    <Selector label="Xử lý VAT" value={value||undefined} onChange={setValue} options={[{value:'8',label:'Tách VAT 8%'},{value:'10',label:'Tách VAT 10%'},{value:'0',label:'Khôi phục giá NCC gốc'}]}/>
    <div className="receipt-actions pr-form-footer"><Button label="Hủy" variant="ghost" onClick={onClose} isDisabled={busy}/><ConfirmationButton label="Xác nhận và lưu" successLabel="Đã lưu VAT" busy={busy} confirmed={confirmed} isDisabled={value===''} onClick={()=>apply({row:action.row.sourceRow,rate:Number(value)})}/></div>
   </>}
   {action.kind==='lookup'&&<>
    <CommandButton label="Tra mã hàng" placeholder="Tên hoặc mã vật tư" shortcut="mod+l" width={300} onSearch={setValue}/>
    <div className="receipt-command-list">{items.map(item=><button type="button" disabled={busy} key={item.code} onClick={()=>apply({code:item.code})}><strong>{item.name}</strong><small>{item.code} · {item.unit}</small></button>)}</div>
   </>}
   {action.kind==='delete'&&<><p>Xóa dòng <strong>{action.row[invoiceName]}</strong> khỏi báo cáo?</p>
    <ConfirmationButton label="Xóa dòng" successLabel="Đã xóa dòng" busy={busy} confirmed={confirmed} onClick={()=>apply({row:action.row.sourceRow})}/></>}
   {action.kind==='capture_time'&&<form className="business-form" onSubmit={event=>{event.preventDefault();apply({time:value,sheets:captureSheets})}}>
    <label>Giờ chụp <input type="time" required value={value} onChange={event=>setValue(event.target.value)}/></label>
    <fieldset><legend>Phiếu trong ngày</legend>
     <label><input type="checkbox" checked={captureSheets.length===receipts.length}
      onChange={event=>setCaptureSheets(event.target.checked?receipts.map(item=>item.file):[])}/> Chọn tất cả</label>
     <div className="business-receipt-list">{receipts.map(item=><label key={item.file}>
      <input type="checkbox" checked={captureSheets.includes(item.file)} onChange={event=>setCaptureSheets(previous=>
       event.target.checked?[...previous,item.file]:previous.filter(name=>name!==item.file))}/> {item.file} · {item.supplier}
     </label>)}</div>
    </fieldset>
    <Button type="submit" label="Lưu giờ chụp" isDisabled={busy||!value||!captureSheets.length}/>
   </form>}
   {action.kind==='rotate_source'&&<>
    <label>Trang ảnh <select value={sourcePage} onChange={event=>setSourcePage(Number(event.target.value))}>
     {doc.pages.map((page,index)=><option key={page} value={index}>Trang {index+1}</option>)}
    </select></label>
    <div className="business-tools">{[[90,'Xoay trái'],[-90,'Xoay phải']].map(([delta,label])=>
     <Button key={delta} label={label} isDisabled={busy||!doc.pages.length}
      onClick={()=>apply({delta,index:sourcePage,sourceToken:doc.reviewToken})}/>)}</div>
   </>}
   {action.kind==='remove_receipt'&&<>
    <p>Gỡ phiếu <strong>{doc.file}</strong>{doc.pages.length > 0 && ` và ${doc.pages.length} trang ảnh`} khỏi báo cáo ngày? {doc.pages.length ? 'REC giữ ảnh gốc và tạo bản sao lưu báo cáo.' : 'Phiếu chưa có ảnh liên kết. REC sẽ sao lưu báo cáo trước khi gỡ.'}</p>
    <div className="receipt-actions pr-form-footer">
     <button type="button" autoFocus disabled={busy} onClick={onClose}>Hủy</button>
     <HoldButton busy={busy} onConfirm={()=>apply({sourceToken:doc.reviewToken,withoutImages:doc.pages.length===0})}/>
    </div>
   </>}
   {action.kind==='nickname'&&<>
    <TextInput label="Tên hiển thị" value={value} onChange={setValue} placeholder={doc.supplier}/>
    <Button label="Lưu tên" isDisabled={busy} onClick={()=>apply({label:value})}/>
   </>}
   {action.kind==='no_po'&&<><p>Chọn cách theo dõi cho phiếu {doc.file}.</p>
    <div className="receipt-actions">
     <Button label="Có PR/PO" variant="secondary" isDisabled={busy} onClick={()=>apply({enabled:false})}/>
     <Button label="Không có PR/PO" isDisabled={busy} onClick={()=>apply({enabled:true})}/>
    </div></>}
   {action.kind==='merge'&&<><p>Chọn phiếu trong ngày chứa trang của cùng chứng từ. Kiểm tra số phiếu và thứ tự ảnh trước khi ghép.</p>
    <Selector label="Phiếu cần ghép" options={receipts.filter(r=>r.id!==doc.id).map(r=>({value:r.file,label:r.file+' · '+(r.supplierNickname||r.supplier)}))} value={value||undefined} onChange={setValue}/>
    <div className="receipt-merge-images">{[doc,receipts.find(r=>r.file===value)].filter(Boolean).flatMap(r=>r.pages.map((url,i)=><a key={url} href={url} target="_blank" rel="noreferrer"><img src={url} alt={r.file+' trang '+(i+1)}/></a>))}</div>
    <ConfirmationButton label="Ghép trang" successLabel="Đã ghép trang" busy={busy} confirmed={confirmed} isDisabled={!value} onClick={()=>apply({other:value})}/>
   </>}
   {error&&<p className="error-banner" role="alert">{error}</p>}
  </div>
 </Modal>
}

function PageFrame({title,children,className=''}) {
 return <section className={'page-frame '+className}><header><h1>{title}</h1></header>{children}</section>;
}

const receiptPages = [['intake','Nhận phiếu'],['review','Kiểm phiếu'],['history','Tìm phiếu'],['export','Xuất hồ sơ']];
const directoryPages = [['directory','Danh mục'],['knowledge','Ghi nhớ']];
const workspacePages = [businessPages[0],['review','Phiếu giao'],...businessPages.slice(1),['assistant','Trợ lý REC']];

function PageNavigation({label,items,current,onChange,className,disabled}) {
 return <nav aria-label={label} className={className}>
  {items.map(([id,name])=><button type="button" key={id} aria-current={current===id?'page':undefined}
   disabled={disabled} onClick={()=>onChange(id)}>{name}</button>)}
 </nav>;
}

const workspaceIcons=[LayoutDashboard,FileImage,LibraryBig,BookOpen,Wallet,ChartNoAxesCombined,Sheet,Database,Settings,Sparkles];

const supplierLabel=receipt=>receipt.supplierNickname||receipt.supplier||'Chưa có nhà cung cấp';

function ReceiptSelector({receipts,index,onSelect,busy}) {
 const [open,setOpen]=useState(false);
 const [filter,setFilter]=useState('');
 const root=useRef(null), trigger=useRef(null);
 const doc=receipts[index];
 const query=searchable(filter.trim());
 const matches=useMemo(()=>receipts.map((receipt,index)=>({receipt,index}))
  .filter(({receipt})=>searchable(receipt.file+' '+supplierLabel(receipt)).includes(query)),
  [receipts,query]);

 useEffect(()=>{
  if(!open)return;
  function dismiss(event){
   if(event.type==='pointerdown' && root.current.contains(event.target))return;
   if(event.type==='keydown' && event.key!=='Escape')return;
   if(event.type==='keydown'){
    event.stopPropagation();
    trigger.current.focus();
   }
   setOpen(false);
  }
  document.addEventListener('pointerdown',dismiss);
  document.addEventListener('keydown',dismiss);
  return ()=>{
   document.removeEventListener('pointerdown',dismiss);
   document.removeEventListener('keydown',dismiss);
  };
 },[open]);

 return <div className="receipt-strip" ref={root}>
  <div className="receipt-selector">
   <button type="button" ref={trigger} className="receipt-name receipt-supplier"
    aria-label={'Chọn phiếu: '+supplierLabel(doc)} aria-expanded={open}
    title={doc.file} onClick={()=>{setFilter('');setOpen(value=>!value)}}>
    <strong title={supplierLabel(doc)}>{supplierLabel(doc)}</strong><ChevronDown size={13}/>
   </button>
   <div className="receipt-inline-nav">
    <ReceiptNavButton label="Phiếu trước" icon={<ChevronLeft size={14}/>} disabled={busy||index===0} onClick={()=>{setOpen(false);onSelect(index-1)}}/>
    <span>{index+1}<small> / {receipts.length}</small></span>
    <ReceiptNavButton label="Phiếu sau" icon={<ChevronRight size={14}/>} disabled={busy||index===receipts.length-1} onClick={()=>{setOpen(false);onSelect(index+1)}}/>
   </div>
  </div>
  {open&&<div className="receipt-popover">
   <TextInput label="Tìm phiếu" isLabelHidden size="sm" value={filter} onChange={setFilter} placeholder="Tìm tên phiếu hoặc NCC…"/>
   {busy&&<p role="status">Đang cập nhật dữ liệu phiếu…</p>}
   {matches.length===0&&<p>Không tìm thấy phiếu.</p>}
   {matches.map(({receipt,index:matchIndex})=><button type="button" key={receipt.file}
    disabled={busy} aria-current={matchIndex===index?'true':undefined}
    onClick={()=>{setOpen(false);onSelect(matchIndex);trigger.current.focus()}}>
    <FileImage size={16}/><span><b>{supplierLabel(receipt)}</b><small>{receipt.file}</small></span>
    {matchIndex===index&&<Check size={14}/>}
   </button>)}
  </div>}
 </div>;
}

function App(){
 const [sidebarOpen,setSidebarOpen]=useState(false);
 const metadataActions=useRef(null),prCache=useRef(new Map());
 const [data,setData]=useState(null),[error,setError]=useState(''),[page,setPage]=useState('review'),[index,setIndex]=useState(0),[selected,setSelected]=useState(null),[metadataDraft,setMetadataDraft]=useState(null),[itemQuery,setItemQuery]=useState(''),[editing,setEditing]=useState(null),[rowSaving,setRowSaving]=useState(false),[expanded,setExpanded]=useState(false),[ratio,setRatio]=useState(50),[modal,setModal]=useState(''),[loadingDay,setLoadingDay]=useState(false),[saving,setSaving]=useState(false),[saveMessage,setSaveMessage]=useState('');
 const [picker,setPicker]=useState(false),[prBusy,setPrBusy]=useState(false),[prError,setPrError]=useState(''),[prRefresh,setPrRefresh]=useState(0),[unlinkConfirm,setUnlinkConfirm]=useState(false);
 const [unlinkConfirmed,showUnlinkSuccess]=useConfirmation();
 const [unreceivedOpen,setUnreceivedOpen]=useState(false),[deliveryOverviewOpen,setDeliveryOverviewOpen]=useState(false);
 const [exportBusy,setExportBusy]=useState(false);
 const [prAction,setPrAction]=useState(null),[prGroup,setPrGroup]=useState('');
 const [context,setContext]=useState(null),[command,setCommand]=useState(null),[pr,setPr]=useState(null);
 const rowSave=useRef(false),pendingSave=useRef(null),requestRef=useRef(null),splitRef=useRef(null),moving=useRef(false);const doc=data?.receipts[index];

 async function reload(requestedDay,refresh=false,target=null){
  if(pendingSave.current||rowSave.current){if(target)throw Error('Đang lưu phiếu. Chờ hoàn tất.');return;}
  if(typeof requestedDay!=='string')requestedDay=data?.dayId;
  requestRef.current?.abort();const controller=new AbortController();requestRef.current=controller;
  let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;controller.abort()},20000);
  setError('');setLoadingDay(true);
  try{const query=new URLSearchParams();if(requestedDay)query.set('day',requestedDay);if(refresh)query.set('refresh','1');const r=await fetch('/api/receipts?'+query,{cache:'no-store',signal:controller.signal});if(!r.ok){const failure=await r.json().catch(()=>({}));throw Error(failure.error||`Không tải được phiếu (mã ${r.status}).`)}const next=await r.json();if(controller.signal.aborted)return;const nextIndex=target?next.receipts.findIndex(d=>d.file===target.sheet):0;
   if(target&&(nextIndex<0||(target.version&&next.version!==target.version)))throw Error('Phiếu đã thay đổi. Tìm lại trước khi mở.');
   setData(next);setIndex(nextIndex);setSelected(null);setEditing(null);setItemQuery('');setSaveMessage('');setExpanded(false)}catch(e){if(target)throw Error(timedOut?'Tải phiếu quá lâu. Thử mở lại.':e.message||'Chưa mở được phiếu.');if(requestRef.current===controller){if(timedOut)setError('Server chưa trả dữ liệu sau 20 giây. Thử tải lại; dữ liệu đã mở vẫn được giữ.');else if(e.name!=='AbortError'){console.error('REC load day failed',e);setError((e.message||'Chưa đọc được ngày đã chọn.')+' Thử tải lại hoặc đóng rồi mở lại React REC.')}}}finally{clearTimeout(timeout);if(requestRef.current===controller)setLoadingDay(false)}
 }
 useEffect(()=>{reload()},[]);
 useEffect(()=>{
  const refresh=()=>{prCache.current.clear();setPrRefresh(value=>value+1);reload(data?.dayId,true)};
  window.addEventListener('rec-data-changed',refresh);
  return ()=>window.removeEventListener('rec-data-changed',refresh);
 },[data?.dayId]);
 useEffect(()=>{
  if(page!=='review'||!doc)return;
  const controller=new AbortController();
  const query=prQuery(data,doc);
  const cacheKey=query.toString()+'::'+prRefresh;
  if(prCache.current.has(cacheKey)){setPr(prCache.current.get(cacheKey));return}
  setPr({status:'loading', message:'Đang đọc liên kết PR…'});
  const start=setTimeout(()=>fetchPr(query,controller.signal).then(result=>{
   if(!controller.signal.aborted){if(prCache.current.size>30)prCache.current.clear();prCache.current.set(cacheKey,result);setPr(result);}
  }).catch(error=>{if(!controller.signal.aborted)setPr({status:'review',message:error.message})}),350);
  return ()=>{clearTimeout(start);controller.abort()};
 },[page,doc?.id,data?.version,prRefresh]);
 useEffect(()=>{
  if(!context)return;
  function close(event){
   if(event.type==='resize'||event.key==='Escape'||(event.type==='pointerdown'&&!event.target.closest('.receipt-context')))setContext(null);
  }
  window.addEventListener('pointerdown',close);
  window.addEventListener('keydown',close);
  window.addEventListener('resize',close);
  return ()=>{window.removeEventListener('pointerdown',close);window.removeEventListener('keydown',close);window.removeEventListener('resize',close)};
 },[context]);

 useEffect(()=>{function key(e){if(e.key==='Escape'){setExpanded(false)}}window.addEventListener('keydown',key);return ()=>window.removeEventListener('keydown',key)},[]);
 const changeDoc=useCallback(i=>{if(loadingDay||pendingSave.current||rowSave.current||i===index)return;setContext(null);setPr(null);setPrError('');setPicker(false);setUnlinkConfirm(false);setSaveMessage('');setIndex(i);setSelected(null);setEditing(null);setItemQuery('')},[index,loadingDay]);
 const receiptNavigation=useMemo(()=>data&&<ReceiptSelector key={data.dayId} receipts={data.receipts}
  index={index} onSelect={changeDoc} busy={loadingDay||saving||rowSaving}/>,
  [data?.dayId,data?.receipts,index,changeDoc,loadingDay,saving,rowSaving]);
 const toggleExpanded=useCallback(()=>setExpanded(value=>!value),[]);
 const draft=metadataDraft?.id===doc?.id ? metadataDraft?.values||{} : {};
 const visibleRows=useMemo(()=>{
  const terms=searchable(itemQuery).trim().split(/\s+/).filter(Boolean);
  return (doc?.rows||[]).map((row,index)=>({row,index})).filter(({row})=>{
   const haystack=searchable([row['Tên hàng trên phiếu (Ảnh)'],row['Tên vật tư chuẩn'],row['Tên chuẩn hệ thống'],row['Mã vật tư'],row['Đơn vị tính']].join(' '));
   return terms.every(term=>haystack.includes(term));
  });
 },[doc?.rows,itemQuery]);
 const summary=useMemo(()=>{if(!doc)return {sum:0,missing:0};return doc.rows.reduce((s,r)=>{const a=amount(r);return{sum:s.sum+(a??0),missing:s.missing+(a===null?1:0)}},{sum:0,missing:0})},[doc]);
 const inReceipts=receiptPages.some(([key])=>key===page);
 const inDirectory=directoryPages.some(([key])=>key===page);
 const mainPage=inReceipts?'review':inDirectory?'directory':page;
 const navigationBusy=saving||rowSaving||loadingDay||exportBusy||Boolean(editing);
 const showDate=Boolean(data?.dayId)&&(inReceipts||['overview','library','ledger','assistant'].includes(page));
 function split(value){setRatio(Math.max(35,Math.min(65,Math.round(value))))}
 if(!data)return <div className="loading"><ScanLine size={34}/><h1>REC Studio</h1><p>{error||'Đang đọc dữ liệu REC…'}</p>{error&&<Button label="Thử lại" onClick={reload}/>}</div>;

 const safeSelected=selected!==null&&doc?.rows[selected]?selected:null;
 metadataActions.current={saveMetadata,filterItems(value){
  if(rowSave.current)return;
  setItemQuery(value);setSelected(null);setEditing(null);
 }};
 function openContext(event,row,index){
  if(rowSave.current||pendingSave.current||loadingDay)return;
  setSelected(index);
  setPrGroup('');setContext({row,x:Math.max(4,Math.min(event.clientX,window.innerWidth-294)),y:Math.max(4,Math.min(event.clientY,window.innerHeight-184))});
 }
 async function applyCommand(fields,showSuccess){
  if(command.kind==='lookup'){
   await saveLine(command.row.sourceRow,{[itemCode]:fields.code});
   setCommand(null);
   return;
  }
  if(rowSave.current||pendingSave.current||loadingDay)throw new Error('Đang cập nhật phiếu. Thử lại sau.');
  rowSave.current=true;setRowSaving(true);
  try{
   const auth=await fetch('/api/ocr/status',{cache:'no-store'}).then(response=>response.json());
   const response=await fetch('/api/receipt/action',{method:'POST',
    headers:{'Content-Type':'application/json','X-REC-Token':auth.token},
    body:JSON.stringify({day:data.dayId,sheet:doc.file,version:data.version,action:command.kind,...fields})});
   const result=await response.json();
   if(!response.ok)throw new Error(result.error||'Chưa thực hiện được thao tác.');
   if(['vat','delete','merge'].includes(command.kind))await showSuccess();
   const updated=await fetch('/api/receipts?'+new URLSearchParams({day:data.dayId,refresh:'1'}),{cache:'no-store'});
   if(!updated.ok){setCommand(null);setError('Đã lưu thay đổi. Tải lại trang để xem dữ liệu mới.');return}
   const next=await updated.json();
   if(result.warning)setError(result.warning);
   setData(next);setIndex(Math.max(0,next.receipts.findIndex(r=>r.file===(result.sheet||doc.file))));
   setSaveMessage(command.kind==='delete'?'Đã xóa dòng.':'Đã cập nhật.');
   setSelected(null);setPr(null);setCommand(null);
   if(command.kind==='remove_receipt'){setItemQuery('');setExpanded(false);setSaveMessage('Đã gỡ phiếu nhập nhầm.')}
   if(command.kind==='capture_time')setSaveMessage('Đã lưu giờ chụp.')
  }finally{rowSave.current=false;setRowSaving(false)}
 }
 async function savePr(action){
  if(rowSave.current||pendingSave.current||loadingDay||!pr?.token)throw new Error('Đang cập nhật. Thử lại sau.');
  rowSave.current=true;setPrBusy(true);setPrError('');
  try{
   const auth=await fetch('/api/ocr/status',{cache:'no-store'}).then(response=>response.json());
   const response=await fetch('/api/receipt/pr',{method:'POST',
    headers:{'Content-Type':'application/json','X-REC-Token':auth.token},
    body:JSON.stringify({day:data.dayId,sheet:doc.file,version:data.version,token:pr.token,...action})});
   const result=await response.json();
   if(!response.ok)throw new Error(result.error||'Chưa lưu được đối chiếu.');
   if(result.preview)return result;
   if(action.action==='unlink')await showUnlinkSuccess();
   if(action.action!=='choose')setPicker(false);
   setUnlinkConfirm(false);
   if(action.action==='row_action'&&['stop_topup','reopen_topup'].includes(action.kind)){
    const query=prQuery(data,doc);
    prCache.current.clear();
    try{
     const updated=await fetchPr(query,AbortSignal.timeout(20000));
     prCache.current.set(query.toString()+'::'+prRefresh,updated);
     setPr(updated);
    }catch{
     setPrError('Đã lưu quyết định giao bù. Mở lại phiếu để cập nhật trạng thái.');
    }
   }else{
    setPrRefresh(value=>value+1);
   }
   if(result.warning)setPrError(result.warning);
   return result;
  }catch(error){
   setPrError(error.message);
   if(action.action!=='choose')setPicker(false);
   if(action.action==='row_action'||action.throwOnError)throw error;
  }finally{
   rowSave.current=false;setPrBusy(false);
  }
 }
 function selectLine(index){
  if(rowSave.current)return;
  setSelected(index);
 }
 function editLine(index,column=0){
  if(rowSave.current||pendingSave.current||loadingDay)return;
  setSelected(index);
  setEditing({row:doc.rows[index].sourceRow,column});
 }
 async function saveLine(row,changes){
  if(rowSave.current||pendingSave.current||loadingDay)throw new Error('Đang cập nhật phiếu. Thử lại sau.');
  rowSave.current=true;
  setRowSaving(true);
  let saved=false;
  try{
   const auth=await fetch('/api/ocr/status',{cache:'no-store'}).then(response=>response.json());
   const response=await fetch('/api/receipt/row',{method:'POST',
    headers:{'Content-Type':'application/json','X-REC-Token':auth.token},
    body:JSON.stringify({day:data.dayId,sheet:doc.file,version:data.version,row,changes})});
   const result=await response.json();
   if(!response.ok)throw new Error(result.error||'Chưa lưu được dòng hàng.');
   saved=true;
   const refreshed=await fetch('/api/receipts?day='+data.dayId+'&refresh=1',{cache:'no-store'});
   if(!refreshed.ok)throw new Error('Đã lưu dòng. Tải lại trang để xem dữ liệu mới.');
   setData(await refreshed.json());
   setSaveMessage('Đã cập nhật dòng.');
  }catch(error){
   if(saved){setEditing(null);setError('Đã lưu ô. Tải lại trang để xem dữ liệu mới.');throw error}
   throw error;
  }finally{
   rowSave.current=false;
   setRowSaving(false);
  }
 }
 async function saveMetadata(key,value){
  if(rowSave.current)return;
  const currentValue=key==='receiptTime'?(draft.receiptTime??doc.receiptTime??''):key==='supplierName'?(draft.supplierName??doc.supplier??''):(draft.warehouseCode??doc.warehouseCode);
  if(value===currentValue)return;
  setMetadataDraft(current=>({id:doc.id,values:{...current?.values,[key]:value}}));
  if(pendingSave.current){
   pendingSave.current.changes[key]=value;
   return;
  }
  const queue={changes:{[key]:value}};
  pendingSave.current=queue;
  let version=data.version;
  setSaving(true);setError('');setSaveMessage('');
  try{
   const auth=await fetch('/api/ocr/status',{cache:'no-store'}).then(r=>r.json());
   while(Object.keys(queue.changes).length){
    const changes=queue.changes;
    queue.changes={};
    const response=await fetch('/api/receipt/metadata',{method:'POST',headers:{'Content-Type':'application/json','X-REC-Token':auth.token},body:JSON.stringify({day:data.dayId,sheet:doc.file,version,changes})});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Chưa lưu được thông tin phiếu.');
    const refreshed=await fetch('/api/receipts?day='+data.dayId+'&refresh=1',{cache:'no-store'});
    if(!refreshed.ok)throw new Error('Đã lưu nhưng chưa tải lại được. Tải lại trang để xem dữ liệu mới.');
    const next=await refreshed.json();
    version=next.version;
    setData(next);
   }
   setSaveMessage('Đã lưu');
  }catch(e){setError(e.message);setSaveMessage('Chưa lưu xong')}
  finally{pendingSave.current=null;setMetadataDraft(null);setSaving(false)}
 }
 const contextPrRow=context&&pr?.status==='ready'?pr.rows?.[context.row.sourceRow]:null;
 const prQuickAction=contextPrRow?.topupAction?
  {key:contextPrRow.topupAction,label:contextPrRow.topupAction==='stop_topup'?'Ngừng giao bù…':'Tiếp tục giao bù…'}:
  contextPrRow?.prIndex!=null&&contextPrRow.status?.includes('Quy cách/dung lượng khác')?{key:'spec',label:'Rà quy cách…'}:null;
 return <div className="studio neutral">
 {modal==='review-receipt'&&<ReviewReceipt Modal={Modal} data={data} doc={doc} onClose={()=>setModal('')} onSaved={async()=>{const r=await fetch('/api/receipts?day='+data.dayId+'&refresh=1',{cache:'no-store'});if(!r.ok)throw Error('Đã lưu. Tải lại để cập nhật trạng thái.');setData(await r.json())}}/>}

 <a href="#work" className="skip">Đến vùng làm việc</a>
 <aside className={'workspace-sidebar '+(sidebarOpen?'is-open':'')} aria-label="Điều hướng chính">
  <div className="sidebar-brand"><span>REC</span>{sidebarOpen&&<strong>Nhận hàng</strong>}</div>
  <nav>{workspacePages.map(([id,label],i)=>{const Icon=workspaceIcons[i];return <button type="button" key={id} title={label} aria-label={label} aria-current={mainPage===id?'page':undefined} disabled={navigationBusy} onClick={()=>setPage(id)}><Icon size={19}/><span>{label}</span></button>})}</nav>
  <div className="sidebar-caption">{sidebarOpen?'Không gian làm việc':'REC'}</div>
 </aside>
 <div className="main-shell">
 <header className="app-header rec-workspace-header compact-header">
  <Tool label={sidebarOpen?'Thu gọn điều hướng':'Mở rộng điều hướng'} icon={<PanelLeft size={18}/>} onClick={()=>setSidebarOpen(v=>!v)}/>
  <div className="workspace-heading"><span>Không gian làm việc</span><strong>{workspacePages.find(([id])=>id===mainPage)?.[1]}</strong></div>
  {inReceipts&&<PageNavigation label="Phiếu giao" items={receiptPages} current={page} onChange={setPage}
   className="workspace-subtabs" disabled={navigationBusy}/>}
  {inDirectory&&<PageNavigation label="Danh mục" items={directoryPages} current={page} onChange={setPage}
   className="workspace-subtabs" disabled={navigationBusy}/>}
  {showDate&&<div className="calendar-picker header-calendar"><DateInput label="Ngày xem phiếu" isLabelHidden
   value={data.dayId} size="sm" presentation="popover" isDisabled={navigationBusy}
   format={iso=>iso.split('-').reverse().join('/')}
   onChange={iso=>{if(iso)reload(iso)}}/></div>}

 </header>
 <main id="work">

 {data.directoryWarning&&<div role="alert" className="error-banner">{data.directoryWarning}</div>}
 {error&&<div role="alert" className="error-banner">{error}</div>}
 {page==='history'?(data.dayId?<ReceiptHistory Modal={PageFrame} day={data.dayId}
  onClose={()=>setPage('review')} onOpen={item=>reload(item.day,false,item)}/>:
  <PageFrame title="Tra cứu nhiều ngày"><p>Chưa có phiếu để tra cứu.</p></PageFrame>):
  page==='export'?(data.dayId?<ExportReceipts key={data.dayId} Modal={PageFrame} data={data} onBusyChange={setExportBusy}/>:
   <PageFrame title="Xuất phiếu"><p>Chưa có phiếu để xuất.</p></PageFrame>):
  page==='assistant'?<RecAssistant key={data.dayId} day={data.dayId} dateLabel={data.day} navigate={setPage} navigationBusy={navigationBusy}/>:
  page==='review'?doc?<>

 <div className={'review-layout '+(loadingDay?'loading-day':'')} aria-busy={loadingDay} ref={splitRef} style={{'--image-part':ratio+'%'}}><Viewer receiptNavigation={receiptNavigation} doc={doc} prPages={pr?.prPages} prLabel={pr?.status==='ready'?pr.message:'Ảnh PR đã ghép'}

 expanded={expanded} onExpand={toggleExpanded}/><div role="separator" aria-label="Chia vùng ảnh và bảng" aria-orientation="vertical" aria-valuemin={35} aria-valuemax={65} aria-valuenow={ratio} tabIndex={0} className="resize" onPointerDown={e=>{moving.current=true;e.currentTarget.setPointerCapture(e.pointerId)}} onPointerMove={e=>{if(moving.current){const r=splitRef.current.getBoundingClientRect();split((e.clientX-r.left)/r.width*100)}}} onPointerUp={()=>moving.current=false} onPointerCancel={()=>moving.current=false} onLostPointerCapture={()=>moving.current=false} onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();split(e.key==='Home'?35:e.key==='End'?65:ratio+(e.key==='ArrowRight'?2:-2))}}}><GripVertical size={14}/></div>
 <section className="data-panel" inert={loadingDay} aria-label="Dữ liệu phiếu đang chọn"><ReceiptReviewSummary pr={pr} rows={doc.rows}/><ReceiptMetadata doc={doc} draft={metadataDraft?.id===doc.id?metadataDraft.values:null}
 departments={data.departments} itemQuery={itemQuery} rowSaving={rowSaving} actions={metadataActions}/>
 <SaveStatus busy={saving||rowSaving} message={saveMessage}/>
 <div className="receipt-pr-status">
  <div className="pr-toolbar">
   <CommandButton label="Tìm hàng" placeholder="Tên hoặc mã hàng…" shortcut="mod+j" width={190} onSearch={value=>metadataActions.current.filterItems(value)}/>
    <span role="status">{pr?.message||'Đang đọc liên kết PR…'}</span>
   {pr?.canChoose&&pr.status!=='no_po'&&<Button label={pr.linked?'Đổi PR':'Chọn PR'} size="sm" variant="secondary" isDisabled={prBusy} onClick={()=>setPicker(true)}/>}
   {pr?.linked&&pr.status!=='no_po'&&(unlinkConfirm?
    <ConfirmationButton label="Xác nhận bỏ ghép" successLabel="Đã bỏ ghép" busy={prBusy} confirmed={unlinkConfirmed}
     onClick={()=>savePr({action:'unlink'})}/>:
    <Button label="Bỏ ghép PR" size="sm" variant="ghost" isDisabled={prBusy} onClick={()=>setUnlinkConfirm(true)}/>)}
   {pr?.stale&&<Button label="Xóa ghép dòng cũ và rà lại" size="sm" variant="secondary" isDisabled={prBusy} onClick={()=>savePr({action:'reset'})}/>}




  </div>
  {prError&&<p className="error-banner" role="alert">{prError}</p>}
  {pr?.ledgerIssue&&<p role="status">{pr.ledgerIssue}</p>}
  {pr?.repair&&<PrAssignment key={pr.token} items={pr.prItems} rows={doc.rows} onSave={savePr}/>}
  {pr?.status==='ready'&&<div className="receipt-actions">
   <Button label="Đã giao / Chưa giao" size="sm" variant="secondary" onClick={()=>setDeliveryOverviewOpen(true)}/>
   <Button label="Xác nhận các món còn lại chưa giao" size="sm" variant="secondary"
    isDisabled={prBusy||!pr.pendingUnreceived?.length} onClick={()=>setUnreceivedOpen(true)}/>
  </div>}
  {pr?.unreceivedBlocked&&<p>{pr.unreceivedBlocked}</p>}
 </div>
 {picker&&<PrPicker linked={pr?.linked} busy={prBusy} day={data.dayId} sheet={doc.file} version={data.version} receiptPages={doc.pages}
  onSave={savePr} onClose={()=>setPicker(false)}/>}
<DataTable pr={pr} onPrSave={savePr} onContext={openContext} doc={doc}
 visibleRows={visibleRows}
 selected={safeSelected} onSelect={selectLine} editing={editing} onEdit={editLine} onSave={saveLine} onCancel={()=>setEditing(null)}/>

 <div className="total-row"><div><span>{summary.missing?'Tạm tính phần đủ dữ liệu':'Tổng theo thực nhận'}</span><small>{summary.missing?`${summary.missing} dòng chưa đủ lượng / giá`:'Đơn giá đang lưu trong REC'}</small></div><strong>{money(summary.sum)}<span>đ</span></strong></div>
 {(pr?.reviewBlockers?.length>0||pr?.status==='review')&&<div role="status">
  <strong>Cần xử lý trước khi xác nhận đã kiểm</strong>
  {pr.reviewBlockers?.length>0?<ul>{pr.reviewBlockers.map((reason,index)=><li key={index}>{reason}</li>)}</ul>:<p>{pr.message}</p>}
 </div>}
 <div className="data-footer"><span>{editing?'Enter: lưu và xuống dòng · Tab: sang ô · Esc: hủy':safeSelected===null?'Nhấp đúp vào ô để sửa':'Đã chọn dòng; định vị trên ảnh đang tắt để phản hồi nhanh.'}</span><div className="receipt-actions">
 <button type="button" className="remove-receipt-button"
  disabled={(doc.pages.length>0&&!doc.reviewToken)||navigationBusy||prBusy}
  onClick={()=>setCommand({kind:'remove_receipt'})}>Xóa phiếu</button>
 <Button label={doc.reviewed?'Bỏ xác nhận kiểm tra':'Xác nhận đã kiểm tra'} size="sm" variant={doc.reviewed?'secondary':'primary'} icon={<Check size={13}/>} onClick={()=>setModal('review-receipt')} isDisabled={saving||rowSaving||loadingDay||prBusy||(!doc.reviewed&&(!pr||pr.status==='loading'||pr.status==='review'||!!pr.reviewBlockers?.length))}/></div></div></section></div>
 </>:<section className="secondary-page"><p role="status">{saveMessage||`Ngày ${data.day} chưa có phiếu đã đọc.`}</p><Button label="Nhận phiếu" onClick={()=>setPage('intake')}/></section>:page==='knowledge'?<KnowledgePage/>:page==='intake'?<OcrPanel key={data.dayId} initialDay={data.dayId} onComplete={day=>{reload(day,true);setPage('review')}}/>:<BusinessPage key={page} page={page} data={data} navigate={setPage} Modal={Modal} navigationBusy={navigationBusy} onSelectDay={reload} openReceipt={async item=>{
  if(page==='overview'&&item.day===data.dayId&&item.version===data.version){
   const target=data.receipts.findIndex(receipt=>receipt.file===item.sheet);
   if(target>=0){changeDoc(target);setPage('review');return}
  }
  await reload(item.day,false,{sheet:item.sheet});setPage('review')
 }}/>}
 </main></div>
 {context&&page==='review'&&<RowContextMenu context={context} onClose={()=>setContext(null)}
  quickAction={prQuickAction}
  groups={[
  ...prMenuGroups.map(([group,entries])=>[group,entries
   .filter(([kind])=>kind!=='reopen_topup'||contextPrRow?.topupAction===kind)
   .map(([kind,label])=>({key:kind,label,receipt:kind==='vat',
    disabled:kind==='stop_topup'?contextPrRow?.topupAction!==kind:
     kind!=='vat'&&(pr?.status!=='ready'||(!['deposit','assign'].includes(kind)&&contextPrRow?.prIndex==null))}))]),
  ['Dòng trên phiếu giao',receiptCommands.filter(([kind])=>['lookup','delete','vat'].includes(kind)).map(([kind,label])=>({key:kind,label,receipt:true}))],
  ['Toàn phiếu giao',receiptCommands.filter(([kind])=>['no_po','nickname','merge','remove_receipt','capture_time','rotate_source','unreceived','opening'].includes(kind)).map(([kind,label])=>({key:kind,label,receipt:!['unreceived','opening'].includes(kind),disabled:kind==='remove_receipt'?doc.pages.length>0&&!doc.reviewToken:kind==='rotate_source'?!doc.reviewToken:['unreceived','opening'].includes(kind)&&pr?.status!=='ready'}))]
 ]} onAction={entry=>{if(entry.key==='unreceived')setUnreceivedOpen(true);else if(entry.receipt)setCommand({kind:entry.key,row:context.row});else setPrAction({kind:entry.key,index:pr?.rows?.[context.row.sourceRow]?.prIndex,row:context.row})}}/>}
 {deliveryOverviewOpen&&pr?.status==='ready'&&<Modal title="Tình trạng giao hàng" className="pr-dialog pr-dialog-wide" onClose={()=>setDeliveryOverviewOpen(false)}>
  <div className="receipt-command-body pr-delivery-overview">
   <p>{pr.message} · {doc.file}</p>
   <p role="status">{pr.posted===false?<><strong>Phiếu chưa ghi sổ.</strong> Google Sheets sẽ nhận số lượng sau khi phiếu được ghi sổ.</>:pr.posted===true?'Phiếu đã ghi sổ.':''}</p>
   {pr.priorCount>0&&<p>Cột Còn thiếu đã tính cả {pr.priorCount} lần giao trước.</p>}
   <div className="pr-delivery-table" role="region" aria-label="Số lượng theo món" tabIndex={0}>
   <table>
    <colgroup><col className="delivery-item-col"/><col span={4} className="delivery-quantity-col"/><col/></colgroup>
    <thead><tr><th scope="col">Món trên PR/PO</th><th scope="col">Đặt</th><th scope="col">Đã nhận trước</th><th scope="col">Nhận lần này</th><th scope="col">Còn thiếu</th><th scope="col">Tình trạng</th></tr></thead>
    <tbody>{pr.deliveryItems?.map(item=><tr key={item.index}>
     <th scope="row">{item.name}<small>{item.unit}</small></th>
     <td>{item.ordered==null?'—':money(item.ordered)}</td>
     <td>{item.previous==null?'—':money(item.previous)}</td>
     <td>{item.received!=null?money(item.received):item.reported!=null?<>{money(item.reported)}<small>{item.reportedUnit} trên phiếu</small></>:'—'}</td>
     <td>{item.remaining==null?'—':money(Math.max(0,item.remaining))}</td>
     <td><strong>{item.remaining===0?'Đã nhận đủ':item.state==='received'?'Đã giao lần này':item.previous>0?'Đã giao trước':item.state==='not_delivered'?'Chưa giao lần này':'Cần rà'}</strong>
      {item.status&&<small>{item.state==='review'&&item.previous>0?'Lần này cần rà. ':''}{item.status}</small>}
      {item.state==='not_delivered'&&item.previous>0&&<small>Không giao thêm lần này</small>}</td>
    </tr>)}</tbody>
   </table>
   </div>
   <PrAssignment key={pr.token} items={pr.prItems} rows={doc.rows} onSave={savePr}/>
  </div>
 </Modal>}
 {unreceivedOpen&&<UnreceivedDialog pr={pr} onClose={()=>setUnreceivedOpen(false)} onSave={savePr}/>}
 {prAction&&<PrActionDialog key={prAction.kind} action={prAction} doc={doc} pr={pr} onClose={()=>setPrAction(null)} onSave={savePr}/>}
 {command&&<ReceiptActions key={command.kind} action={command} doc={doc} receipts={data.receipts} onClose={()=>setCommand(null)} onApply={applyCommand}/>}

 </div>
}
createRoot(document.getElementById('root')).render(<Theme theme={neutralTheme} mode="light"><App/></Theme>);

