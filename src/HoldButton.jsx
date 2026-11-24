import React, {useEffect, useRef, useState} from 'react';
import {motion, useReducedMotion} from 'motion/react';

const holdMs = 1200;
const holdKeys = [' ', 'Enter'];

export default function HoldButton({busy, onConfirm}) {
 const press = useRef(null);
 const [holding, setHolding] = useState(false);
 const reduceMotion = useReducedMotion();

 function cancel(input) {
  if (!press.current || (input != null && input !== press.current.input)) return;
  clearTimeout(press.current.timer);
  press.current = null;
  setHolding(false);
 }

 useEffect(() => {
  const cancelOnBlur = () => cancel();
  window.addEventListener('blur', cancelOnBlur);
  return () => {
   window.removeEventListener('blur', cancelOnBlur);
   clearTimeout(press.current?.timer);
  };
 }, []);

 function start(input) {
  if (busy || press.current) return;
  setHolding(true);
  press.current = {input, timer: setTimeout(() => {
   press.current = null;
   setHolding(false);
   onConfirm();
  }, holdMs)};
 }

 return <button type="button" className="hold-delete-button" disabled={busy}
  aria-label={busy ? 'Đang xóa phiếu' : 'Giữ 1,2 giây để xóa phiếu'}
  onPointerDown={event => {
   if (event.isPrimary && event.button === 0) start(event.pointerId);
  }}
  onPointerUp={event => cancel(event.pointerId)}
  onPointerLeave={event => cancel(event.pointerId)}
  onPointerCancel={event => cancel(event.pointerId)}
  onLostPointerCapture={event => cancel(event.pointerId)}
  onPointerMove={event => {
   if (press.current?.input !== event.pointerId) return;
   const {left, right, top, bottom} = event.currentTarget.getBoundingClientRect();
   if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) {
    cancel(event.pointerId);
   }
  }}
  onContextMenu={event => event.preventDefault()}
  onBlur={() => cancel()}
  onKeyDown={event => {
   if (!holdKeys.includes(event.key)) return;
   event.preventDefault();
   if (!event.repeat) start(event.key);
  }}
  onKeyUp={event => {
   if (!holdKeys.includes(event.key)) return;
   event.preventDefault();
   cancel(event.key);
  }}>
  <motion.span className="hold-delete-fill" aria-hidden="true" initial={false}
   animate={{scaleX:busy || (holding && !reduceMotion) ? 1 : 0}}
   transition={{duration:reduceMotion || busy ? 0 : holding ? holdMs / 1000 : 0.25,
    ease:holding ? 'linear' : 'easeOut'}}/>
  <span className="hold-delete-label">
   {busy && <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
    <motion.path d="m3.5 8 3 3 6-6" fill="none" stroke="currentColor"
     strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
     initial={{pathLength:reduceMotion ? 1 : 0}} animate={{pathLength:1}}
     transition={{duration:reduceMotion ? 0 : 0.25}}/>
   </svg>}
   {busy ? 'Đang xóa…' : holding ? 'Tiếp tục giữ' : 'Giữ để xóa phiếu'}
  </span>
 </button>;
}
