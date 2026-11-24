"""Screen34: staged profile settings, masked secrets and offline diagnostics."""
import json,re
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QHBoxLayout,QLabel,QLineEdit,QCheckBox,QPushButton,QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox,QScrollArea,QFrame,QLayout,QTabWidget
from PySide6.QtCore import Qt
from rec_pr_surface import flat_page

def show(w):
 old=getattr(w,'settings_design_page',None)
 if old is not None:w.main_pages.setCurrentWidget(old);return old
 page=QWidget();page.setObjectName('settingsDesignPage');QVBoxLayout(page);w.settings_design_page=page
 root=w.root;runtime=root/'.receiving/runtime.json';settings=root/'.receiving/settings.json';preferences=root/'.receiving/ui-preferences.json'
 def read_dict(path):
  try:
   value=json.loads(path.read_text(encoding='utf-8-sig'))
   if not isinstance(value,dict):raise ValueError('Invalid profile')
   return value
  except FileNotFoundError:return {}
 config_error=False
 try:existing=read_dict(runtime);prefs=read_dict(preferences)
 except (OSError,ValueError):existing={};prefs={};config_error=True
 paths=[runtime,settings,preferences,root/'gemini_api_key.txt',root/'google-sheets-key.json',root/'DanhMuc.xlsm']
 originals={p:p.read_bytes() if p.exists() else None for p in paths};pending={}
 destination=QLineEdit(str(w.destination));destination.setObjectName('settingsDestination')
 sheet=QLineEdit();sheet.setObjectName('settingsSheetId');sheet.setEchoMode(QLineEdit.Password);sheet.setPlaceholderText('Đã cấu hình — để trống để giữ' if existing.get('sheet_id') else 'Để trống để giữ cấu hình hiện có')
 key=QLineEdit();key.setObjectName('settingsGeminiKey');key.setEchoMode(QLineEdit.Password);key.setPlaceholderText('Để trống để giữ khóa đang có')
 sections=[]
 content=QWidget();content.setObjectName('settingsContent');v=QVBoxLayout(content);v.setContentsMargins(10,10,10,10);v.setSpacing(12)
 heading=QLabel('Cài đặt REC');heading.setStyleSheet('font-size:22px;font-weight:600;color:#26324b;');v.addWidget(heading)
 intro=QLabel('Quản lý nơi lưu chứng từ, đọc ảnh và kết nối Google Sheets. Thay đổi chỉ áp dụng khi bấm Lưu cấu hình.');intro.setWordWrap(True);v.addWidget(intro)
 def section(title,description):
  frame=QFrame();frame.setObjectName('settingsSection');layout=QVBoxLayout(frame);layout.setContentsMargins(16,14,16,14);layout.setSpacing(10);layout.setSizeConstraint(QLayout.SetMinimumSize)
  label=QLabel(title);label.setWordWrap(True);label.setStyleSheet('font-size:16px;font-weight:600;color:#334155;');layout.addWidget(label)
  hint=QLabel(description);hint.setWordWrap(True);hint.setStyleSheet('color:#64748b;');layout.addWidget(hint);v.addWidget(frame);sections.append(frame);return layout
 def field(layout,title,widget):
  label=QLabel(title);label.setWordWrap(True);layout.addWidget(label);widget.setAccessibleName(title);layout.addWidget(widget)
 data=section('Dữ liệu và nơi lưu','Thư mục lưu phiếu, ảnh và sổ nhận hàng. Danh mục dùng để tra mã hàng và đơn vị tính.')
 field(data,'Thư mục kế toán',destination)
 folder=QPushButton('Chọn thư mục lưu…');folder.setObjectName('settingsChooseFolder');data.addWidget(folder,0,Qt.AlignLeft)
 if getattr(w,'portable_workspace',False):
  destination.setReadOnly(True);folder.hide()
 def choose_folder():
  if w.busy or getattr(w,'sheets_sync_running',False):return
  selected=QFileDialog.getExistingDirectory(w,'Chọn thư mục kế toán',destination.text())
  if selected:destination.setText(selected)
 folder.clicked.connect(choose_folder)
 catalog=QPushButton('Chọn tệp DanhMuc.xlsm…');catalog.setObjectName('settingsChooseCatalog');data.addWidget(catalog,0,Qt.AlignLeft)
 ai=section('Đọc ảnh bằng Gemini','Khóa API cho phép REC đọc nội dung ảnh bằng Gemini. Để trống ô dưới nếu không cần đổi khóa đang dùng.')
 field(ai,'Khóa API Gemini mới',key)
 key.setPlaceholderText('Nhập khóa mới khi cần thay đổi')
 sheets=section('Kết nối Google Sheets','Cần mã bảng tính và tệp khóa Google JSON để đồng bộ. Xem và xác nhận dữ liệu trong mục Sheets trước khi gửi.')
 field(sheets,'Mã bảng tính Google Sheets',sheet)
 help_text=QLabel('Lấy phần nằm giữa /d/ và /edit trong đường dẫn Google Sheets. Để trống để giữ mã hiện có.');help_text.setWordWrap(True);sheets.addWidget(help_text)
 google=QPushButton('Chọn tệp khóa Google (.json)…');google.setObjectName('settingsChooseGoogle');sheets.addWidget(google,0,Qt.AlignLeft)
 window=section('Cửa sổ và công cụ hỗ trợ','Tùy chỉnh cửa sổ hoặc mở các công cụ nhận ảnh và khôi phục.')
 remember=QCheckBox('Nhớ kích thước và trạng thái cửa sổ');remember.setObjectName('settingsRememberWindow');remember.setChecked(prefs.get('remember_window',True));window.addWidget(remember)
 diagnostics_layout=section('Kiểm tra cấu hình trên máy','Kiểm tra các tệp và quyền truy cập trên máy. Kết quả này chưa xác nhận kết nối Internet với Gemini hoặc Google Sheets.')
 check=QPushButton('Kiểm tra lại cấu hình trên máy');check.setObjectName('settingsCheckOffline');diagnostics_layout.addWidget(check,0,Qt.AlignLeft)
 table=QTableWidget(0,2);table.setObjectName('settingsDiagnosticsTable');table.setHorizontalHeaderLabels(['Thành phần','Chẩn đoán']);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44);diagnostics_layout.addWidget(table)
 status=QLabel('Thay đổi chỉ được ghi khi bấm Lưu cấu hình.');status.setObjectName('settingsDesignStatus');status.setWordWrap(True);v.addWidget(status)
 box=QDialogButtonBox(QDialogButtonBox.Save);save=box.button(QDialogButtonBox.Save);save.setText('Lưu cấu hình');recovery=box.addButton('Khôi phục / model',QDialogButtonBox.ActionRole);inbox=box.addButton('Nhận ảnh tự động',QDialogButtonBox.ActionRole)
 notice=QLabel('Kiểm tra offline không gửi yêu cầu mạng. Để trống khóa Gemini hoặc mã Sheets sẽ giữ cấu hình đang có; không hiển thị khóa đã lưu.')
 flat_page(page,'Cài đặt và chẩn đoán','Hồ sơ cá nhân lưu riêng trên máy; không hiển thị khóa bí mật',content,notice,box);notice.hide();page.layout().removeWidget(content)
 tabs=QTabWidget();tabs.setObjectName('settingsTabs')
 groups=[('Dữ liệu',[0]),('Kết nối',[1,2]),('Ứng dụng',[3,4])]
 for title,indices in groups:
  tab=QWidget();tab_layout=QVBoxLayout(tab);tab_layout.setContentsMargins(0,10,0,0);tab_layout.setSpacing(12)
  for index in indices:
   frame=sections[index];v.removeWidget(frame);tab_layout.addWidget(frame)
  tab_layout.addStretch()
  scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setWidget(tab);tabs.addTab(scroll,title)
 v.addWidget(tabs,1);page.layout().insertWidget(0,content,1)
 page.settings_tabs=tabs
 for button in [inbox,recovery]:box.removeButton(button);window.addWidget(button,0,Qt.AlignLeft);button.show()
 page.setStyleSheet(page.styleSheet()+'''QWidget#settingsDesignPage,QWidget#settingsContent,QScrollArea {background:#f8f9fc;} QFrame#settingsSection {background:white;border:1px solid #e1e6ef;border-radius:10px;} QLabel {background:transparent;border:0;color:#53617a;max-height:16777215px;} QLineEdit {min-width:120px;} QTabWidget::pane {border:0;} QTabBar::tab {padding:9px 18px;background:#f1f3f8;color:#64748b;border:0;} QTabBar::tab:selected {background:white;color:#6054d8;border-bottom:2px solid #6054d8;}''')
 for label in page.findChildren(QLabel):
  if label.text()=='PR & đối chiếu / Cài đặt và chẩn đoán':label.setText('Danh mục & cấu hình / Cài đặt và chẩn đoán')
 def mutable():return not w.busy and not getattr(w,'sheets_sync_running',False)
 def diagnostics():
  if not check.isEnabled():return
  from receiving_qt import Worker
  from rec_runtime import config_check
  check.setEnabled(False);status.setText('Đang kiểm tra các tệp cấu hình trên máy…')
  def ready(report):
   checks=report['checks'];table.setRowCount(len(checks));names={'catalog':'Danh mục / quy tắc','gemini':'Khóa Gemini','sheets':'Google Sheets','template':'Mẫu xuất phiếu','ocr':'Model OCR','writable':'Quyền ghi hồ sơ'}
   for i,(name,result) in enumerate(checks.items()):
    # Diagnostic content is allowlisted; never echo credential or parser exceptions.
    ok=result['ok'];text=('Đã có cấu hình trên máy' if ok else 'Thiếu hoặc chưa hợp lệ')+(' · Chưa thử kết nối' if name in ['gemini','sheets'] else '')
    table.setItem(i,0,QTableWidgetItem(names.get(name,name)));table.setItem(i,1,QTableWidgetItem(text));table.setRowHeight(i,38)
   table.setFixedHeight(44+38*len(checks)+2);status.setText('Đã kiểm tra cấu hình đã lưu trên máy. Các thay đổi chưa lưu chưa được kiểm tra; kết nối Gemini và Google Sheets chưa được thử.')
  job=Worker(config_check,root);job.signals.result.connect(ready);job.signals.error.connect(lambda _:status.setText('Chưa kiểm tra được hồ sơ. Kiểm tra quyền đọc/ghi và tệp cấu hình.'));job.signals.finished.connect(lambda:check.setEnabled(True));w._start_worker(job)
 def import_google():
  if not mutable():status.setText('Chờ xử lý/đồng bộ kết thúc trước khi đổi cấu hình.');return
  selected,_=QFileDialog.getOpenFileName(w,'Chọn khóa Google JSON','','JSON (*.json)')
  if not selected:return
  try:
   raw=Path(selected).read_bytes();data=json.loads(raw)
   from google.oauth2.service_account import Credentials
   Credentials.from_service_account_info(data,scopes=['https://www.googleapis.com/auth/spreadsheets'])
   pending[root/'google-sheets-key.json']=raw;status.setText('Đã chọn khóa Google hợp lệ. Bấm Lưu cấu hình để áp dụng.')
  except Exception:status.setText('Khóa Google JSON không hợp lệ hoặc không đọc được. Cấu hình đang có được giữ nguyên.')
 def import_catalog():
  if not mutable():status.setText('Chờ xử lý/đồng bộ kết thúc trước khi đổi cấu hình.');return
  selected,_=QFileDialog.getOpenFileName(w,'Chọn DanhMuc.xlsm','','Excel macro (*.xlsm)')
  if not selected:return
  try:
   from AutoWatcher import load_catalog_data
   from supplier_rules import read_rules
   raw=Path(selected).read_bytes();items,groups=load_catalog_data(Path(selected));read_rules(root/'NhaCungCap.json',items,groups);pending[root/'DanhMuc.xlsm']=raw;status.setText('Đã kiểm tra danh mục với quy tắc hiện có. Bấm Lưu cấu hình để áp dụng.')
  except Exception:status.setText('Danh mục không hợp lệ với quy tắc hiện có. Tệp gốc được giữ nguyên.')
 def commit():
  if not mutable():status.setText('Chờ xử lý/đồng bộ kết thúc trước khi lưu cấu hình.');return
  try:
   if config_error:raise ValueError('Hồ sơ cấu hình lỗi định dạng. Khôi phục tệp hợp lệ trước khi ghi đè.')
   raw=destination.text().strip()
   if not raw or not Path(raw).is_absolute() or not Path(raw).is_dir():raise ValueError('Chọn đường dẫn tuyệt đối tới thư mục kế toán đã tồn tại.')
   if sheet.text().strip() and not re.fullmatch('[A-Za-z0-9_-]+',sheet.text().strip()):raise ValueError('Mã Google Sheets không hợp lệ.')
   from receiving_service import accounting_root
   dest=accounting_root(raw)
   if getattr(w,'portable_workspace',False) and dest.resolve()!=w.portable_store:
    raise ValueError('Công cụ này dùng thư mục dữ liệu của React REC.')
   destination_changed=dest!=w.destination
   if destination_changed and (w.inbox_toggle.isChecked() or not w._leave_pr()):raise ValueError('Tắt nhận ảnh tự động và lưu đối chiếu trước khi đổi nơi lưu.')
   writes=dict(pending);updated=dict(existing)
   if sheet.text().strip():updated['sheet_id']=sheet.text().strip()
   writes[runtime]=json.dumps(updated,ensure_ascii=False).encode();writes[settings]=json.dumps(dict(read_dict(settings),destination=str(dest)),ensure_ascii=False).encode();writes[preferences]=json.dumps(dict(read_dict(preferences),remember_window=remember.isChecked()),ensure_ascii=False).encode()
   if key.text().strip():writes[root/'gemini_api_key.txt']=key.text().strip().encode()
   from multi_delivery import output_lock
   from rec_runtime import atomic_bytes
   with output_lock(runtime):
    if any((p.read_bytes() if p.exists() else None)!=originals[p] for p in paths):raise ValueError('Hồ sơ đã đổi bên ngoài. Mở lại Cài đặt trước khi lưu.')
    backup=root/'.receiving/settings-backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');backup.mkdir(parents=True)
    for i,p in enumerate(writes):
     if originals[p] is not None:atomic_bytes(backup/(str(i)+'-'+p.name),originals[p])
    changed=[]
    try:
     for p,data in writes.items():atomic_bytes(p,data);changed.append(p)
    except OSError:
     for p in reversed(changed):
      if originals[p] is None:p.unlink(missing_ok=True)
      else:atomic_bytes(p,originals[p])
     raise
   for p in paths:originals[p]=p.read_bytes() if p.exists() else None
   existing.clear();existing.update(updated);pending.clear();key.clear();sheet.clear();sheet.setPlaceholderText('Đã cấu hình — để trống để giữ');w.destination=dest;w.catalog=None;w._warehouse_cache=None
   if getattr(w,'directory_page',None) is not None:w.main_pages.removeWidget(w.directory_page);w.directory_page.deleteLater();w.directory_page=None
   if getattr(w,'supplier_design_page',None) is not None:w.main_pages.removeWidget(w.supplier_design_page);w.supplier_design_page.deleteLater();w.supplier_design_page=None
   status.setText('Đã lưu cấu hình riêng trên máy và tạo bản dự phòng. Chưa kết nối dịch vụ.')
   if destination_changed:
    w.data=[];w.data_by_sheet={};w.current_sheet='';w.report=None;w.source_hash=None;w.open_day()
  except ValueError as exc:status.setText(str(exc))
  except Exception:status.setText('Chưa lưu được cấu hình. Kiểm tra quyền truy cập; không hiển thị thông tin khóa.')
 google.clicked.connect(import_google);catalog.clicked.connect(import_catalog);check.clicked.connect(diagnostics);box.accepted.connect(commit)
 # Until phases35/36 are built, preserve their established setup controls.
 inbox.clicked.connect(lambda:__import__('rec_inbox_page').show(w));recovery.clicked.connect(lambda:__import__('rec_recovery_page').show(w))
 page.run_diagnostics=diagnostics;w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);diagnostics();return page
