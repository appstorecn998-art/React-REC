import React, {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import ConfirmationButton, {useConfirmation} from './ConfirmationButton';
import {TextInput} from '@astryxdesign/core/TextInput';
import {ArrowRight, ClipboardList, History, Search, Sheet} from 'lucide-react';
import CommandButton from './CommandButton';
import OverviewDashboard from './OverviewDashboard';

export const businessPages = [
 ['overview','Tổng quan'], ['library','PR và kho'], ['ledger','Sổ nhận hàng'],
 ['debt','Công nợ'], ['prices','Giá và thuế'], ['sheets','Đồng bộ Sheets'],
 ['directory','Danh mục'], ['settings','Quản trị'],
];

async function read(url, options) {
 const response = await fetch(url, {cache:'no-store', ...options});
 const result = await response.json();
 if (!response.ok) throw Error(result.error || 'REC chưa tải được dữ liệu.');
 return result;
}

async function write(url, payload) {
 const {token} = await read('/api/ocr/status');
 return read(url, {method:'POST', headers:{'Content-Type':'application/json','X-REC-Token':token},
  body:JSON.stringify(payload)});
}

function Table({title, columns, rows, render}) {
 const [limit,setLimit] = useState(50);
 return rows.length ? <>
  <div className="business-table" tabIndex={0} role="region" aria-label={title}>
   <table>
    <caption>{title}</caption>
    <thead><tr>{columns.map(column=><th key={column} scope="col">{column}</th>)}</tr></thead>
    <tbody>{rows.slice(0,limit).map((row,index)=><tr key={row.id ?? index}>
     {render(row).map((cell,i)=><td key={i}>{cell ?? '—'}</td>)}
    </tr>)}</tbody>
   </table>
  </div>
  <div className="business-table-footer">
   <span>{Math.min(limit,rows.length)} / {rows.length} dòng</span>
   {rows.length>limit&&<Button label="Xem thêm" size="sm" variant="secondary" onClick={()=>setLimit(limit+50)}/>}
  </div>
 </> : <p className="business-empty">Không có dữ liệu phù hợp.</p>;
}

const searchText = value=>String(value??'').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase().replaceAll('đ','d');
const money = value=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(Number(value));
const syncTime = new Intl.DateTimeFormat('vi-VN',{
 dateStyle:'short',timeStyle:'short',timeZone:'Asia/Ho_Chi_Minh',
});

function SyncTimeline({events}) {
 const [limit,setLimit]=useState(50);
 return <>
  <ol className="sheets-timeline" role="list" aria-label="Sự kiện đồng bộ mới nhất trước">
   {events.slice(0,limit).map(event=>{
    const stamp=Date.parse(event.time);
    const status=event.state==='synced'?'Đã đồng bộ':event.error?'Cần thử lại':'Chờ đồng bộ';
    return <li key={event.id} data-state={event.state}>
     <time dateTime={Number.isFinite(stamp)?event.time:undefined}>
      {Number.isFinite(stamp)?syncTime.format(stamp):event.time}
     </time>
     <div className="sheets-event">
      <strong>{event.sheet}</strong>
      <span className="sheets-status" data-state={event.state}>{status}</span>
      {event.error&&<p>{event.error}</p>}
     </div>
    </li>;
   })}
  </ol>
  {events.length>limit&&<div className="business-table-footer">
   <span>{limit} / {events.length} mục</span>
   <Button label="Xem thêm" size="sm" variant="secondary" onClick={()=>setLimit(value=>value+50)}/>
  </div>}
 </>;
}

function DebtEditor({receipt, directory, close, run}) {
 const [code,setCode]=useState(receipt.supplier.code || '');
 const [reason,setReason]=useState('');
 const [alias,setAlias]=useState('');
 const [preview,setPreview]=useState(null);
 const [busy,setBusy]=useState(false);
 const [confirmed,showSuccess]=useConfirmation();
 async function submit(event) {
  event.preventDefault();
  setBusy(true);
  await run(async()=>{
   const next=await write('/api/debt/supplier',{id:receipt.id,version:receipt.version,code,reason,
    ...(alias ? {alias,previewToken:preview?.previewToken} : {})});
   if(next.saved){await showSuccess();close(true)}
   else setPreview(next);
  });
  setBusy(false);
 }
 return <form onSubmit={submit} className="business-form">
  <div className="pr-action-context business-form-context"><span>PHIẾU GIAO</span><strong>{receipt.sheet}</strong></div>
  <label>Nhà cung cấp<select required value={code} onChange={e=>{setCode(e.target.value);setPreview(null)}}>
   <option value="">Chọn mã NCC</option>{directory.map(item=><option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}
  </select></label>
  <TextInput label="Lý do" isRequired maxLength={500} value={reason} onChange={setReason} size="sm"/>
  <label>Phạm vi<select value={alias} onChange={e=>{setAlias(e.target.value);setPreview(null)}}>
   <option value="">Riêng phiếu này</option>{receipt.rawNames.map(name=><option key={name} value={name}>Bí danh · {name}</option>)}
  </select></label>
  {preview&&<details open><summary>{preview.affected.length} phiếu đổi mã NCC theo bí danh</summary>
   <ul>{preview.affected.map(row=><li key={row.id}>{row.day} · {row.sheet} · {row.proposedSupplier.name}</li>)}</ul>
  </details>}
  <div className="business-tools"><Button label="Hủy" variant="ghost" onClick={()=>close(false)} isDisabled={busy}/>
   <ConfirmationButton type="submit" label={alias&&!preview?'Xem trước ảnh hưởng':'Xác nhận NCC'} busy={busy} confirmed={confirmed}/></div>
 </form>;
}

function PRImages({record}) {
 const [result,setResult]=useState(null);
 const [error,setError]=useState('');
 function load() {
  setError('');setResult({pages:[]});
  read('/api/workspace/pr-images?'+new URLSearchParams({key:record.key}))
   .then(setResult).catch(error=>{setError(error.message);setResult(null)});
 }
 return <>
  <Button label="Mở ảnh PR" onClick={load} isDisabled={!!result}/>
  {error&&<p role="alert">{error}</p>}
  <div className="business-pr-images">{result?.pages.map((url,index)=>
   <a key={url} href={url} target="_blank" rel="noreferrer">
    <img src={url} alt={`Trang ${index+1} của PR`} loading="lazy"/>
   </a>)}</div>
 </>;
}

export default function BusinessPage({page, data, navigate, openReceipt, onSelectDay, Modal, navigationBusy}) {
 const [month,setMonth]=useState((data.dayId||'').slice(0,7));
 const [query,setQuery]=useState('');
 const [tab,setTab]=useState('');
 const [result,setResult]=useState(null);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [loading,setLoading]=useState(page==='sheets');
 const [revision,setRevision]=useState(0);
 const [selected,setSelected]=useState(null);
 const [confirm,setConfirm]=useState(false);
 const [ledgerPlan,setLedgerPlan]=useState(null);
 const [confirmed,showSuccess]=useConfirmation();
 const [ledgerResult,setLedgerResult]=useState(null);
 const [itemDecision,setItemDecision]=useState(null);
 const [syncHistory,setSyncHistory]=useState(null);
 const title=businessPages.find(([key])=>key===page)?.[1];
 const endpoint=page==='debt'?'/api/debt/suppliers':'/api/workspace/'+page;
 const period=page==='debt'||page==='prices';
 const day=data.dayId;
 const hasSearch=['library','directory','ledger','debt','prices'].includes(page);
 const showingSyncHistory=page==='sheets'&&tab==='history';
 useEffect(()=>{
  const controller=new AbortController();
  const params=period?{month}:page==='overview'?{day}:{};
  const url=showingSyncHistory?'/api/workspace/sync-history':endpoint+'?'+new URLSearchParams(params);
  setLoading(true);setError('');
  if(showingSyncHistory)setSyncHistory(null);
  else if(page!=='ledger')setResult(null);
  read(url,{signal:controller.signal})
   .then(value=>{
    if(controller.signal.aborted)return;
    if(showingSyncHistory)setSyncHistory(value.events);
    else setResult(page==='overview'?{...value,day}:value);
   })
   .catch(error=>{if(!controller.signal.aborted)setError(error.message)})
   .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
  return ()=>controller.abort();
 },[page,endpoint,month,day,period,revision,showingSyncHistory]);
 useEffect(()=>{
  const refresh=()=>{
   setSelected(null);setItemDecision(null);setLedgerPlan(null);setConfirm(false);setSyncHistory(null);
   if(page==='sheets')setResult(null);
   setRevision(value=>value+1);
  };
  window.addEventListener('rec-data-changed',refresh);
  return ()=>window.removeEventListener('rec-data-changed',refresh);
 },[page]);

 async function run(task) {
  setError('');
  try {await task()} catch(error) {setError(error.message)}
 }
 function search(rows,pick) {
  const terms=searchText(query).trim().split(/\s+/).filter(Boolean);
  return rows.filter(row=>terms.every(term=>searchText(pick(row)).includes(term)));
 }
 function receiptLink(row) {
  return <button type="button" className="business-link" onClick={()=>run(()=>openReceipt(row))}>{row.sheet}</button>;
 }
 function selectTabs(options) {
  const active=tab||options[0][0];
  return <div className="business-sections" role="group" aria-label={title}>
   {options.map(([key,label])=><button type="button" key={key} aria-pressed={active===key}
    onClick={()=>{setTab(key);setQuery('')}}>{label}</button>)}
  </div>;
 }

 if(page==='overview')return <section className="secondary-page rec-overview">
  <OverviewDashboard key={day} data={data} result={result?.day===day?result:null} loading={loading}
   error={error} onRetry={()=>setRevision(value=>value+1)} navigate={navigate} openReceipt={openReceipt}
   navigationBusy={navigationBusy}/>
 </section>;

 const ledgerGroups=page==='ledger'&&result?[
  ['all','Tất cả phiếu',result.receipts],
  ['shortages','Chờ giao bù',result.lines.filter(row=>row.status==='Còn thiếu')],
  ['sources','Nguồn cần rà',result.lines.filter(row=>row.remaining===null)],
  ['stopped','Đã ngừng giao bù',result.lines.filter(row=>row.item_stopped&&row.remaining!==null)],
 ]:null;
 const ledgerGroup=ledgerGroups?.find(([key])=>key===(tab||'all'));
 const lastUnpostedDay=page==='ledger'&&!data.receipts.length?
  result?.receipts.find(row=>row.status==='Chưa ghi sổ')?.day:null;

 return <section className={'secondary-page business-page'+(page==='sheets'?' sheets-page':page==='ledger'?' ledger-page':'')}>
  {page!=='sheets'&&page!=='ledger'&&<header className="business-header">
   <h1>{title}</h1>
   {(period||hasSearch)&&<div className="business-filters">
    {period&&<label className="business-month">Tháng theo dõi
     <input type="month" value={month} onChange={event=>{if(event.target.value)setMonth(event.target.value)}}/>
    </label>}
    {hasSearch&&<CommandButton label="Tìm kiếm" placeholder="Nhập từ khóa…" shortcut="mod+f" width={270} onSearch={setQuery}/>}
   </div>}
  </header>}
  {page==='ledger'&&<><header className="ledger-header">
   <div>
    <h1>{title}</h1>
    <p>Ghi nhận phiếu đã kiểm tra và theo dõi lượng hàng còn thiếu theo PR.</p>
   </div>
  </header>
   <section className="ledger-post" aria-label="Ghi sổ theo ngày">
    <Button label={'Ghi sổ'+(data.day?' ngày '+data.day:'')} variant="primary" icon={<ClipboardList size={17}/>}
     isDisabled={loading||navigationBusy||!data.dayId||!data.receipts.length} onClick={()=>{
      setLoading(true);
      run(async()=>{
       setLedgerResult(null);
       const plan=await write(endpoint,{action:'post_day',day});
       setLedgerPlan({...plan,day});
      })
       .finally(()=>setLoading(false));
     }}/>
    {data.receipts.length?
     <p>Xem danh sách phiếu đủ điều kiện trước khi xác nhận ghi sổ.</p>:
     <p>Ngày đang chọn chưa có phiếu. Chọn ngày của phiếu ở góc trên bên phải.</p>}
    {lastUnpostedDay&&<Button label={'Chọn ngày '+lastUnpostedDay.split('-').reverse().join('/')}
     variant="secondary" isDisabled={loading||navigationBusy} onClick={()=>onSelectDay(lastUnpostedDay)}/>}
   </section>
  </>}
  {page!=='sheets'&&loading&&<p role="status">Đang tải dữ liệu REC…</p>}
  {page!=='sheets'&&error&&<p className="error-banner" role="alert">{error}</p>}
  {page!=='sheets'&&notice&&<p role="status">{notice}</p>}
  {page==='directory'&&result&&<>
   {selectTabs([['items','Hàng hóa'],['warehouses','Kho'],['suppliers','Nhà cung cấp']])}
   <Table key={tab} title={title} columns={['Mã','Tên',tab==='warehouses'?'Bộ phận':'Đơn vị']}
    rows={search(result[tab||'items'],row=>[row.code,row.name,row.department].join(' '))}
    render={row=>[row.code,row.name,tab==='warehouses'?row.department:row.unit]}/>
  </>}
  {page==='library'&&result&&<Table title={title} columns={['PR','Mặt hàng','Trạng thái']}
   rows={search(result.items,row=>[row.title,row.supplier_code,row.related_pr_number,...row.items.map(item=>item.item_name)].join(' '))}
   render={row=>[<button type="button" className="business-link" onClick={()=>setSelected(row)}>{row.title}</button>,row.count,
    <>{row.status}{row.warnings?.length>0&&<div>{row.warnings.length} mục cần đối chiếu danh mục</div>}</>]}/>}
  {page==='library'&&selected&&<Modal className="pr-dialog business-dialog" title={selected.title} onClose={()=>setSelected(null)}>
   <PRImages record={selected}/>
   {selected.supplier_code&&<p>Mã NCC · {selected.supplier_code}</p>}
   {selected.warnings?.length>0&&<section className="error-banner" aria-label="Chênh lệch danh mục">
    <strong>Cần đối chiếu danh mục</strong>
    <ul>{selected.warnings.map((warning,index)=><li key={index}>{warning}</li>)}</ul>
   </section>}
   <form className="business-form" onSubmit={event=>{
    event.preventDefault();
    const changes=Object.fromEntries(new FormData(event.currentTarget));
    setLoading(true);
    run(async()=>{await write(endpoint,{key:selected.key,version:selected.version,changes});
     setSelected(null);setNotice('Đã lưu thông tin PR.');setRevision(v=>v+1)})
     .finally(()=>setLoading(false));
   }}>
    {Object.entries({number:selected.order_type==='po'?'Số PO':'Số PR',supplier:'Nhà cung cấp',date:'Ngày chứng từ',department:'Bộ phận'}).map(([key,label])=>
     <label key={key}>{label}<input name={key} maxLength={200} defaultValue={selected[key]||''}
      disabled={key==='supplier'&&selected.order_type==='po'}/></label>)}
    <Button type="submit" label="Lưu thông tin PR" isDisabled={loading}/>
   </form>
   {data.receipts.length>0&&<form className="business-form" onSubmit={event=>{
    event.preventDefault();
    const sheet=new FormData(event.currentTarget).get('sheet');
    const query=new URLSearchParams({day:data.dayId,sheet,version:data.version});
    setLoading(true);
    run(async()=>{
     const status=await read('/api/receipt/pr?'+query);
     if(!status.canChoose||!status.token)throw Error(status.message||'Phiếu chưa sẵn sàng để ghép PR.');
     await write('/api/receipt/pr',{day:data.dayId,sheet,version:data.version,token:status.token,action:'choose',key:selected.key});
     await openReceipt({day:data.dayId,sheet});
    }).finally(()=>setLoading(false));
   }}>
    <label>Phiếu giao ngày {data.day}<select name="sheet" required defaultValue="">
     <option value="" disabled>Chọn phiếu</option>{data.receipts.map(row=>
      <option key={row.file} value={row.file}>{row.file} · {row.supplier}</option>)}
    </select></label>
    <Button type="submit" label="Ghép PR vào phiếu" isDisabled={loading}/>
   </form>}
   {error&&<p role="alert">{error}</p>}
   <Table title="Chi tiết PR/PO" columns={['Mã hàng','Mặt hàng','ĐVT','SL đặt','Đơn giá']} rows={selected.items}
    render={item=>[item.catalog_code,item.item_name,item.unit,item.quantity,item.unit_price]}/>
  </Modal>}
  {page==='ledger'&&ledgerPlan?.day===day&&ledgerPlan&&
   <Modal className="pr-dialog business-dialog" title={'Ghi sổ ngày '+data.day} onClose={()=>{if(!loading)setLedgerPlan(null)}}>
    <p>{ledgerPlan.ready?ledgerPlan.ready+' phiếu sẵn sàng ghi sổ.':'Chưa có phiếu đủ điều kiện. Xem lý do trong cột Chi tiết.'}</p>
    <Table title="Kiểm tra trước khi ghi sổ" columns={['Phiếu','Trạng thái','Chi tiết']}
     rows={ledgerPlan.entries} render={row=>[row.sheet,row.status,row.reason]}/>
    <div className="business-tools">
     <button type="button" autoFocus disabled={loading} onClick={()=>setLedgerPlan(null)}>Hủy</button>
     <ConfirmationButton label="Xác nhận ghi sổ" successLabel="Đã xử lý" busy={loading} confirmed={confirmed} isDisabled={!ledgerPlan.ready} onClick={()=>{
      setLoading(true);
     run(async()=>{const saved=await write(endpoint,{action:'post_day',day:ledgerPlan.day,token:ledgerPlan.token});
       if(saved.results.length>0&&saved.results.every(row=>row[1]==='Đã ghi sổ'))await showSuccess();
       setLedgerResult(saved.results);setLedgerPlan(null);setRevision(v=>v+1)})
       .finally(()=>setLoading(false));
     }}/>
    </div>
    {error&&<p role="alert">{error}</p>}
   </Modal>}
  {page==='ledger'&&result&&<>
   {ledgerResult&&<>
    <Table title="Kết quả ghi sổ" columns={['Phiếu','Kết quả','Chi tiết']}
     rows={ledgerResult} render={row=>row}/>
    <Button label="Xem trước hàng thiếu trên Google Sheets" variant="secondary" onClick={()=>navigate('sheets')}/>
   </>}
   {selected&&<Modal className="pr-dialog business-dialog" title={'Thu hồi lần nhận · '+selected.sheet} onClose={()=>{if(!loading)setSelected(null)}}>
    <form className="business-form" onSubmit={event=>{
     event.preventDefault();
     const reason=new FormData(event.currentTarget).get('reason');
     setLoading(true);
     run(async()=>{await write(endpoint,{action:'revoke',receipt:selected.receipt_id,revision:selected.revision,reason});
      await showSuccess();setSelected(null);setNotice('Đã thu hồi lần nhận.');setRevision(v=>v+1)})
      .finally(()=>setLoading(false));
    }}>
     <label>Lý do thu hồi<input name="reason" required maxLength={500}/></label>
     <button type="button" autoFocus disabled={loading} onClick={()=>setSelected(null)}>Hủy</button>
     <ConfirmationButton type="submit" label="Xác nhận thu hồi" successLabel="Đã thu hồi" busy={loading} confirmed={confirmed}/>
    </form>
    {error&&<p role="alert">{error}</p>}
   </Modal>}
   {itemDecision&&<Modal className="pr-dialog business-dialog" title={(itemDecision.item_stopped?'Mở lại giao bù':'Ngừng giao bù')+' · '+itemDecision.name}
    onClose={()=>{if(!loading)setItemDecision(null)}}>
    <form className="business-form" onSubmit={event=>{
     event.preventDefault();
     const reason=new FormData(event.currentTarget).get('reason');
     const row=itemDecision;
     setLoading(true);
     run(async()=>{await write(endpoint,{action:row.item_stopped?'reopen_item':'stop_item',
      order:row.order_id,index:row.index,version:row.version,reason});
      await showSuccess();setItemDecision(null);setNotice('Đã lưu quyết định giao bù.');setRevision(v=>v+1)})
      .finally(()=>setLoading(false));
    }}>
     <label>Người xác nhận và lý do<input name="reason" required maxLength={500}/></label>
     <button type="button" autoFocus disabled={loading} onClick={()=>setItemDecision(null)}>Hủy</button>
     <ConfirmationButton type="submit" label="Xác nhận" successLabel="Đã lưu" busy={loading} confirmed={confirmed}/>
    </form>
    {error&&<p role="alert">{error}</p>}
   </Modal>}
   <div className="ledger-groups" role="group" aria-label="Nhóm theo dõi sổ nhận hàng">
    {ledgerGroups.map(([key,label,rows])=><button type="button" key={key} aria-pressed={ledgerGroup[0]===key}
     onClick={()=>setTab(key)}><strong>{rows.length}</strong><span>{label}</span></button>)}
   </div>
   <section className="ledger-register" aria-labelledby="ledger-group-title" aria-busy={loading}>
    <div className="ledger-register-heading">
     <div>
      <h2 id="ledger-group-title">{ledgerGroup[1]}</h2>
      {tab==='shortages'&&<p>Hàng còn thiếu theo sổ đã xác minh. Xem Nguồn cần rà để tìm các món đang chờ xác minh lại.</p>}
      {tab==='sources'&&<p>Nguồn phiếu đã đổi hoặc đã bỏ xác nhận. Cần kiểm tra phiếu và ghi sổ lại để tính số còn thiếu.</p>}
      {tab==='stopped'&&<p>Số lượng chưa nhận tại thời điểm ngừng theo dõi giao bù.</p>}
     </div>
     <CommandButton label="Tìm trong sổ" placeholder="Tên, mã hàng, PR hoặc phiếu…" shortcut="mod+f" width={270} onSearch={setQuery}/>
    </div>
    {tab==='sources'?
     <Table key={tab} title={ledgerGroup[1]} columns={['PR','Mặt hàng','ĐVT','SL đặt','Đã ghi nhận','Trạng thái']}
      rows={search(ledgerGroup[2],row=>[row.title,row.name,row.code].join(' '))}
      render={row=>[row.title,row.name,row.unit,row.ordered,row.recorded_received,
       <span className="ledger-status ledger-attention">{row.status}</span>]}/>:
     ['shortages','stopped'].includes(tab)?
      <Table key={tab} title={ledgerGroup[1]} columns={['PR','Mặt hàng','ĐVT','Đã nhận','Còn thiếu','Thao tác']}
       rows={search(ledgerGroup[2],row=>[row.title,row.name,row.code].join(' '))}
       render={row=>[row.title,row.name,row.unit,row.received,
        <strong className="ledger-quantity">{row.item_stopped?row.physical_remaining:row.remaining}</strong>,
        <button type="button" className="business-link" disabled={loading}
         onClick={()=>{setError('');setItemDecision(row)}}>{row.item_stopped?'Mở lại…':'Ngừng giao bù…'}</button>]}/>:
      <Table key="register" title={ledgerGroup[1]} columns={['Ngày','Phiếu','Nhà cung cấp','Dòng','Trạng thái','Thao tác']}
       rows={search(ledgerGroup[2],row=>[row.day,row.sheet,row.supplier,row.status].join(' '))}
       render={row=>[row.day,receiptLink(row),row.supplier,row.count,
        <span className={'ledger-status'+(row.status==='Cần kiểm tra lại'?' ledger-attention':'')}>{row.status}</span>,
        row.receipt_id?<button type="button" className="business-link" disabled={loading}
         onClick={()=>{setError('');setSelected(row)}}>Thu hồi…</button>:null]}/>}
   </section>
  </>}
  {page==='debt'&&result&&<>
   {selected&&<DebtEditor key={selected.id} receipt={selected} directory={result.directory} run={run}
    close={saved=>{setSelected(null);if(saved)setRevision(value=>value+1)}}/>}
   <p>Rà phiếu theo nhà cung cấp và tháng. Số tiền tạm tính bằng số lượng thực nhận nhân đơn giá trên phiếu. Bấm tên nhà cung cấp để xem từng phiếu.</p>
   <Table title="Giá trị phiếu theo nhà cung cấp" columns={['Mã NCC','Nhà cung cấp','Phiếu','Giá trị tạm tính','Dòng thiếu SL nhận hoặc đơn giá']}
    rows={search(result.suppliers,group=>[group.code,group.name].join(' '))}
    render={group=>[group.code,<details><summary>{group.name}</summary>
     <ul>{group.receipts.map(row=><li key={row.id}>{row.day} · {receiptLink(row)} · {money(row.provisional)} đ
      {' '}<button type="button" className="business-link" onClick={()=>setSelected(row)}>Xác nhận NCC</button></li>)}</ul>
    </details>,group.receipts.length,money(group.provisional)+' đ',group.missingRows]}/>
  </>}
  {page==='prices'&&result&&<>
   {result.errors.length>0&&<details><summary>{result.errors.length} báo cáo chưa đọc được</summary>
    <ul>{result.errors.map(message=><li key={message}>{message}</li>)}</ul></details>}
   <p>{result.warnings.length} nhóm hàng đổi giá từ hai lần · {result.excluded} dòng ngoài phạm vi so sánh</p>
   {result.pr_errors.length>0&&<details><summary>{result.pr_errors.length} thông tin PR cần rà</summary>
    <ul>{result.pr_errors.map(message=><li key={message}>{message}</li>)}</ul></details>}
   {selected&&<Modal className="pr-dialog business-dialog" title={'Số PR tham chiếu · '+selected.sheet} onClose={()=>{if(!loading)setSelected(null)}}>
    <form className="business-form" onSubmit={event=>{
     event.preventDefault();
     const number=new FormData(event.currentTarget).get('number');
     setLoading(true);
     run(async()=>{
      await write(endpoint,{day:selected.day,sheet:selected.sheet,signature:selected.source_signature,
       previous:selected.manual_pr||'',number});
      setSelected(null);setNotice('Đã lưu số PR tham chiếu.');setRevision(v=>v+1);
     }).finally(()=>setLoading(false));
    }}>
     <label>Số PR<input autoFocus name="number" maxLength={200} defaultValue={selected.manual_pr||(selected.pr_numbers||[]).join(', ')}/></label>
     <Button type="submit" label="Lưu số PR" isDisabled={loading}/>
    </form>
    {error&&<p role="alert">{error}</p>}
   </Modal>}
   <Table title="Biến động giá" columns={['Mã','Mặt hàng','ĐVT','Số lần đổi','Đơn giá']}
    rows={search(result.warnings,row=>[row.code,row.name].join(' '))}
    render={row=>[row.code,<details><summary>{row.name}</summary>
     <ul>{row.entries.map(item=><li key={item.day+item.sheet+item.row}>{item.day} · {receiptLink(item)} · {item.supplier} · {money(item.price)} đ
      {' '}<button type="button" className="business-link" onClick={()=>setSelected(item)}>
       {item.manual_pr||(item.pr_numbers||[]).join(', ')||'Nhập số PR…'}
      </button></li>)}</ul>
    </details>,row.unit,row.changes,row.prices.map(money).join(' / ')]}/>
  </>}
  {page==='settings'&&result&&<>
   {location.protocol==='rec:'&&<Button label="Mở công cụ REC cũ" variant="secondary" onClick={()=>
    run(async()=>{await read('/__desktop/legacy?'+new URLSearchParams({day:data.dayId||''}))})}/>}
   <Table title="Chẩn đoán trên máy" columns={['Thành phần','Trạng thái']} rows={Object.entries(result.checks)}
    render={([key,check])=>[({catalog:'Danh mục',gemini:'Gemini',sheets:'Google Sheets',template:'Mẫu xuất phiếu',ocr:'Model OCR',writable:'Quyền ghi'})[key]||key,
     check.message||(check.ok?'Sẵn sàng':'Cần kiểm tra')]}/>
   {[[ 'gemini','Khóa Gemini mới'],['sheetId','Mã Google Sheets mới']].map(([key,label])=>
    <form key={key} className="business-form" onSubmit={event=>{
     event.preventDefault();
     const form=event.currentTarget;
     const value=new FormData(form).get(key);
     setLoading(true);
     run(async()=>{await write(endpoint,{[key]:value});form.reset();setNotice('Đã lưu cấu hình.');setRevision(v=>v+1)})
      .finally(()=>setLoading(false));
    }}>
     <label>{label}<input type="password" name={key} required maxLength={200} autoComplete="off"/></label>
     <Button label="Lưu" type="submit" isDisabled={loading}/>
    </form>)}
   {[['catalog','DanhMuc.xlsm','.xlsm'],['google','Khóa Google Sheets','.json']].map(([kind,label,accept])=>
    <form key={kind} className="business-form" onSubmit={event=>{
     event.preventDefault();
     const form=event.currentTarget;
     const selectedFile=new FormData(form).get('file');
     setLoading(true);
     run(async()=>{
      if(!selectedFile.size||selectedFile.size>30_000_000)throw Error('Chọn tệp nhỏ hơn 30 MB.');
      const file=await new Promise((resolve,reject)=>{
       const reader=new FileReader();
       reader.onload=()=>resolve(reader.result.split(',')[1]);
       reader.onerror=()=>reject(Error('Không đọc được tệp.'));
       reader.readAsDataURL(selectedFile);
      });
      await write(endpoint,{kind,file});
      form.reset();setNotice('Đã nhập tệp cấu hình.');setRevision(v=>v+1);
     }).finally(()=>setLoading(false));
    }}>
     <label>{label}<input type="file" name="file" accept={accept} required/></label>
     <Button type="submit" label="Nhập tệp" isDisabled={loading}/>
    </form>)}
  </>}
  {page==='sheets'&&<>
   <header className="sheets-header">
    <div>
     <h1>{title}</h1>
     <p>Đối chiếu hàng còn thiếu đã ghi sổ với danh sách theo dõi trên Google Sheets.</p>
    </div>
    <div className="sheets-source">
     <span><ClipboardList size={17} aria-hidden="true"/> Sổ nhận hàng</span>
     <ArrowRight size={16} aria-hidden="true"/>
     <span><Sheet size={17} aria-hidden="true"/> Google Sheets</span>
    </div>
   </header>
   <div className="sheets-nav" role="group" aria-label="Nội dung đồng bộ">
    <button type="button" aria-pressed={!showingSyncHistory} disabled={confirm} onClick={()=>setTab('preview')}>
     <Sheet size={16} aria-hidden="true"/> Xem trước</button>
    <button type="button" aria-pressed={showingSyncHistory} disabled={confirm} onClick={()=>setTab('history')}>
     <History size={16} aria-hidden="true"/> Lịch sử đồng bộ</button>
   </div>
   {error&&!confirm&&<p className="error-banner" role="alert">{error}</p>}
   {notice&&<p className="sheets-notice" role="status">{notice}</p>}
   {showingSyncHistory?<section className="sheets-panel" aria-labelledby="sheets-history-title" aria-busy={loading}>
    <h2 id="sheets-history-title">Lịch sử đồng bộ</h2>
    {loading?<p role="status">Đang tải lịch sử…</p>:syncHistory?.length?
     <SyncTimeline events={syncHistory}/>:
     !error&&<p>Chưa có phiếu nào được đưa vào hàng đợi đồng bộ.</p>}
   </section>:<section className="sheets-panel" aria-labelledby="sheets-preview-title" aria-busy={loading}>
    <div className="sheets-panel-heading">
     <div>
      <h2 id="sheets-preview-title">Thay đổi dự kiến</h2>
      {result&&!result.historyReview&&(result.changeCount>0||result.newTabs.length>0)&&
       <p>Rà các dòng bên dưới, rồi bấm Cập nhật Google Sheets để mở bước xác nhận.</p>}
     </div>
     <div className="business-tools">
      {!loading&&<Button label={error?'Thử tải lại':'Tải lại bản xem trước'} variant="secondary"
       onClick={()=>setRevision(value=>value+1)}/>}
      {result&&!result.historyReview&&(result.changeCount>0||result.newTabs.length>0)&&
       <Button label="Cập nhật Google Sheets…" isDisabled={loading} onClick={()=>setConfirm(true)}/>}
     </div>
    </div>
    {loading&&!confirm&&<p role="status">Đang đối chiếu với Google Sheets…</p>}
    {result&&<>
     <dl className="sheets-metrics">
      <div><dt>Dòng thay đổi</dt><dd>{result.changeCount}</dd></div>
      <div><dt>Tab sẽ tạo</dt><dd>{result.newTabs.length}</dd></div>
      <div><dt>Dòng chưa đủ điều kiện</dt><dd>{result.skipped}</dd></div>
     </dl>
     {result.newTabs.length>0&&<p><strong>Tab sẽ tạo</strong> · {result.newTabs.join(', ')}</p>}
     {result.historyReview&&<p className="sheets-warning" role="status">Còn dòng cần xác minh lịch sử trước khi cập nhật.</p>}
     {result.departmentIssues?.length>0&&<section className="sheets-issues">
      <h3>Hàng thiếu cần rà bộ phận</h3>
      <Table title="Hàng thiếu cần rà bộ phận" columns={['Mặt hàng','Lý do']}
       rows={result.departmentIssues} render={row=>[row.name,row.reason]}/>
     </section>}
     {result.changes.length>0?
      <Table title="Xem trước đồng bộ" columns={['Tab','NCC','Mặt hàng','Thiếu trước','Thiếu sau','Thao tác']}
       rows={result.changes} render={row=>[row.tab,row.supplier,row.name,row.old?.[8],row.delete?0:row.values[8],
        <span className="sheets-status" data-state={row.delete?'remove':undefined}>{row.action}</span>]}/>:
      <p>Không có dòng nào cần cập nhật.</p>}
    </>}
   </section>}
   {confirm&&result&&<Modal className="pr-dialog business-dialog" title="Xác nhận cập nhật Google Sheets" onClose={()=>{if(!loading)setConfirm(false)}}>
    <p>Áp dụng {result.changeCount} thay đổi và tạo {result.newTabs.length} tab mới trên Google Sheets?</p>
    {error&&<p role="alert">{error}</p>}
    <div className="business-tools"><button type="button" autoFocus disabled={loading} onClick={()=>setConfirm(false)}>Hủy</button>
     <ConfirmationButton label="Xác nhận cập nhật" successLabel="Đã cập nhật Sheets" busy={loading} confirmed={confirmed} onClick={()=>{
      setLoading(true);
      run(async()=>{const saved=await write(endpoint,{token:result.token});
       await showSuccess();setNotice(`Google Sheets đã xác nhận ${saved.updated} dòng cập nhật.`);
       setConfirm(false);setResult(null);setRevision(value=>value+1)})
       .finally(()=>setLoading(false));
     }}/></div>
   </Modal>}
  </>}
 </section>;
}
