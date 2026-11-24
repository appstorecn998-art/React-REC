import React,{useEffect,useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import ConfirmationButton, {useConfirmation} from './ConfirmationButton';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Search,BookOpen,ChevronLeft,ChevronRight} from 'lucide-react';
const folded=value=>String(value??'').toLowerCase().normalize('NFD').replace(/\p{M}/gu,'').replace(/đ/g,'d');
const pageSize=40;
export default function KnowledgePage(){
 const [items,setItems]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[query,setQuery]=useState(''),[kind,setKind]=useState(''),[supplier,setSupplier]=useState(''),[state,setState]=useState(''),[page,setPage]=useState(0),[change,setChange]=useState(null),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{const controller=new AbortController();setLoading(true);fetch('/api/knowledge',{cache:'no-store',signal:controller.signal}).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.error||'Chưa đọc được ghi nhớ.');setItems(data.items);setError('')}).catch(error=>{if(error.name!=='AbortError')setError(error.message)}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});return ()=>controller.abort()},[revision]);
 const [confirmed,showSuccess]=useConfirmation();
 const types=[...new Map(items.map(item=>[item.type,item.label])).entries()].sort((a,b)=>a[1].localeCompare(b[1],'vi'));
 const suppliers=[...new Set(items.map(item=>item.supplier))].sort((a,b)=>a.localeCompare(b,'vi'));
 const result=items.filter(item=>(!kind||item.type===kind)&&(!supplier||item.supplier===supplier)&&(!state||(state==='on'?item.active:item.active===false))&&folded(JSON.stringify(item)).includes(folded(query)));
 const currentPage=Math.min(page,Math.max(0,Math.ceil(result.length/pageSize)-1));
 function filter(setter,value){setter(value);setPage(0)}
 async function save(){if(busy||!reason.trim())return;setBusy(true);setError('');try{const auth=await fetch('/api/ocr/status',{cache:'no-store'}).then(r=>r.json());const response=await fetch('/api/knowledge/pair',{method:'POST',headers:{'Content-Type':'application/json','X-REC-Token':auth.token},body:JSON.stringify({rule:change.id,active:!change.active,reason})});const data=await response.json();if(!response.ok)throw new Error(data.error||'Chưa cập nhật được cặp ghép.');await showSuccess();setChange(null);setReason('');setRevision(r=>r+1)}catch(error){setError(error.message)}finally{setBusy(false)}}
 return <section className="knowledge-page" aria-label="Toàn bộ ghi nhớ REC">
  <div className="knowledge-intro"><BookOpen size={20}/><div><h2>Toàn bộ ghi nhớ</h2><p>Tra cứu quy tắc đã lưu ở mọi NCC và mọi ngày: tên hàng, mã, cặp PR, quy đổi, đóng gói, quy cách và phân kho.</p></div><Button label="Tải lại" size="sm" variant="secondary" isDisabled={loading} onClick={()=>setRevision(r=>r+1)}/></div>
  <div className="knowledge-filters">
   <TextInput type="search" label="Tìm trong toàn bộ nội dung" placeholder="Tên hàng, mã, NCC, quy cách…" value={query} onChange={value=>filter(setQuery,value)} hasClear/>
   <label>Loại ghi nhớ<select aria-label="Loại ghi nhớ" value={kind} onChange={event=>filter(setKind,event.target.value)}><option value="">Tất cả loại</option>{types.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
   <label>Nhà cung cấp<select aria-label="Nhà cung cấp" value={supplier} onChange={event=>filter(setSupplier,event.target.value)}><option value="">Tất cả NCC</option>{suppliers.map(name=><option key={name}>{name}</option>)}</select></label>
   <label>Trạng thái<select aria-label="Trạng thái" value={state} onChange={event=>filter(setState,event.target.value)}><option value="">Tất cả</option><option value="on">Đang dùng</option><option value="off">Đã ngừng dùng</option></select></label>
  </div>
  {error&&<p role="alert" className="error-banner">{error}</p>}
  <div className="knowledge-count" role="status">{loading?'Đang đọc ghi nhớ…':`${result.length} / ${items.length} mục · Toàn bộ ngày`}</div>
  <div className="knowledge-table-wrap"><table className="knowledge-table"><thead><tr><th>Loại / NCC</th><th>Nội dung đã lưu</th><th>Căn cứ / chi tiết</th><th>Trạng thái</th></tr></thead><tbody>
   {result.slice(currentPage*pageSize,(currentPage+1)*pageSize).map(item=><tr key={item.type+item.id}><td><span className="knowledge-type">{item.label}</span><small>{item.supplier}</small></td><td><strong>{item.title}</strong>{item.summary&&<p>{item.summary}</p>}</td><td>{item.reason&&<p>{item.reason}</p>}<details><summary>Xem toàn bộ nội dung</summary><pre>{JSON.stringify(item.record,null,2)}</pre></details></td><td><span>{item.active?'Đang dùng':'Đã chặn tự ghép'}</span>{item.pair&&<Button label={item.active?'Ngừng dùng':'Cho dùng lại'} size="sm" variant="ghost" onClick={()=>{setChange(item);setReason('');setError('')}}/>}</td></tr>)}
   {!loading&&!result.length&&<tr><td colSpan={4}>Không có ghi nhớ phù hợp với bộ lọc.</td></tr>}
  </tbody></table></div>
  <div className="knowledge-pagination"><span>Trang {currentPage+1} / {Math.max(1,Math.ceil(result.length/pageSize))}</span><Button label="Trang ghi nhớ trước" variant="ghost" size="sm" icon={<ChevronLeft size={14}/>} isDisabled={currentPage===0} onClick={()=>setPage(currentPage-1)}/><Button label="Trang ghi nhớ sau" variant="ghost" size="sm" icon={<ChevronRight size={14}/>} isDisabled={(currentPage+1)*pageSize>=result.length} onClick={()=>setPage(currentPage+1)}/></div>
  {change&&<div className="knowledge-confirm" role="region" aria-label="Xác nhận thay đổi cặp ghép"><h3>{change.active?'Ngừng dùng cặp ghép':'Cho dùng lại cặp ghép'}</h3><p>{change.supplier} · {change.title} ↔ {change.summary}</p><p>Ngừng dùng sẽ chặn tự ghép lại đúng cặp này. Các cặp đã gán tay trên phiếu được giữ nguyên.</p><TextInput label="Lý do thay đổi" value={reason} onChange={setReason}/><div className="receipt-actions"><Button label="Hủy thay đổi" variant="ghost" isDisabled={busy} onClick={()=>setChange(null)}/><ConfirmationButton label="Xác nhận thay đổi" successLabel="Đã lưu" busy={busy} confirmed={confirmed} isDisabled={!reason.trim()} onClick={save}/></div></div>}
 </section>
}
