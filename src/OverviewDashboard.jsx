import React, {useRef, useState} from 'react';
import {ArrowRight, BookOpen, CheckCircle2, ClipboardList, FileText, Sheet, Upload} from 'lucide-react';
import {Button} from '@astryxdesign/core/Button';

const filters=[['work','Cần xử lý'],['pending','Chưa kiểm tra'],['reviewed','Đã kiểm tra'],['all','Tất cả']];
const ledgerStatuses=[
 ['Đã ghi sổ','posted'], ['Chưa ghi sổ','pending'],
 ['Cần kiểm tra lại','review'], ['Không có PR/PO','manual'],
];
const pageSize=8;
const activityTime=new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Ho_Chi_Minh'});

export default function OverviewDashboard({data,result,loading,error,onRetry,navigate,openReceipt,navigationBusy}) {
 const [filter,setFilter]=useState('work');
 const [limit,setLimit]=useState(pageSize);
 const [opening,setOpening]=useState('');
 const [openError,setOpenError]=useState('');
 const receiptHeading=useRef(null);
 const total=data.receipts.length;
 const reviewed=data.receipts.filter(receipt=>receipt.reviewed).length;
 const pending=total-reviewed;
 const percent=total?Math.round(reviewed/total*100):0;
 const attention=result?.attention||{};
 const needsWork=receipt=>!receipt.reviewed||Boolean(attention[receipt.file]);
 const receipts=data.receipts
  .filter(receipt=>filter==='all'||(filter==='work'?needsWork(receipt):Boolean(receipt.reviewed)===(filter==='reviewed')))
  .sort((a,b)=>Number(Boolean(attention[b.file]))-Number(Boolean(attention[a.file])));
 const filterCounts={work:data.receipts.filter(needsWork).length,pending,reviewed,all:total};
 const bySheet=new Map(data.receipts.map(receipt=>[receipt.file,receipt]));
 const activity=(result?.activity||[]).filter(event=>Number.isFinite(Date.parse(event.time))&&
  (event.kind!=='review'||bySheet.get(event.sheet)?.reviewed))
  .sort((a,b)=>Date.parse(b.time)-Date.parse(a.time)).slice(0,5);
 const metrics=[
  {key:'all',label:'Phiếu trong ngày',value:total,Icon:FileText},
  {key:'reviewed',label:'Đã kiểm tra',value:reviewed,Icon:CheckCircle2},
  {key:'pending',label:'Chưa kiểm tra',value:pending,Icon:ClipboardList},
  {key:'ledger',label:'Đã ghi sổ',value:result?.counts?.['Đã ghi sổ']??'—',Icon:BookOpen},
 ];
 function selectFilter(value) {
  setFilter(value);setLimit(pageSize);
 }
 async function open(receipt) {
  if(opening||navigationBusy)return;
  setOpening(receipt.file);setOpenError('');
  try{await openReceipt({day:data.dayId,sheet:receipt.file,version:data.version})}
  catch(failure){setOpenError(failure.message)}
  finally{setOpening('')}
 }
 return <>
  <header className="rec-overview-header">
   <div className="rec-overview-hero-main">
    <p>Ngày {data.day}</p>
    <h1>Tổng quan nhận hàng</h1>
    <div className="rec-overview-work-count"><strong>{filterCounts.work}</strong><span>Phiếu cần xử lý</span></div>
    <div className="rec-overview-hero-actions">
     {filterCounts.work>0&&<button type="button" className="rec-overview-review-action" disabled={navigationBusy}
      onClick={()=>{selectFilter('work');receiptHeading.current?.focus()}}>Xem phiếu cần xử lý <ArrowRight size={16}/></button>}
     <button type="button" className="rec-overview-intake-action" disabled={navigationBusy} onClick={()=>navigate('intake')}>
      <Upload size={16}/> Nhận phiếu
     </button>
    </div>
   </div>
   <section className="rec-overview-hero-progress" aria-labelledby="overview-progress">
    <div className="rec-overview-ring" style={{'--review-progress':`${percent}%`}} aria-hidden="true">
     <strong>{percent}%</strong>
    </div>
    <div><h2 id="overview-progress">Tiến độ kiểm phiếu</h2><p>{reviewed} / {total} phiếu đã kiểm tra</p></div>
   </section>
  </header>
  <div className="rec-overview-metrics" role="group" aria-label="Chỉ số trong ngày">
   {metrics.map(({key,label,value,Icon})=><button type="button" key={key}
    className={key==='pending'&&pending>0?'rec-overview-metric-pending':undefined}
    aria-controls={key==='ledger'?undefined:'overview-receipt-list'}
    aria-pressed={key==='ledger'?undefined:filter===key} disabled={navigationBusy}
    onClick={()=>key==='ledger'?navigate('ledger'):selectFilter(key)}>
    <span><Icon size={17}/>{label}<ArrowRight size={16}/></span><strong>{value}</strong>
   </button>)}
  </div>
  <div className="rec-overview-grid">
   <section id="overview-receipt-list" className="rec-overview-panel" aria-labelledby="overview-receipts">
    <header><h2 id="overview-receipts" ref={receiptHeading} tabIndex={-1}>{filter==='work'?'Phiếu cần xử lý':'Phiếu giao trong ngày'}</h2></header>
    <div className="rec-overview-filters" role="group" aria-label="Lọc tình trạng kiểm tra">
     {filters.map(([key,label])=><button type="button" key={key} aria-pressed={filter===key}
      onClick={()=>selectFilter(key)}>{label} <span>{filterCounts[key]}</span></button>)}
    </div>
    {openError&&<p className="error-banner" role="alert">{openError}</p>}
    {receipts.length>0?<ul className="rec-overview-receipts">
     {receipts.slice(0,limit).map(receipt=><li key={receipt.id}>
      <button type="button" data-attention={Boolean(attention[receipt.file])} onClick={()=>open(receipt)} disabled={navigationBusy||Boolean(opening)}>
       <span className="rec-overview-doc"><FileText size={17}/></span>
       <span className="rec-overview-receipt-name">
        <strong>{receipt.supplierNickname||receipt.supplier||'Chưa có nhà cung cấp'}</strong>
        <small>{receipt.file} · {receipt.rows.length} mặt hàng</small>
        {attention[receipt.file]&&<small className="rec-overview-reason">{attention[receipt.file]}</small>}
       </span>
       <span className="rec-overview-state" data-reviewed={Boolean(receipt.reviewed)}>
        {opening===receipt.file?'Đang mở…':receipt.reviewed?'Đã kiểm tra':'Chưa kiểm tra'}
       </span>
       <ArrowRight size={16}/>
      </button>
     </li>)}
    </ul>:<p className="rec-overview-empty">
     {!total?'Chưa có phiếu trong ngày này.':filter==='work'?'Không còn phiếu cần xử lý.':
      filter==='pending'?'Đã kiểm tra tất cả phiếu trong ngày.':'Chưa có phiếu nào được xác nhận kiểm tra.'}
    </p>}
    {receipts.length>limit&&<footer><Button label="Xem thêm phiếu" size="sm" variant="secondary" onClick={()=>setLimit(value=>value+pageSize)}/></footer>}
   </section>
   <aside className="rec-overview-aside" aria-label="Tiến độ và ghi sổ">
    <section className="rec-overview-panel rec-overview-ledger" aria-labelledby="overview-ledger">
     <header><h2 id="overview-ledger">Tình trạng ghi sổ</h2></header>
     {error?<div className="rec-overview-ledger-feedback"><p role="alert">{error}</p><Button label="Thử lại" size="sm" variant="secondary" onClick={onRetry}/></div>:
      !result?<p className="rec-overview-ledger-feedback" role="status">Đang tải trạng thái ghi sổ…</p>:
      <dl aria-busy={loading}>{ledgerStatuses.map(([label,tone])=><div key={label}>
       <dt><span data-tone={tone}/>{label}</dt><dd>{result.counts?.[label]??0}</dd>
      </div>)}</dl>}
     <div className="rec-overview-links">
      <Button label="Mở sổ nhận hàng" icon={<BookOpen size={15}/>} variant="secondary" isDisabled={navigationBusy} onClick={()=>navigate('ledger')}/>
      <Button label="Đồng bộ Sheets" icon={<Sheet size={15}/>} variant="ghost" isDisabled={navigationBusy} onClick={()=>navigate('sheets')}/>
     </div>
    </section>
    <section className="rec-overview-panel rec-overview-activity" aria-labelledby="overview-activity">
     <header><h2 id="overview-activity">Nhật ký gần đây</h2></header>
     {activity.length>0?<ul>{activity.map(event=><li key={event.kind+event.sheet+event.time}>
      <button type="button" disabled={navigationBusy||Boolean(opening)}
       onClick={()=>event.kind==='review'?open(bySheet.get(event.sheet)):navigate(event.sync?'sheets':'ledger')}>
       <span><strong>{event.kind==='review'?'Đã kiểm phiếu':'Đã ghi sổ'} · {event.sheet}</strong>
        <small>{activityTime.format(new Date(event.time))}
         {event.kind==='ledger'&&` · ${event.sync==='synced'?'Đã đồng bộ Sheets':event.retry?'Đồng bộ cần thử lại':'Chờ đồng bộ Sheets'}`}
        </small></span><ArrowRight size={15}/>
      </button>
     </li>)}</ul>:<p className="rec-overview-empty">{result?'Chưa có hoạt động được ghi nhận trong ngày này.':error?'Chưa tải được nhật ký.':'Đang tải nhật ký…'}</p>}
    </section>
   </aside>
  </div>
 </>;
}
