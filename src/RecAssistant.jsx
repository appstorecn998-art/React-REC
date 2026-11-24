import React, {useEffect, useRef, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {ArrowUp, BookOpen, FileCode2, Globe, Sheet, Sparkles} from 'lucide-react';

const actions = {
 ledger: {label:'Ghi sổ', icon:BookOpen, path:'/api/workspace/ledger'},
 sheets: {label:'Đồng bộ Sheets', icon:Sheet, path:'/api/workspace/sheets'},
};

const displayDate = value => value.split('-').reverse().join('/');

function ReceiptLookup({lookup}) {
 return <section className="rec-assistant-lookup" aria-label="Kết quả tra sổ REC">
  <strong>Phiếu chưa ghi sổ từ {displayDate(lookup.start)} đến {displayDate(lookup.end)}</strong>
  <p>{lookup.days?lookup.rows.length+' phiếu chưa ghi sổ · '+lookup.days+' ngày có báo cáo':'REC chưa có báo cáo trong khoảng ngày này.'}</p>
  {lookup.rows.length>0&&<details open>
   <summary>Danh sách phiếu</summary>
   <ul className="rec-assistant-receipts">
    {lookup.rows.map(row=><li key={row.day+' '+row.sheet}>{displayDate(row.day)} · <strong>{row.sheet}</strong>{row.supplier&&' · '+row.supplier}</li>)}
   </ul>
  </details>}
 </section>;
}

async function request(path, payload, signal) {
 const headers = {};
 if (payload) {
  const auth = await fetch('/api/ocr/status', {cache:'no-store', signal});
  if (!auth.ok) throw Error('Chưa kết nối được với REC.');
  headers['X-REC-Token'] = (await auth.json()).token;
  headers['Content-Type'] = 'application/json';
 }
 const response = await fetch(path, {
  method:payload?'POST':'GET', signal, headers, cache:'no-store',
  body:payload?JSON.stringify(payload):undefined,
 });
 const result = await response.json().catch(()=>({}));
 if (!response.ok) throw Error(result.error || 'REC chưa xử lý được yêu cầu.');
 return result;
}

function ActionPreview({plan, day, busy, onClose, onConfirm}) {
 const ledger=plan.kind==='ledger';
 const count=ledger?plan.ready:plan.changeCount;
 const canConfirm=ledger?count>0:!plan.historyReview&&(count>0||plan.newTabs.length>0);
 return <section className="rec-assistant-plan" aria-label="Bản xem trước thao tác">
  <h2>{ledger?'Ghi sổ ngày '+day:'Cập nhật Google Sheets'}</h2>
  {!ledger&&<p>Phạm vi cập nhật · Toàn bộ sổ nhận hàng</p>}
  <p>{ledger?count+' / '+plan.entries.length+' phiếu sẵn sàng ghi sổ.':
   count+' dòng thay đổi · '+plan.newTabs.length+' tab mới · '+plan.skipped+' dòng chưa đủ điều kiện.'}</p>
  {plan.historyReview&&<p role="status">Cần xác minh lịch sử trước khi cập nhật.</p>}
  {plan.newTabs?.length>0&&<p>Tab sẽ tạo · {plan.newTabs.join(', ')}</p>}
  <ul className="rec-assistant-receipts">
   {ledger?plan.entries.map(row=><li key={row.sheet}>
    <strong>{row.sheet}</strong> · {row.status}
    {row.status!=='Sẵn sàng ghi sổ'&&row.reason&&<div>{row.reason}</div>}
   </li>):plan.changes.map((row,index)=><li key={index}>
    <strong>{row.name}</strong> · {row.tab} · {row.action}
    <div>Thiếu {row.old?.[8]??'—'} → {row.delete?0:row.values?.[8]??'—'}</div>
   </li>)}
  </ul>
  <div className="rec-assistant-suggestions">
   <Button label="Đóng" variant="secondary" isDisabled={busy} onClick={onClose}/>
   {canConfirm&&<Button label={ledger?'Xác nhận ghi sổ '+count+' phiếu':'Xác nhận cập nhật Sheets'}
    variant="primary" isDisabled={busy||!plan.token} onClick={onConfirm}/>}
  </div>
 </section>;
}

export default function RecAssistant({day, dateLabel, navigationBusy}) {
 const [question,setQuestion]=useState('');
 const [messages,setMessages]=useState([]);
 const [pending,setPending]=useState('');
 const [plan,setPlan]=useState(null);
 const [shareSource,setShareSource]=useState(false);
 const [shareRec,setShareRec]=useState(false);
 const chat=useRef(null);
 const input=useRef(null);
 const running=useRef(false);

 useEffect(()=>{
  const panel=chat.current;
  if (panel) panel.scrollTop=panel.scrollHeight;
 },[messages,pending,plan]);

 function add(message) {
  setMessages(items=>[...items,message]);
 }

 async function send(text, action) {
  text=text.trim();
  if (!text||!day||running.current||navigationBusy) return;
  running.current=true;
  setQuestion('');
  setPlan(null);
  const localContext=shareRec||shareSource;
  add({role:'user',text,localContext});
  setPending(action?'REC đang lập bản xem trước…':'Gemini đang xử lý…');
  try {
   const reply=action?{action}:await request('/api/assistant',{
    day,question:text,shareSource,shareRec,
    history:messages.filter(message=>!message.error&&(localContext||!message.localContext)).slice(-8).map(({role,text})=>({role,text})),
   },AbortSignal.timeout(130000));
   if (reply.answer||reply.receiptLookup) add({role:'assistant',text:reply.answer,sources:reply.sources,receiptLookup:reply.receiptLookup,localContext});
   const workflow=actions[reply.action];
   if (!workflow) return;
   setPending('REC đang lập bản xem trước…');
   const payload=reply.action==='ledger'?{action:'post_day',day}:null;
   const preview=await request(workflow.path,payload,AbortSignal.timeout(60000));
   setPlan({...preview,kind:reply.action});
  } catch (error) {
   add({role:'assistant',error:true,text:error.name==='TimeoutError'?'REC phản hồi quá lâu. Bạn có thể gửi lại câu hỏi hoặc thao tác.':error.message});
   setQuestion(text);
  } finally {
   running.current=false;
   setPending('');
  }
 }

 async function confirm() {
  if (!plan?.token||running.current||navigationBusy) return;
  const ledger=plan.kind==='ledger';
  running.current=true;
  setPending(ledger?'Đang ghi sổ…':'Đang cập nhật Google Sheets…');
  try {
   const saved=await request(actions[plan.kind].path,
    ledger?{action:'post_day',day,token:plan.token}:{token:plan.token},AbortSignal.timeout(90000));
   const text=ledger?
    'Đã ghi sổ '+saved.results.filter(row=>row[1]==='Đã ghi sổ').length+' / '+saved.results.length+' phiếu ngày '+dateLabel+'.':
    'Google Sheets đã xác nhận '+saved.updated+' dòng cập nhật.';
   add({role:'assistant',text,results:saved.results,localContext:true});
  } catch (error) {
   add({role:'assistant',error:true,text:error.name==='TimeoutError'?
    'Chưa nhận được kết quả. Mở bản xem trước mới để kiểm tra trạng thái hiện tại.':error.message});
  } finally {
   setPlan(null);
   running.current=false;
   setPending('');
  }
 }

 return <section className="secondary-page rec-assistant">
  <header className="rec-assistant-header">
   <div><Sparkles size={20} aria-hidden="true"/><h1>Gemini trong REC</h1></div>
   <span>{dateLabel}</span>
  </header>
  <div className="rec-assistant-body">
   <div ref={chat} className="rec-assistant-chat" role="log" aria-label="Cuộc trò chuyện">
    {!messages.length&&<div className="rec-assistant-welcome">
     <h2>Bạn muốn xử lý việc gì?</h2>
     <p>Trò chuyện với Gemini, hỏi về sổ nhận hàng hoặc tra cứu thông tin.</p>
     <div className="rec-assistant-suggestions">
      <Button label="Còn phiếu nào cần kiểm tra?" size="sm" variant="secondary" onClick={()=>{setQuestion('Ngày đang chọn còn bao nhiêu phiếu cần kiểm tra?');input.current?.focus()}}/>
      <Button label="REC tính hàng thiếu thế nào?" icon={<FileCode2 size={15}/>} size="sm" variant="secondary"
       onClick={()=>send('Tra mã nguồn REC và giải thích cách tính hàng còn thiếu.')}/>
      <Button label="Tra web" icon={<Globe size={15}/>} size="sm" variant="secondary" onClick={()=>{setQuestion('Tra web giúp tôi về ');input.current?.focus()}}/>
     </div>
    </div>}
    {messages.map((message,index)=><article key={index} className={'rec-assistant-message '+message.role}>
     <strong>{message.role==='user'?'Bạn':'Gemini'}</strong>
     {message.text&&<p role={message.error?'alert':undefined}>{message.text}</p>}
     {message.receiptLookup&&<ReceiptLookup lookup={message.receiptLookup}/>}
     {message.sources?.length>0&&<ul className="rec-assistant-sources" aria-label="Nguồn">
      {message.sources.map((source,i)=><li key={i}>
       {source.excerpt?<details><summary><code>{source.title}</code></summary><pre>{source.excerpt}</pre></details>:
        source.url?.startsWith('https://')?<a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>:<code>{source.title}</code>}
      </li>)}
     </ul>}
     {message.results?.length>0&&<ul className="rec-assistant-receipts">
      {message.results.map(([sheet,status,detail])=><li key={sheet}>{sheet} · {status}{detail&&<div>{detail}</div>}</li>)}
     </ul>}
    </article>)}
    {plan&&<ActionPreview plan={plan} day={dateLabel} busy={!!pending||navigationBusy} onClose={()=>setPlan(null)} onConfirm={confirm}/>}
    {pending&&<p role="status" className="rec-assistant-progress">{pending}</p>}
   </div>
   <form onSubmit={event=>{event.preventDefault();send(question)}} className="rec-assistant-form">
    <label htmlFor="rec-assistant-question">Nhắn cho Gemini</label>
    <textarea ref={input} id="rec-assistant-question" value={question} rows={2} maxLength={1000}
     placeholder="Nhập câu hỏi hoặc việc bạn muốn REC xử lý…" onChange={event=>setQuestion(event.target.value)}
     onKeyDown={event=>{
      if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();event.currentTarget.form.requestSubmit()}
     }}/>
    <div className="rec-assistant-submit">
     <div className="rec-assistant-suggestions" role="group" aria-label="Thao tác nhanh">
      {Object.entries(actions).map(([id,action])=><Button key={id} type="button" label={action.label} size="sm"
       variant="secondary" icon={<action.icon size={15}/>} isDisabled={!!pending||navigationBusy||!day}
       onClick={()=>send(action.label,id)}/>)}
     </div>
     <Button type="submit" label="Gửi" icon={<ArrowUp size={16}/>} variant="primary"
      isDisabled={!day||!question.trim()||!!pending||navigationBusy}/>
    </div>
    <label className="rec-assistant-source-option">
     <input type="checkbox" checked={shareRec} onChange={event=>setShareRec(event.target.checked)}/>
     Cho phép gửi số liệu sổ và tình trạng phiếu liên quan sang Gemini
    </label>
    <label className="rec-assistant-source-option">
     <input type="checkbox" checked={shareSource} onChange={event=>setShareSource(event.target.checked)}/>
     Cho phép gửi đoạn mã REC liên quan đến Gemini để giải thích
    </label>
   </form>
  </div>
 </section>;
}
