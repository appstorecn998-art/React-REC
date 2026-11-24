"""React REC desktop: Qt Chromium + in-process Python, no HTTP listener."""
import argparse
import base64
import importlib.util
import json
import logging
import sys
import uuid
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS','--disable-gpu --disable-gpu-compositing')
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from PySide6.QtCore import QByteArray, QBuffer, QDate, QIODevice, QObject, Signal, Slot, Qt, QUrl, QTimer, QLockFile, QSaveFile
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PySide6.QtWebEngineCore import (QWebEngineUrlScheme, QWebEngineUrlSchemeHandler,
    QWebEngineUrlRequestJob, QWebEngineProfile, QWebEnginePage, QWebEngineScript,
    QWebEngineUrlRequestInterceptor)
from PySide6.QtWebEngineWidgets import QWebEngineView
from desktop_transport import dispatch

FETCH_SCRIPT = r"""
(() => {
 const nativeFetch=window.fetch.bind(window);
 document.addEventListener('click', event=>{
  const link=event.target.closest?.('a[download]');
  if(!link)return;
  const url=new URL(link.href);
  if(url.origin!==location.origin||url.pathname!=='/api/export/download')return;
  event.preventDefault();
  url.pathname='/__desktop/save-export';
  nativeFetch(url.href).catch(console.error);
 });
 window.fetch=async (input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return nativeFetch(input,options);
  url.searchParams.set('__rec_ipc','1');
  const response=await nativeFetch(url.href,options);
  const packet=await response.json();
  const bytes=Uint8Array.from(atob(packet.body),c=>c.charCodeAt(0));
  return new Response(bytes,{status:packet.status,headers:{'Content-Type':packet.type}});
 };
})();
"""


def register_scheme():
    scheme=QWebEngineUrlScheme(b'rec')
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme |
                    QWebEngineUrlScheme.Flag.CorsEnabled |
                    QWebEngineUrlScheme.Flag.FetchApiAllowed)
    QWebEngineUrlScheme.registerScheme(scheme)


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url=info.requestUrl()
        if url.scheme() not in ('rec','data','blob','qrc','about') or (url.scheme()=='rec' and url.host()!='app'):
            info.block(True)


class SchemeHandler(QWebEngineUrlSchemeHandler):
    completed=Signal(str,object)
    save_export=Signal(str)
    open_legacy=Signal(str)

    def __init__(self, backend, parent):
        super().__init__(parent)
        self.backend=backend
        self.pool=ThreadPoolExecutor(max_workers=6,thread_name_prefix='REC')
        self.jobs={}
        self.pending=set()
        self.completed.connect(self.finish)

    def requestStarted(self, job):
        url=job.requestUrl()
        origin=job.initiator()
        if url.host()!='app' or (not origin.isEmpty() and origin.scheme() not in ('rec',)):
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied);return
        if not origin.isEmpty() and origin.host()!='app':
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied);return
        method=bytes(job.requestMethod()).decode('ascii')
        if url.path() in ('/__desktop/save-export','/__desktop/legacy'):
            if method!='GET' or origin.scheme()!='rec' or origin.host()!='app':
                job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
                return
            buffer=QBuffer(job)
            buffer.setData(b'{}')
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            job.reply(b'application/json',buffer)
            action=self.save_export if url.path().endswith('/save-export') else self.open_legacy
            action.emit(url.query())
            return
        query=parse_qsl(url.query(),keep_blank_values=True)
        envelope=any(k=='__rec_ipc' for k,v in query)
        query=[(k,v) for k,v in query if k!='__rec_ipc']
        path=url.path() or '/'
        if query:path+='?'+urlencode(query)
        headers={bytes(k).decode():bytes(v).decode() for k,v in job.requestHeaders().items()}
        body=b''
        if method=='POST':
            device=job.requestBody()
            if not device.isOpen():device.open(QIODevice.OpenModeFlag.ReadOnly)
            body=bytes(device.readAll())
            logging.info('Request body: size=%s available=%s received=%s',device.size(),device.bytesAvailable(),len(body))
        key=uuid.uuid4().hex
        self.jobs[key]=(job,envelope)
        job.destroyed.connect(lambda *_:self.jobs.pop(key,None))
        future=self.pool.submit(dispatch,self.backend,method,path,headers,body)
        self.pending.add(future)
        future.add_done_callback(lambda f:self.completed.emit(key,f))

    @Slot(str,object)
    def finish(self,key,future):
        self.pending.discard(future)
        pair=self.jobs.get(key)
        if pair is None:return
        job,envelope=pair
        try:status,kind,data=future.result()
        except Exception:
            logging.exception('Desktop request failed')
            status,kind,data=500,'application/json',b'{"error":"REC could not complete this request."}'
        if envelope:
            data=json.dumps(dict(status=status,type=kind,body=base64.b64encode(data).decode())).encode()
            kind='application/json'
        elif status>=400:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound);return
        buffer=QBuffer(job);buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(kind.split(';')[0].encode(),buffer)


