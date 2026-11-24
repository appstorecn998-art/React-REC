"""Measure click-to-render in the same source and frozen GUI, with no cloud calls."""
def run(path=None):
 import tempfile,time,json
 from pathlib import Path
 from PIL import Image
 from PySide6.QtWidgets import QApplication
 from PySide6.QtCore import QTimer
 from receiving_qt import ReceivingWindow
 app=QApplication.instance() or QApplication([])
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp)
  if path:
   image=Path(path);box=[0,1904,3024,2013];anchor=[409,1913,2576,2005]
  else:
   image=root/'sample.png';Image.new('RGB',(3024,4032),'white').save(image);box=[0,1904,3024,2013];anchor=[409,1913,2576,2005]
  w=ReceivingWindow(root=root,auto_load=False);w.local_review_enabled=False;w.show();w.inbox_timer.stop();app.processEvents()
  ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(time.perf_counter()));timer.start()
  samples=[]
  try:
   for i in range(4):
    # same selected item, then a different item on the same page
    which=0 if i<3 else 1
    match={'box':[box[0],box[1]+which*110,box[2],box[3]+which*110],'anchor':[anchor[0],anchor[1]+which*110,anchor[2],anchor[3]+which*110],'text':'sample'+str(which)}
    values={'Tên hàng trên phiếu (Ảnh)':'sample'+str(which),'STT trên phiếu':str(which)}
    w.location_request+=1;w.region_qimage=None
    start=time.perf_counter();w.show_row_region(image,values,{'initial_match':match},w.location_request)
    returned=time.perf_counter()-start
    while w.region_qimage is None and time.perf_counter()-start<20:app.processEvents();time.sleep(.001)
    if w.region_qimage is None:raise RuntimeError('Render timeout')
    samples.append({'click':i,'handler_ms':returned*1000,'render_ms':(time.perf_counter()-start)*1000})
   return {'samples':samples,'ui_timer_ticks':len(ticks),'network_requests':0}
  finally:
   timer.stop();w.close();app.processEvents()
