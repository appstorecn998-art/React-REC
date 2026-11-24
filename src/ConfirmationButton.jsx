import React, {useState} from 'react';
import {motion, useReducedMotion} from 'motion/react';

// Loading to success uses distinct springs for the width, label and check.
const spring = (stiffness, damping) => ({type:'spring', stiffness, damping});

export function useConfirmation() {
 const [confirmed,setConfirmed]=useState(false);
 async function showSuccess() {
  setConfirmed(true);
  await new Promise(resolve=>setTimeout(resolve,850));
  setConfirmed(false);
 }
 return [confirmed,showSuccess];
}

export default function ConfirmationButton({label,successLabel='Đã xác nhận',busy,confirmed,isDisabled,onClick,type='button'}) {
 const reduced=useReducedMotion();
 const pending=busy&&!confirmed;
 const transition=(stiffness,damping)=>reduced?{duration:0}:spring(stiffness,damping);
 return <span className="confirmation-button-slot">
  <motion.button type={type} className="confirmation-button" data-confirmed={Boolean(confirmed)}
   disabled={busy||confirmed||isDisabled} onClick={onClick}
   aria-label={confirmed?successLabel:pending?'Đang xử lý':undefined} aria-busy={pending}
   initial={false} animate={{width:pending&&!reduced?34:'auto',backgroundColor:confirmed?'#21633d':'#242624'}}
   transition={{width:transition(300,22),backgroundColor:transition(200,30)}}>
   <motion.span className="confirmation-button-label" aria-hidden={pending||confirmed}
    animate={{opacity:pending||confirmed?0:1,y:pending||confirmed?14:0}} transition={transition(400,30)}>{label}</motion.span>
   {pending&&<motion.span className="confirmation-button-spinner" aria-hidden="true"
    initial={{opacity:0,scale:.6}} animate={{opacity:1,scale:1}} transition={transition(300,28)}><i/></motion.span>}
   {confirmed&&<motion.span className="confirmation-button-result" aria-hidden="true"
    initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={transition(220,20)}>
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
     <motion.path d="M5 12.5l4.5 4.5L19 7.5" initial={{pathLength:0}} animate={{pathLength:1}}
      transition={reduced?{duration:0}:{...spring(120,20),delay:.15}}/>
    </svg>{successLabel}
   </motion.span>}
  </motion.button>
  <span className="confirmation-announcement" role="status">{confirmed?successLabel:pending?'Đang xử lý…':''}</span>
 </span>;
}
