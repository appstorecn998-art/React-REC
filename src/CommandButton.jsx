import React, {useEffect, useRef, useState} from 'react';
import {AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring} from 'motion/react';

const pressSpring={stiffness:520,damping:34,mass:.6};
const openSpring={type:'spring',stiffness:300,damping:24};

function keyParts(shortcut){
 const parts=shortcut.toLowerCase().split('+').map(v=>v.trim()).filter(Boolean);
 return {mods:parts.filter(v=>['mod','ctrl','alt','shift'].includes(v)),key:parts.find(v=>!['mod','ctrl','alt','shift'].includes(v))||'k'};
}
function isMac(){return /mac|iphone|ipad|ipod/i.test(navigator.platform||'')}
function pressed(mod,event,mac){return mod==='mod'?(mac?event.metaKey:event.ctrlKey):mod==='ctrl'?event.ctrlKey:mod==='alt'?event.altKey:event.shiftKey}

export default function CommandButton({label='Tìm phiếu',placeholder='Số PO/PR, NCC hoặc mặt hàng',shortcut='mod+k',onSearch,width=320,iconOnly=false}){
 const root=useRef(null),input=useRef(null),{mods,key}=keyParts(shortcut),mac=isMac(),reduce=useReducedMotion();
 const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[held,setHeld]=useState({mods:[],key:false});
 const target=useMotionValue(1),scale=useSpring(target,pressSpring);
 const close=()=>{setOpen(false);setQuery('');input.current?.blur()};
 useEffect(()=>{
  const down=e=>{
   if(open)return;
   const heldMods=mods.filter(mod=>pressed(mod,e,mac));
   setHeld({mods:heldMods,key:e.key.toLowerCase()===key||e.code===`Key${key.toUpperCase()}`});
   if(!e.repeat&&heldMods.length===mods.length&&(e.key.toLowerCase()===key||e.code===`Key${key.toUpperCase()}`)){e.preventDefault();setOpen(true)}
  };
  const up=()=>{setHeld({mods:[],key:false});target.set(1)};
  window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',up);
  return()=>{window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',up)};
 },[open,mods,key,mac,target]);
 useEffect(()=>{
  if(!open)return;
  const away=e=>{if(!root.current?.contains(e.target))close()};
  document.addEventListener('pointerdown',away);return()=>document.removeEventListener('pointerdown',away);
 },[open]);
 const submit=()=>{if(query.trim())onSearch?.(query.trim())};
 const updateQuery=value=>{setQuery(value);onSearch?.(value)};
 return <motion.div ref={root} className="command-button" style={{scale,width:open?width:'auto'}} layout transition={{layout:reduce?{duration:0}:openSpring}}
  onPointerDown={()=>!open&&target.set(reduce?1:.97)} onPointerUp={()=>target.set(1)} onPointerLeave={()=>target.set(1)}>
  <AnimatePresence initial={false} mode="popLayout">
   {open?<motion.div key="field" className="command-button-field" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
    <span className="command-search-icon" aria-hidden="true">⌕</span><input ref={input} autoFocus value={query} onChange={e=>updateQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'){updateQuery('');close()}if(e.key==='Enter')submit()}} placeholder={placeholder} aria-label={placeholder}/><kbd>Esc</kbd>
   </motion.div>:<motion.button key="button" type="button" className={'command-button-trigger '+(iconOnly?'is-icon-only':'')} onClick={()=>setOpen(true)} aria-label={label}>
    {iconOnly?<span className="command-search-icon" aria-hidden="true">⌕</span>:<span>{label}</span>}<span className="command-keys">{!iconOnly&&mods.map(mod=><kbd key={mod}>{mod==='mod'?(mac?'⌘':'Ctrl'):mod[0].toUpperCase()+mod.slice(1)}</kbd>)}{!iconOnly&&<kbd data-held={held.key||undefined}>{key.toUpperCase()}</kbd>}</span>
   </motion.button>}
  </AnimatePresence>
 </motion.div>;
}
