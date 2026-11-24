"""Screen37 shared operational feedback; never fabricates live failures."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDialog,QDialogButtonBox
from rec_pr_surface import flat_page

def show(w,kind,message='',retry=None):
 previous=getattr(w,'feedback_state_page',None)
 if previous is not None:w.main_pages.removeWidget(previous);previous.deleteLater()
 if kind=='empty':return empty_day(w,retry)
 page=QWidget();page.setObjectName('feedbackStatePage');QVBoxLayout(page);w.feedback_state_page=page
 content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18)
 definitions={
 'save-error':('Chưa lưu được thay đổi.','Đóng file trong Excel/WPS nếu đang mở rồi thử lưu lại. Kết quả đọc được giữ.','Thử lưu lại'),
 'source-changed':('Nguồn vừa thay đổi.','Chưa ghi sổ phiếu này. Tải lại dữ liệu để kiểm tra.','Tải lại'),
 'empty':('Chưa có phiếu trong ngày.','Chọn ngày khác hoặc thêm ảnh.','Thêm ảnh'),
 'load-error':('Chưa tải được dữ liệu.','Kiểm tra nguồn và tải lại. Kết quả đang có được giữ nếu có thể.','Tải lại'),
 'loading':('Đang tải sổ…','Giữ bảng cũ trong khi chờ; vẫn chuyển trang được.','')}
 title,description,button=definitions[kind];banner=QLabel('<b>'+title+'</b><br>'+description);banner.setWordWrap(True);banner.setStyleSheet('background:'+('#f7f5ff' if kind in ['empty','loading'] else '#fffaf0')+';border:1px solid #e8e3ff;border-radius:9px;padding:14px 16px;color:#746d9c;');v.addWidget(banner)
 detail=QLabel(message);detail.setWordWrap(True);detail.setObjectName('feedbackStateDetail');v.addWidget(detail)
 action=QPushButton(button);action.setObjectName('feedbackStateRetry');action.setVisible(bool(button));action.setEnabled(retry is not None)
 if retry:
  def run():
   if w.busy:return
   action.setEnabled(False);retry()
  action.clicked.connect(run)
 row=QHBoxLayout();row.addStretch();row.addWidget(action);v.addLayout(row)
 box=QDialogButtonBox(QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Cancel).setText('Kiểm tra phiếu');box.rejected.connect(lambda:w.main_pages.setCurrentWidget(w.receipt_page))
 notice=QLabel('Không báo thành công khi dữ liệu chưa lưu. Thao tác thử lại vẫn kiểm tra nguồn trước khi ghi.')
 flat_page(page,'Lỗi, tải, chưa lưu và dữ liệu trống','Cùng một ngôn ngữ phản hồi trên mọi trang',content,notice,box);notice.hide();page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#feedbackStatePage {background:white;}')
 for label in page.findChildren(QLabel):
  if label.text()=='PR & đối chiếu / Lỗi, tải, chưa lưu và dữ liệu trống':label.setText('Xác nhận / Lỗi, tải, chưa lưu và dữ liệu trống')
 w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page

def leave_comparison(w):
 if not getattr(w,'pr_dirty',lambda:False)():return True
 dialog=QDialog(w);dialog.setObjectName('unsavedComparisonDialog');dialog.setWindowTitle('Rời trang có thay đổi chưa lưu');dialog.resize(560,210)
 v=QVBoxLayout(dialog);v.setContentsMargins(24,24,24,24);v.setSpacing(18)
 heading=QLabel('Rời trang có thay đổi chưa lưu');heading.setStyleSheet('font-size:18px;font-weight:600;color:#29334c;');v.addWidget(heading);v.addWidget(QLabel('Bạn muốn lưu đối chiếu trước khi chuyển trang?'))
 actions=QHBoxLayout();actions.addStretch();state={'leave':False}
 def stay():dialog.reject()
 def discard():w.pr_discard();state['leave']=True;dialog.accept()
 def save():
  if w.pr_save():state['leave']=True;dialog.accept()
 for text,callback in [('Ở lại',stay),('Bỏ thay đổi',discard),('Lưu rồi chuyển',save)]:
  button=QPushButton(text);button.setFixedHeight(36);button.clicked.connect(callback);actions.addWidget(button)
  button.setStyleSheet('background:'+('#6054d8;color:white;' if text=='Lưu rồi chuyển' else 'white;color:#59657a;')+'border:1px solid #e0e4ee;border-radius:7px;padding:0 12px;')
 v.addLayout(actions);dialog.exec();return state['leave']


def empty_day(w,retry):
 from PySide6.QtCore import Qt
 from PySide6.QtWidgets import QDateEdit,QFrame,QScrollArea,QStyle,QLayout,QSizePolicy
 page=QWidget();page.setObjectName('emptyReceiptPage');w.feedback_state_page=page
 outer=QVBoxLayout(page);outer.setContentsMargins(28,24,28,24);outer.setSpacing(16)
 heading=QLabel('Kiểm tra phiếu');heading.setObjectName('emptyPageHeading');outer.addWidget(heading)
 subtitle=QLabel('Xem và đối chiếu các phiếu giao hàng theo ngày.');subtitle.setWordWrap(True);subtitle.setObjectName('emptyPageSubtitle');outer.addWidget(subtitle)
 scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);outer.addWidget(scroll,1)
 body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,24,0,24);layout.addStretch(1)
 card=QFrame();card.setObjectName('emptyReceiptCard');card.setMaximumWidth(640);card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)
 v=QVBoxLayout(card);v.setSizeConstraint(QLayout.SetMinimumSize);v.setContentsMargins(32,32,32,32);v.setSpacing(16)
 icon=QLabel();icon.setPixmap(page.style().standardIcon(QStyle.SP_FileDialogDetailedView).pixmap(28,28));icon.setObjectName('emptyReceiptIcon');icon.setFixedSize(56,56);icon.setAlignment(Qt.AlignCenter);v.addWidget(icon,0,Qt.AlignHCenter)
 title=WrappingLabel('Chưa có phiếu trong ngày');title.setObjectName('emptyReceiptTitle');title.setWordWrap(True);title.setAlignment(Qt.AlignCenter);v.addWidget(title)
 description=WrappingLabel('Thêm ảnh phiếu giao hàng để bắt đầu kiểm tra,\nhoặc chọn ngày khác để xem các phiếu đã có.');description.setObjectName('emptyReceiptDescription');description.setWordWrap(True);description.setAlignment(Qt.AlignCenter);v.addWidget(description)
 label=QLabel('Ngày làm việc');label.setAlignment(Qt.AlignCenter);v.addWidget(label)
 date=QDateEdit();date.setObjectName('emptyReceiptDate');date.setCalendarPopup(True);date.setDisplayFormat('dd/MM/yyyy');date.setDate(w.date_edit.date());date.setMinimumWidth(160);date.setAccessibleName('Ngày làm việc');v.addWidget(date,0,Qt.AlignHCenter)
 primary=QPushButton('Thêm ảnh phiếu giao');primary.setObjectName('emptyReceiptAdd');primary.setMinimumHeight(42);primary.setEnabled(retry is not None)
 def add_images():
  if not w.busy and retry:retry()
 primary.clicked.connect(add_images);v.addWidget(primary)
 secondary=QPushButton('Xem phiếu theo ngày');secondary.setObjectName('emptyReceiptOpen');secondary.setMinimumHeight(40)
 def open_selected():
  if w.busy:return
  if date.date()==w.date_edit.date():w.open_day()
  else:w.date_edit.setDate(date.date())
 secondary.clicked.connect(open_selected);v.addWidget(secondary)
 card_row=QHBoxLayout();card_row.addStretch(1);card_row.addWidget(card,4);card_row.addStretch(1);layout.addLayout(card_row);layout.addStretch(2);layout.setSizeConstraint(QLayout.SetMinimumSize);scroll.setWidget(body)
 page.setStyleSheet('''
 QWidget#emptyReceiptPage,QScrollArea,QScrollArea>QWidget>QWidget {background:#f8f9fc;color:#475569;font-family:"Segoe UI";font-size:13px;}
 QLabel {background:transparent;border:0;max-height:16777215px;}
 QLabel#emptyPageHeading {font-size:22px;font-weight:600;color:#26324b;}
 QLabel#emptyPageSubtitle {color:#64748b;}
 QFrame#emptyReceiptCard {background:white;border:1px solid #e4e7ef;border-radius:16px;}
 QLabel#emptyReceiptIcon {background:#efecff;color:#6554d9;border-radius:16px;font-size:26px;}
 QLabel#emptyReceiptTitle {font-size:22px;font-weight:600;color:#26324b;}
 QLabel#emptyReceiptDescription {color:#64748b;font-size:14px;}
 QDateEdit {background:white;border:1px solid #dce1ec;border-radius:8px;padding:8px;color:#334155;min-height:24px;}
 QPushButton {border:1px solid #dce1ec;border-radius:8px;background:white;color:#475569;padding:0 18px;font-size:14px;}
 QPushButton:hover {background:#f3f1ff;border-color:#a99cec;}
 QPushButton#emptyReceiptAdd {background:#6554d9;border-color:#6554d9;color:white;font-weight:600;}
 QPushButton#emptyReceiptAdd:hover {background:#5543c6;}
 QPushButton:disabled {background:#eceaf5;color:#9693a8;}
 QPushButton:focus,QDateEdit:focus {border:2px solid #9182e5;}
 ''')
 w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page


class WrappingLabel(QLabel):
 """Reserve enough height for the actual styled font at the current width."""
 def resizeEvent(self,event):
  super().resizeEvent(event)
  required=self.heightForWidth(self.width())
  if required>0 and self.minimumHeight()!=required:self.setMinimumHeight(required)
