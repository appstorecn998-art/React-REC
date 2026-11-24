(() => {
 const send=(action,extra='')=>fetch('rec://app/__window/'+action+extra).catch(()=>{});
 const style=document.createElement('style');
 style.textContent=`
  .app-header{padding-right:154px!important;user-select:none}
  html,body,#root{width:100%;height:100%;overflow:hidden} html,body{border-radius:8px} .studio{width:100%;height:100dvh;min-width:0;overflow:hidden;border-radius:8px} #rec-window-controls{position:fixed;top:0;right:0;z-index:100;width:138px;height:46px;display:flex;background:#fff}
  #rec-window-controls button{width:46px;height:46px;display:grid;place-items:center;border:0;background:transparent;color:#444;cursor:default;padding:0}
  #rec-window-controls button:hover{background:#ececec}
  #rec-window-controls button:last-child:hover{background:#c42b1c;color:#fff}
  #rec-window-controls button:focus-visible{outline:2px solid #666;outline-offset:-4px}
  #rec-window-controls svg{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:1}
  .rec-resize-edge{position:fixed;z-index:101}
  .rec-resize-edge[data-edge=n]{top:0;left:6px;right:6px;height:4px;cursor:n-resize}
  .rec-resize-edge[data-edge=s]{bottom:0;left:6px;right:6px;height:4px;cursor:s-resize}
  .rec-resize-edge[data-edge=w]{left:0;top:6px;bottom:6px;width:4px;cursor:w-resize}
  .rec-resize-edge[data-edge=e]{right:0;top:6px;bottom:6px;width:4px;cursor:e-resize}
  .rec-resize-edge[data-edge=nw]{left:0;top:0;width:6px;height:6px;cursor:nw-resize}
  .rec-resize-edge[data-edge=ne]{right:0;top:0;width:6px;height:6px;cursor:ne-resize}
  .rec-resize-edge[data-edge=sw]{left:0;bottom:0;width:6px;height:6px;cursor:sw-resize}
  .rec-resize-edge[data-edge=se]{right:0;bottom:0;width:6px;height:6px;cursor:se-resize}
  html[data-rec-maximized=true] .rec-resize-edge{display:none} html[data-rec-maximized=true],html[data-rec-maximized=true] body,html[data-rec-maximized=true] .studio{border-radius:0}
 `;
 function mount(){
  if(!document.head||!document.body)return;
  document.head.append(style);
  const controls=document.createElement('div');controls.id='rec-window-controls';controls.setAttribute('role','group');controls.setAttribute('aria-label','Điều khiển cửa sổ');
  const drawings=['M1 6h10','M1 1h10v10H1z','M1 1l10 10M11 1L1 11'];
  ['Thu nhỏ cửa sổ','Phóng to cửa sổ','Đóng ứng dụng'].forEach((label,i)=>{
   const b=document.createElement('button');b.type='button';b.title=label;b.setAttribute('aria-label',label);
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 12 12');svg.setAttribute('aria-hidden','true');
   const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',drawings[i]);svg.append(path);b.append(svg);
   b.addEventListener('click',()=>send(['minimize','maximize','close'][i]));controls.append(b);
  });
  document.body.append(controls);
  for(const edge of ['n','s','e','w','nw','ne','sw','se']){
   const grip=document.createElement('div');grip.className='rec-resize-edge';grip.dataset.edge=edge;grip.setAttribute('aria-hidden','true');
   grip.addEventListener('pointerdown',e=>{if(e.button===0){e.preventDefault();send('resize','?edge='+edge)}});document.body.append(grip);
  }
  const isDragTarget=e=>e.target.closest('.app-header')&&!e.target.closest('button,a,input,select,textarea,[role=button],[role=combobox],[contenteditable=true]');
  document.addEventListener('pointerdown',e=>{if(e.button===0&&e.detail<2&&isDragTarget(e))send('move')});
  document.addEventListener('dblclick',e=>{if(e.button===0&&isDragTarget(e))send('maximize')});
  window.addEventListener('rec-window-state',e=>{
   document.documentElement.dataset.recMaximized=String(e.detail);
   const b=controls.children[1],label=e.detail?'Khôi phục cửa sổ':'Phóng to cửa sổ';b.title=label;b.setAttribute('aria-label',label);
  });
  send('state');
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();

