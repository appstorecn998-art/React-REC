import React,{useState,useRef,useLayoutEffect,useEffect} from 'react';
import {ChevronRight,Link2,Ruler,SlidersHorizontal,FileText,Files,Coins} from 'lucide-react';
const icons=[Link2,Ruler,SlidersHorizontal,Coins,FileText,Files];
export default function RowContextMenu({context,groups,quickAction,onAction,onClose}){
 const [active,setActive]=useState(null),[position,setPosition]=useState({left:0,top:0});
 const root=useRef(null),panel=useRef(null);
 useEffect(()=>{root.current?.querySelector('button')?.focus()},[]);
 useLayoutEffect(()=>{
  if(!panel.current)return;
  const r=root.current.getBoundingClientRect(),p=panel.current.getBoundingClientRect();
  const left=r.right+p.width+12<=window.innerWidth?r.right+6:Math.max(8,r.left-p.width-6);
  const group=root.current.querySelectorAll('[aria-haspopup="menu"]')[active];
  const top=Math.max(8,Math.min(group.getBoundingClientRect().top,window.innerHeight-p.height-8));
  setPosition({left,top});
 },[active,context]);
 function keys(event){
  const buttons=[...event.currentTarget.querySelectorAll('button:not(:disabled)')];
  const index=buttons.indexOf(document.activeElement);
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
   event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons[next]?.focus();
  }
 }
 return <div ref={root} className="receipt-context rec-row-menu" aria-label="Thao tác dòng hàng" style={{left:Math.min(context.x,window.innerWidth-264),top:Math.max(8,Math.min(context.y,window.innerHeight-(quickAction?302:260)))}}>
  <div className="rec-menu-heading">Thao tác dòng hàng</div>
  <div role="menu" aria-label="Nhóm thao tác" onKeyDown={keys}>
   {quickAction&&<button type="button" role="menuitem" onMouseEnter={()=>setActive(null)}
    onClick={()=>{onAction(quickAction);onClose()}}><Ruler size={16}/><span>{quickAction.label}</span></button>}
   {groups.map(([label,entries],i)=>{const Icon=icons[i];return <button key={label} type="button" role="menuitem" aria-haspopup="menu" aria-expanded={active===i} className={active===i?'is-active':''} onMouseEnter={()=>setActive(i)} onClick={()=>setActive(i)} onKeyDown={event=>{if(event.key==='ArrowRight'){event.preventDefault();setActive(i);requestAnimationFrame(()=>panel.current?.querySelector('button:not(:disabled)')?.focus())}}}>
    <Icon size={16}/><span>{label}</span><ChevronRight size={14}/>
   </button>})}
  </div>
  {active!==null&&<div ref={panel} className="rec-row-submenu" style={position} role="menu" aria-label={groups[active][0]} onKeyDown={event=>{keys(event);if(event.key==='ArrowLeft'){event.preventDefault();setActive(null);root.current?.querySelectorAll('[aria-haspopup]')[active]?.focus()}}}>
   <div className="rec-menu-heading">{groups[active][0]}</div>
   {groups[active][1].map(entry=><button type="button" role="menuitem" key={entry.key} disabled={entry.disabled} onClick={()=>{onAction(entry);onClose()}}>{entry.label.replace(/…$/,'')}<span className="rec-menu-action-arrow" aria-hidden="true">↗</span></button>)}
  </div>}
 </div>
}
