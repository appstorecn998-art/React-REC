from receiving_evidence import validate,strip,attach
import copy,hashlib
from pathlib import Path
from PySide6.QtCore import Qt,QBuffer,QIODevice
from PySide6.QtGui import QImage,QPixmap,QShortcut,QKeySequence,QIcon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,QFileDialog,QApplication,QDialog,QScrollArea,QLineEdit
class EvidencePanel(QWidget):
 def __init__(self,w,old=None,directory=None,parent=None):
  super().__init__(parent);self.setObjectName('approvalEvidencePanel');self.owner=w;self.entries=[];self.directory=Path(directory) if directory else (Path(w.ledger_path()).parent/'approval-evidence' if callable(getattr(w,'ledger_path',None)) else Path(w.root)/'.receiving/approval-evidence' if getattr(w,'root',None) else None)
  v=QVBoxLayout(self);v.setContentsMargins(0,0,0,0);v.setSpacing(8)
  title=QLabel('Ảnh bằng chứng / xác nhận');title.setStyleSheet('font-weight:600;color:#334155;');v.addWidget(title)
  hint=QLabel('Chọn ảnh hoặc dán ảnh chụp đoạn chat, email, phiếu có xác nhận. Ảnh được sao lưu khi bạn xác nhận; không gửi lên mạng.');hint.setWordWrap(True);v.addWidget(hint)
  self.list=QListWidget();self.list.setObjectName('approvalEvidenceList');self.list.setIconSize(__import__('PySide6.QtCore',fromlist=['QSize']).QSize(60,44));self.list.setFixedHeight(76);v.addWidget(self.list)
  row=QHBoxLayout();v.addLayout(row)
  for text,callback,name in [('Thêm ảnh…',self.choose,'addApprovalEvidence'),('Dán ảnh',self.paste,'pasteApprovalEvidence'),('Xem ảnh',self.view,'viewApprovalEvidence'),('Bỏ ảnh',self.remove,'removeApprovalEvidence')]:
   button=QPushButton(text);button.setObjectName(name);button.clicked.connect(lambda checked=False,callback=callback:callback());row.addWidget(button)
  history=QPushButton('Xem ảnh các lần xác nhận trước');history.setObjectName('approvalEvidenceHistory');history.clicked.connect(lambda:self.show_history(old or {}));v.addWidget(history);history.setEnabled(bool((old or {}).get('attachment_history') or any(e.get('attachments') for e in (old or {}).get('history',[]))))
  self.status=QLabel();self.status.setWordWrap(True);self.status.setText((old or {}).get('_evidence_history_error',''));v.addWidget(self.status)
  for ref in (old or {}).get('attachments',[]):self.entries.append(dict(ref=copy.deepcopy(ref),image=None,name=ref.get('name') or 'Ảnh xác nhận đã lưu'))
  hint.setVisible(False);hint.setToolTip(hint.text());self.setToolTip(hint.text())
  self.refresh();self.list.itemDoubleClicked.connect(lambda *_:self.view())
  shortcut=QShortcut(QKeySequence.Paste,self);shortcut.setContext(Qt.WidgetWithChildrenShortcut);shortcut.activated.connect(self.paste)
 def refresh(self):
  current=self.list.currentRow();self.list.clear();self.list.setVisible(bool(self.entries))
  for data in self.entries:
   image=data['image']
   if image is None:
    try:validate([data['ref']]);image=QImage(data['ref']['path'])
    except (OSError,ValueError,KeyError):image=QImage()
   item=QListWidgetItem(data['name']+(' · Không đọc được / đã thay đổi' if image.isNull() else ''));item.setToolTip(data['name'])
   if not image.isNull():item.setIcon(QIcon(QPixmap.fromImage(image)))
   self.list.addItem(item)
  if self.entries:self.list.setCurrentRow(max(0,min(current,len(self.entries)-1)))
 def add_image(self,image,name='Ảnh xác nhận'):
  if image.isNull():self.status.setText('Không đọc được ảnh. Chọn tệp ảnh hợp lệ.');return False
  if image.width()*image.height()>60000000:self.status.setText('Ảnh quá lớn. Chọn ảnh chụp gọn hơn.');return False
  self.entries.append(dict(ref=None,image=image.copy(),name=name));self.refresh();self.list.setCurrentRow(len(self.entries)-1);self.status.setText('Ảnh mới sẽ lưu cùng lần xác nhận này.');return True
 def choose(self):
  paths,_=QFileDialog.getOpenFileNames(self,'Chọn ảnh bằng chứng','','Ảnh (*.png *.jpg *.jpeg *.webp *.bmp)')
  for path in paths:self.add_image(QImage(path),Path(path).name)
 def paste(self):
  clipboard=QApplication.clipboard();image=clipboard.image()
  if image.isNull():
   urls=clipboard.mimeData().urls()
   if len(urls)==1 and urls[0].isLocalFile():image=QImage(urls[0].toLocalFile())
  return self.add_image(image,'Ảnh dán '+str(len(self.entries)+1))
 def remove(self):
  row=self.list.currentRow()
  if row>=0:self.entries.pop(row);self.refresh();self.status.setText('Đã bỏ khỏi lần xác nhận này. Bản ảnh và lịch sử cũ vẫn được giữ.')
 def view(self,ref=None):
  try:
   if ref is not None:validate([ref]);image=QImage(ref['path'])
   else:
    row=self.list.currentRow()
    if row<0:return
    data=self.entries[row]
    if data['image'] is None:validate([data['ref']]);image=QImage(data['ref']['path'])
    else:image=data['image']
   if image.isNull():raise ValueError('Không đọc được ảnh bằng chứng.')
   dialog=QDialog(self);dialog.setWindowTitle('Ảnh bằng chứng');dialog.resize(900,700);v=QVBoxLayout(dialog);scroll=QScrollArea();label=QLabel();label.setPixmap(QPixmap.fromImage(image));scroll.setWidget(label);v.addWidget(scroll);dialog.setAttribute(Qt.WA_DeleteOnClose);dialog.open();self.viewer=dialog
  except (OSError,ValueError,KeyError) as exc:self.status.setText(str(exc))
 def show_history(self,old):
  events=old.get('attachment_history',[])+old.get('history',[]);refs=[]
  dialog=QDialog(self);dialog.setWindowTitle('Ảnh các lần xác nhận trước');v=QVBoxLayout(dialog);listing=QListWidget();v.addWidget(listing)
  for event in events:
   for ref in event.get('attachments',[]):
    if (event.get('time'),ref) in refs:continue
    refs.append((event.get('time'),ref));listing.addItem(str(event.get('time') or event.get('date') or '')+' · '+('Bỏ duyệt' if event.get('action')=='revoke' else 'Xác nhận')+' · '+str(ref.get('name') or 'Ảnh xác nhận'))
  listing.itemDoubleClicked.connect(lambda item:self.view(refs[listing.row(item)][1]));dialog.resize(650,400);dialog.setAttribute(Qt.WA_DeleteOnClose);dialog.open();self.history_viewer=dialog
 def persist(self):
  refs=[]
  from rec_runtime import atomic_bytes
  for data in self.entries:
   if data['image'] is None:validate([data['ref']]);refs.append(copy.deepcopy(data['ref']));continue
   image=data['image'];buffer=QBuffer();buffer.open(QIODevice.WriteOnly)
   if not image.save(buffer,'PNG'):raise ValueError('Không lưu được ảnh bằng chứng.')
   if self.directory is None:raise ValueError('Chưa xác định được thư mục lưu bằng chứng. Mở lại phiếu trong REC.')
   raw=bytes(buffer.data());sha=hashlib.sha256(raw).hexdigest();target=self.directory/(sha+'.png')
   from multi_delivery import output_lock
   target.parent.mkdir(parents=True,exist_ok=True)
   with output_lock(target):
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=sha:raise ValueError('Ảnh bằng chứng lưu trên máy đã thay đổi.')
    if not target.exists():atomic_bytes(target,raw)
   ref=dict(path=str(target.resolve()),sha256=sha,width=image.width(),height=image.height(),name=data['name'])
   data['ref']=copy.deepcopy(ref);data['image']=None
   if ref not in refs:refs.append(ref)
  return refs
