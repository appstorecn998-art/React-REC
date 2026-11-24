"""Screen42 actual, verified PR images and scoped metadata, hosted inside REC."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,QPushButton,QDialogButtonBox
from rec_pr_surface import flat_page
import receiving_pr_library as library

def show(w,key):
 old=getattr(w,'pr_pages_page',None)
 if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
 page=QWidget();page.setObjectName('prPagesPage');QVBoxLayout(page);w.pr_pages_page=page
 record=library.load(w.pr_library_directory()).get(key)
 if not record:w.show_top_notice('Chưa mở được bộ PR','PR đã không còn trong thư viện.',variant='warning');return
 content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(16);bar=QHBoxLayout();previous=QPushButton('Trang trước');following=QPushButton('Trang sau');counter=QLabel();counter.setObjectName('prPagesCounter');bar.addWidget(previous);bar.addWidget(counter);bar.addWidget(following);bar.addStretch();v.addLayout(bar)
 from receiving_qt import PreviewView
 preview=PreviewView();preview.setFixedHeight(380)
 from PySide6.QtGui import QBrush,QColor
 preview.setBackgroundBrush(QBrush(QColor('#fffcf5')));v.addWidget(preview)
 grid=QGridLayout();grid.setHorizontalSpacing(18);grid.setVerticalSpacing(18);edits={}
 for i,(field,label) in enumerate([('number','Số PR'),('supplier','NCC'),('date','Ngày PR'),('department','Bộ phận')]):
  wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);caption=QLabel(label);caption.setStyleSheet('color:#7b869a;font-size:11px;');edit=QLineEdit(str(record.get(field) or ''));edit.setObjectName('prPages_'+field);edits[field]=edit;column.addWidget(caption);column.addWidget(edit);grid.addWidget(wrap,i//2,i%2)
 grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);v.addLayout(grid);status=QLabel();status.setObjectName('prPagesStatus');status.setWordWrap(True);v.addWidget(status)
 box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);choose=box.button(QDialogButtonBox.Save);choose.setText('Chọn bộ PR này');save=box.button(QDialogButtonBox.Cancel);save.setText('Lưu thông tin nhận diện')
 notice=QLabel('Thông tin nhận diện không thay đổi lượng đặt; các trang thuộc một bộ PR đã chọn.')
 flat_page(page,'Xem bộ PR nhiều trang','PR '+str(record.get('number') or 'chưa rõ số')+' · Kiểm tra ảnh trước khi gán',content,notice,box);page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#prPagesPage {background:white;}')
 state={'page':0,'paths':list(record.get('images',{}))}
 def display():
  count=len(state['paths']);index=state['page'];counter.setText(f'Trang {index+1 if count else 0} / {count}');previous.setEnabled(index>0);following.setEnabled(index<count-1)
  try:
   # Validate the entire set, not just the visible page, before enabling selection.
   paths=library.images_for(record);choose.setEnabled(bool(paths));preview.set_image(paths[index]);status.clear()
  except (OSError,ValueError) as exc:preview.clear_image('Ảnh PR mất hoặc đã thay đổi');choose.setEnabled(False);status.setText(str(exc))
 def move(delta):state['page']+=delta;display()
 previous.clicked.connect(lambda:move(-1));following.clicked.connect(lambda:move(1))
 zoom=QPushButton('Phóng to ảnh PR');zoom.setObjectName('enlargePRImage');bar.addWidget(zoom)
 zoom.clicked.connect(lambda:__import__('rec_pr_image_zoom').show(w,key,state['page']))
 def metadata():
  if w.busy:return
  try:
   current=library.load(w.pr_library_directory()).get(key)
   if current!=record:raise ValueError('Thông tin PR đã đổi. Mở lại bộ ảnh trước khi lưu.')
   library.update_metadata(w.pr_library_directory(),key,**{name:edit.text() for name,edit in edits.items()});record.update({name:edit.text().strip()[:200] for name,edit in edits.items()});status.setText('Đã lưu thông tin nhận diện. Lượng đặt và ảnh PR giữ nguyên.')
  except (OSError,ValueError) as exc:status.setText('Chưa lưu: '+str(exc))
 box.rejected.connect(metadata);choose.hide();display();w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
