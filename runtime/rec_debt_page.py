"""Independent multi-day receipt queue for supplier reconciliation."""
import os,json,sys,codecs
from pathlib import Path
from datetime import date,datetime
from PySide6.QtCore import Qt,QDate,QProcess,QProcessEnvironment
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDateEdit,QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QMessageBox,QProgressBar,QApplication
from receiving_service import atomic_json,import_images,paths,snapshot
from rec_debt_data import workspace,profile,export

class DebtPage(QWidget):
    def __init__(self,w):
        super().__init__();self.owner=w;self.root=workspace(w.destination);self.running=False;self.reading=False;self.proc=None
        self.root.mkdir(parents=True,exist_ok=True);self.input=self.root/'AnhDauVao';self.input.mkdir(exist_ok=True);self.state_file=self.root/'hang-doi.json'
        try:self.jobs=json.loads(self.state_file.read_text(encoding='utf-8')) if self.state_file.exists() else []
        except (OSError,ValueError):raise ValueError('Không đọc được hàng đợi công nợ. Giữ file cũ và kiểm tra trước khi tiếp tục.')
        for job in self.jobs:
            if job['status']=='Đang đọc':job['status']='Chưa hoàn tất'
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,20);layout.setSpacing(12)
        title=QLabel('Đối chiếu công nợ');title.setStyleSheet('font-size:22px;font-weight:600;color:#26324b;');layout.addWidget(title)
        bar=QHBoxLayout();self.day=QDateEdit(QDate.currentDate());self.day.setCalendarPopup(True);self.day.setDisplayFormat('dd/MM/yyyy');bar.addWidget(QLabel('Ngày'));bar.addWidget(self.day)
        self.new_receipt=QPushButton('Tạo phiếu mới');self.add=QPushButton('Thêm ảnh');self.run=QPushButton('Đọc phiếu');self.output=QPushButton('Xuất Excel');self.open_report=QPushButton('Kiểm phiếu');folder=QPushButton('Thư mục ảnh');details=QPushButton('Chi tiết');details.setCheckable(True);bar.addWidget(self.add);bar.addWidget(folder);bar.addStretch();bar.addWidget(self.run);bar.addWidget(self.open_report);bar.addWidget(self.new_receipt);bar.addWidget(self.output);bar.addWidget(details);layout.addLayout(bar)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Ngày nhóm ảnh','Ảnh đã thêm','Trạng thái','Kết quả']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.setMaximumHeight(110);layout.addWidget(self.table)
        from rec_debt_review import DebtReview
        self.review=DebtReview(self);layout.addWidget(self.review,1);self.review.hide()
        self.empty=QLabel('Chọn ngày và thêm ảnh để bắt đầu.');self.empty.setAlignment(Qt.AlignCenter);layout.addWidget(self.empty,1)
        self.table.cellDoubleClicked.connect(lambda *_:self.open_selected_report())
        self.status=QLabel('Chưa có tác vụ đang chạy.');self.status.setWordWrap(True);layout.insertWidget(2,self.status)
        self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.setFixedHeight(6);self.progress.hide();layout.insertWidget(3,self.progress)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(75);self.log.setMaximumBlockCount(1500);self.log.hide();details.toggled.connect(self.log.setVisible)
        self.new_receipt.clicked.connect(lambda:self.review.manual_line(True));self.add.clicked.connect(self.add_images);self.run.clicked.connect(self.start);self.output.clicked.connect(self.export_file);self.open_report.clicked.connect(self.open_selected_report);folder.clicked.connect(lambda:os.startfile(self.input));self.render()
        self.setStyleSheet('QWidget {font-family:Segoe UI;font-size:13px;color:#40506c;} QPushButton,QDateEdit {min-height:36px;border:1px solid #dddfea;border-radius:7px;padding:0 12px;background:white;} QTableWidget {background:white;border:1px solid #e5e7f0;}')
    def feedback(self,message,kind='info',busy=False):
        colors={'info':('#eef2ff','#40506c'),'busy':('#eeeaff','#5143bd'),'success':('#e7f6ed','#197344'),'error':('#fff0ed','#b43b2f')}
        bg,fg=colors[kind];self.status.setStyleSheet(f'background:{bg};color:{fg};padding:12px;border-radius:7px;font-size:14px;font-weight:600;');self.status.setText(message)
        self.progress.setRange(0,0 if busy else 1);self.progress.setValue(1);self.progress.setVisible(busy)
    def persist(self):atomic_json(self.state_file,self.jobs)
    def render(self):
        self.table.setVisible(bool(self.jobs));self.table.setRowCount(len(self.jobs))
        for i,job in enumerate(self.jobs):
            for col,value in enumerate((job['day'],job['count'],job['status'],job.get('result',''))):self.table.setItem(i,col,QTableWidgetItem(str(value)))
        saving=getattr(self.review,'saving',False);busy=self.running or saving
        self.new_receipt.setEnabled(not busy);self.add.setEnabled(not busy);self.run.setEnabled(not busy);self.output.setEnabled(not busy)
        self.open_report.setEnabled(bool(self.jobs) and not saving)
        same_day=self.reading and getattr(self.review,'day',None) is not None and self.review.day.isoformat()==getattr(self,'active',{}).get('day')
        self.review.setEnabled(not saving and not same_day and (not self.running or self.reading))

    def add_images(self):
        sources,_=QFileDialog.getOpenFileNames(self,'Chọn phiếu giao cho ngày '+self.day.text(),str(self.input),'Ảnh (*.jpg *.jpeg *.png *.webp *.heic *.heif)')
        if not sources:return
        day=self.day.date().toPython();self.running=True;self.render();self.feedback(f'Đang thêm {len(sources)} ảnh · Chưa bắt đầu đọc phiếu…','busy',True)
        from receiving_qt import Worker
        def work():return import_images(self.root/'CauHinh',day,list(map(Path,sources)),self.root/'DuLieu',progress=task.signals.progress.emit)
        def ready(images):
            job=next((j for j in self.jobs if j['day']==day.isoformat()),None)
            if job is None:job=dict(day=day.isoformat(),count=0,status='Chờ đọc');self.jobs.append(job)
            job['count']+=len(images);job['status']='Chờ đọc';self.persist();self.feedback('Đã thêm '+str(len(images))+' ảnh · Chờ đọc. Bấm Đọc phiếu để bắt đầu.','success')
            self.table.selectRow(self.jobs.index(job))
        def failed(message):self.feedback('Thêm ảnh không thành công: '+message,'error')
        def finished():self.running=False;self.render()
        task=Worker(work);task.signals.progress.connect(lambda message:self.feedback('Đang thêm ảnh · '+message,'busy',True));task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished);self.owner._start_worker(task)
    def start(self):
        if self.running:return
        pending=[j for j in self.jobs if j['status']!='Đã đọc']
        if not pending:
            self.feedback('Không có ảnh chờ đọc. Chọn ngày rồi bấm Thêm ảnh.' if not self.jobs else 'Các ngày đã đọc xong. Chọn ngày rồi bấm Kiểm phiếu.');return
        try:
            template=Path('C:/Users/Fenn/Desktop/Công việc/Kế toán/Phieu giao hang hang thang/Phieu giao hang ngay X.xlsx')
            self.profile=profile(self.root,self.owner.root,template if template.exists() else None)
        except (OSError,ValueError) as exc:self.feedback('Chưa bắt đầu đọc: '+str(exc),'error');return
        self.queue=list(pending);self.batch=list(pending);self.batch_done=0;self.running=True;self.reading=True;self.render();self.next_job()
    def next_job(self):
        if not self.queue:
            self.running=False;self.reading=False;self.render()
            failed=[j for j in self.batch if j['status']!='Đã đọc']
            receipts=sum(j.get('receipts',0) for j in self.batch);rows=sum(j.get('rows',0) for j in self.batch)
            if failed:self.feedback(f'Chưa hoàn tất · {len(failed)}/{len(self.batch)} ngày gặp lỗi. Kết quả đã đọc vẫn được giữ. '+str(failed[0].get('error','Bấm Chi tiết để xem bước thất bại.')),'error')
            else:
                self.feedback(f'Đã đọc xong {len(self.batch)} ngày · {receipts} phiếu · {rows} dòng. Chọn ngày rồi bấm Kiểm phiếu.','success')
                self.table.selectRow(self.jobs.index(self.batch[-1]))
                QApplication.alert(self.window(),0)
            return
        self.active=self.queue.pop(0);self.active['status']='Đang đọc';self.persist();self.render();self.table.selectRow(self.jobs.index(self.active));self.feedback(f'Đang đọc ngày {self.active["day"]} · {self.batch_done}/{len(self.batch)} ngày xong…','busy',True)
        self.progress_buffer='';self.image_progress='';self.last_detail='';self.decoder=codecs.getincrementaldecoder('utf-8')(errors='replace');self.proc=QProcess(self);self.proc.setProcessChannelMode(QProcess.MergedChannels)
        env=QProcessEnvironment.systemEnvironment();env.insert('REC_DATA_DIR',str(self.profile));env.insert('REC_DEBT_MODE','1');env.remove('REC_SELECTED_IMAGE_HASHES')
        if not env.value('GEMINI_API_KEY'):
            key=self.owner.root/'gemini_api_key.txt'
            if key.is_file():env.insert('GEMINI_API_KEY',key.read_text(encoding='utf-8-sig').strip())
        self.proc.setProcessEnvironment(env);self.proc.setWorkingDirectory(str(self.profile))
        from rec_runtime import process_command
        program,args=process_command('worker',[self.active['day'],str(self.root/'DuLieu')],self.profile)
        self.proc.readyReadStandardOutput.connect(self.read_log);self.proc.finished.connect(self.completed);self.proc.errorOccurred.connect(self.process_error)
        self.proc.start(program,args)
    def read_log(self):
        text=self.decoder.decode(bytes(self.proc.readAllStandardOutput()))
        key=self.proc.processEnvironment().value('GEMINI_API_KEY')
        if key:text=text.replace(key,'[KEY]')
        self.log.appendPlainText(text.rstrip())
        if text.strip():
            self.last_detail=text.strip().splitlines()[-1][:500]
            try:
                folder=self.root/'LichSu';folder.mkdir(exist_ok=True)
                with (folder/(self.active['day']+'.log')).open('a',encoding='utf-8') as handle:handle.write(text)
            except OSError:pass
        self.progress_buffer+=text
        while '\n' in self.progress_buffer:
            line,self.progress_buffer=self.progress_buffer.split('\n',1)
            if line.startswith('REC_IMAGE_PROGRESS '):
                self.image_progress=line.split(' ',1)[1].strip()
        lines=[line for line in text.strip().splitlines() if not line.startswith('REC_IMAGE_PROGRESS ')]
        detail=lines[-1][:180] if lines else 'Đang lưu / đối chiếu…'
        self.feedback(f'Ngày {self.active["day"]} · Đã xử lý {self.image_progress or "0/?"} ảnh · '+detail,'busy',True)
    def process_error(self,error):
        if error==QProcess.FailedToStart:self.completed(-1,QProcess.CrashExit)
    def completed(self,code,*_):
        if not self.running:return
        self.read_log();job=self.active;self.proc.deleteLater()
        _,report=paths(self.profile,date.fromisoformat(job['day']),self.root/'DuLieu')
        def finalize():
            from rec_debt_vat import defaults
            if report.exists():defaults(self.root,report)
            data=snapshot(report)[1] if report.exists() else []
            return len(data),sum(len(rows) for _,rows in data)
        self.feedback('Đang lưu kết quả và áp dụng VAT NCC đã chọn…','busy',True)
        from receiving_qt import Worker
        task=Worker(finalize)
        def done(result):
            receipts,rows=result;job.update(receipts=receipts,rows=rows)
            job['status']='Đã đọc' if code==0 and rows else 'Chưa hoàn tất'
            job['result']=f'{receipts} phiếu · {rows} dòng'
            if code!=0:job['error']=getattr(self,'last_detail','') or f'Tiến trình kết thúc với mã {code}'
            else:job.pop('error',None)
        def error(message):job['status']='Chưa hoàn tất';job['error']=message;job['result']=message
        def finished():self.persist();self.batch_done+=1;self.next_job()
        task.signals.result.connect(done);task.signals.error.connect(error);task.signals.finished.connect(finished);self.owner._start_worker(task)
    def open_selected_report(self):
        index=self.table.currentRow()
        if not 0<=index<len(self.jobs):return
        _,report=paths(self.root/'CauHinh',date.fromisoformat(self.jobs[index]['day']),self.root/'DuLieu')
        if report.is_file():self.review.load_day(date.fromisoformat(self.jobs[index]['day']))
        else:self.status.setText('Ngày này chưa có kết quả. Bấm Đọc phiếu trước.')
    def export_file(self):
        index=self.table.currentRow()
        day=date.fromisoformat(self.jobs[index]['day']) if 0<=index<len(self.jobs) else self.day.date().toPython()
        filename,_=QFileDialog.getSaveFileName(self,'Xuất công nợ ngày '+day.strftime('%d/%m/%Y'),str(self.root/('CongNo_'+day.isoformat()+'_'+datetime.now().strftime('%H%M%S')+'.xlsx')),'Excel (*.xlsx)')
        if not filename:return
        self.running=True;self.render();self.feedback('Đang xuất Excel…','busy',True)
        from receiving_qt import Worker
        task=Worker(export,self.root,filename,day)
        task.signals.result.connect(lambda count:self.feedback('Đã xuất xong '+str(count)+' dòng: '+filename,'success'))
        task.signals.error.connect(lambda message:self.feedback('Chưa xuất được: '+message,'error'))
        task.signals.finished.connect(lambda:(setattr(self,'running',False),self.render()));self.owner._start_worker(task)

def show(w):
    if not w._leave_pr():return
    page=getattr(w,'debt_page',None)
    if page is not None and page.root!=workspace(w.destination):
        if page.running or getattr(page.review,'saving',False):
            QMessageBox.information(w,'Đang đọc công nợ','Chờ hàng đợi cũ hoàn tất trước khi đổi thư mục dữ liệu.');return
        w.main_pages.removeWidget(page);page.deleteLater();page=None
    if page is None:
        page=DebtPage(w);w.debt_page=page;w.main_pages.addWidget(page)
    w.main_pages.setCurrentWidget(page)