class Page(QWebEnginePage):
    def acceptNavigationRequest(self,url,kind,is_main):
        if url.scheme()=='rec' and url.host()=='app':return True
        if kind==QWebEnginePage.NavigationType.NavigationTypeLinkClicked and url.scheme() in ('https','http'):
            QDesktopServices.openUrl(url)
        return False

    def javaScriptConsoleMessage(self,level,message,line,source):
        logging.info('JS %s:%s %s',source,line,message)


class Window(QMainWindow):
    def __init__(self,backend,root,smoke=None):
        super().__init__()
        self.backend=backend
        self.setMinimumSize(760,550)
        self.setWindowTitle('React REC — Quản lý nhận hàng')
        available=self.screen().availableGeometry()
        self.resize(min(1500,available.width()),min(950,available.height()))
        self.profile=QWebEngineProfile(self)
        self.interceptor=LocalOnly(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.handler=SchemeHandler(backend,self.profile)
        self.handler.save_export.connect(self.save_export)
        self.handler.open_legacy.connect(self.open_legacy)
        self.legacy=None
        self.saving_export=False
        self.profile.installUrlSchemeHandler(b'rec',self.handler)
        self.view=QWebEngineView(self)
        self.page=Page(self.profile,self.view)
        script=QWebEngineScript();script.setName('REC internal transport')
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setSourceCode(FETCH_SCRIPT);self.page.scripts().insert(script)
        self.view.setPage(self.page);self.setCentralWidget(self.view)
        self.profile.downloadRequested.connect(self.download)
        self.smoke=smoke
        self.page.renderProcessTerminated.connect(self.log_renderer_exit)
        self.started=False
        if smoke:
            self.page.loadFinished.connect(lambda ok:QTimer.singleShot(15000,self.probe))

    def log_renderer_exit(self,status,exit_code):
        logging.error('REC web renderer stopped: %s (%s)',status.name,exit_code)

    def showEvent(self,event):
        super().showEvent(event)
        if self.started:
            return
        self.started=True
        QTimer.singleShot(0,lambda: self.view.setUrl(QUrl('rec://app/')))

    def probe(self):
        self.page.runJavaScript("""(async()=>{
          const auth=await fetch('/api/ocr/status').then(r=>r.json());
          const invalid=await fetch('/api/receipt/review',{method:'POST',headers:{'Content-Type':'application/json','X-REC-Token':auth.token},body:'{}'});
          const denied=await fetch('/api/receipt/review',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
          window.__recSmoke=JSON.stringify({text:document.body.innerText,images:[...document.images].filter(x=>x.naturalWidth>0).length,href:location.href,headerTop:document.querySelector('.app-header')?.getBoundingClientRect().top,invalidStatus:invalid.status,deniedStatus:denied.status});
        })()""")
        QTimer.singleShot(3000,lambda:self.page.runJavaScript('window.__recSmoke',self.smoke_result))

    def smoke_result(self,value):
        result=json.loads(value or '{}')
        Path(self.smoke).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        self.close()

    @Slot(str)
    def open_legacy(self, query):
        if self.legacy is not None:
            self.legacy.raise_()
            self.legacy.activateWindow()
            return
        job=self.backend.ocr_jobs.public().get('job')
        if self.saving_export or any(not future.done() for future in self.handler.pending) or (
                job and job.get('status') in ('importing','running')):
            QMessageBox.information(self,'Đang xử lý','Chờ thao tác hiện tại hoàn tất.')
            return
        try:
            from receiving_qt import ReceivingWindow

            fields=dict(parse_qsl(query))
            day=date.fromisoformat(fields['day']) if fields.get('day') else None
            legacy=ReceivingWindow(root=self.backend.PROFILE,day=day,auto_load=False,destination=self.backend.STORE)
            legacy.setWindowTitle('React REC · Công cụ REC cũ')
            legacy.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            if day:
                legacy.day=day
                blocked=legacy.date_edit.blockSignals(True)
                legacy.date_edit.setDate(QDate(day.year,day.month,day.day))
                legacy.date_edit.blockSignals(blocked)
            legacy.destroyed.connect(self.legacy_closed)
            self.legacy=legacy
            self.view.setEnabled(False)
            legacy.show()
            legacy.open_day()
        except Exception:
            logging.exception('Could not open legacy REC tools')
            QMessageBox.warning(self,'Công cụ REC cũ','Chưa mở được công cụ REC cũ.')

    @Slot()
    def legacy_closed(self):
        self.legacy=None
        with self.backend.lock:
            self.backend.cache.clear()
        self.view.setEnabled(True)
        self.page.runJavaScript("window.dispatchEvent(new Event('rec-data-changed'))")

    @Slot(str)
    def save_export(self, query):
        if self.saving_export:
            return
        from receipt_workflow import download, guard

        self.saving_export=True
        try:
            fields=dict(parse_qsl(query))
            report=self.backend.available_days().get(fields.get('day'))
            if report is None:
                raise ValueError('Ngày không có báo cáo REC.')
            index=int(fields.get('file','-1'))
            with guard:
                source=download(self.backend.STORE,report,index)
            path,_=QFileDialog.getSaveFileName(self,'Lưu hồ sơ REC',source.name)
            if not path:
                return
            with guard:
                source=download(self.backend.STORE,report,index)
                if Path(path).resolve()==source:
                    return
                target=QSaveFile(path)
                if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                    raise OSError(target.errorString())
                with source.open('rb') as stream:
                    while chunk:=stream.read(1024*1024):
                        if target.write(chunk)!=len(chunk):
                            raise OSError(target.errorString())
                if not target.commit():
                    raise OSError(target.errorString())
        except (OSError,ValueError,KeyError) as exc:
            QMessageBox.warning(self,'Không lưu được hồ sơ REC',str(exc))
        finally:
            self.saving_export=False

    def download(self,item):
        path,_=QFileDialog.getSaveFileName(self,'Lưu file REC',item.downloadFileName())
        if path:
            item.setDownloadDirectory(str(Path(path).parent));item.setDownloadFileName(Path(path).name);item.accept()
        else:item.cancel()

    def closeEvent(self,event):
        if self.legacy is not None:
            self.legacy.raise_()
            QMessageBox.information(self,'Công cụ REC cũ','Đóng cửa sổ công cụ REC cũ trước.')
            event.ignore()
            return
        if self.saving_export:
            event.ignore()
            return
        job=self.backend.ocr_jobs.public().get('job')
        if job and job.get('status') in ('importing','running'):
            QMessageBox.information(self,'Đang xử lý','Chờ OCR hoàn tất trước khi đóng REC.');event.ignore();return
        if any(not f.done() for f in self.handler.pending):
            QMessageBox.information(self,'Đang xử lý','Chờ thao tác hiện tại hoàn tất trước khi đóng REC.');event.ignore();return
        # Pending writes finish before Python exits; no worker is killed mid-save.
        self.handler.pool.shutdown(wait=True)
        event.accept()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--smoke',type=Path)
    args=parser.parse_args();root=args.root.resolve()
    if not (root/'dist/index.html').is_file():raise SystemExit('Thiếu dist/index.html. Dựng giao diện trước khi mở app.')
    sys.path.insert(0,str(root))
    (root/'output').mkdir(exist_ok=True)
    logging.basicConfig(filename=root/'output/desktop.log',level=logging.INFO,encoding='utf-8')
    # Large receipt photos are more stable without QtWebEngine's GPU compositor;
    # rapid resize/zoom otherwise can terminate the renderer on some drivers.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)
    register_scheme()
    app=QApplication(sys.argv)
    lock=QLockFile(str(root/'output'/('desktop-smoke.lock' if args.smoke else 'desktop.lock')))
    if not lock.tryLock(0):
        QMessageBox.information(None,'REC đang mở','React REC đã mở trong một cửa sổ khác.');return 0
    spec=importlib.util.spec_from_file_location('rec_backend',root/'server.py')
    backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
    window=Window(backend,root,args.smoke);window.show()
    result=app.exec();lock.unlock();return result


if __name__=='__main__':raise SystemExit(main())



