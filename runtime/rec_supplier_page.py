"""Screen33: official supplier selection and local nickname; rules remain read-only."""
import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialogButtonBox
from PySide6.QtCore import Qt
from rec_pr_surface import flat_page
from receiving_preferences import nickname,set_nickname

def show(w):
 old=getattr(w,'supplier_design_page',None)
 if old is not None:w.main_pages.setCurrentWidget(old);return old
 page=QWidget();page.setObjectName('supplierDesignPage');QVBoxLayout(page);w.supplier_design_page=page
 content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18);grid=QGridLayout();grid.setHorizontalSpacing(18);supplier=QComboBox();supplier.setObjectName('supplierOfficialName');short=QLineEdit();short.setObjectName('supplierShortName')
 for col,(text,field) in enumerate([('Tên NCC đầy đủ',supplier),('Tên hiển thị ngắn',short)]):
  wrap=QWidget();column=QVBoxLayout(wrap);column.setContentsMargins(0,0,0,0);label=QLabel(text);label.setStyleSheet('font-size:11px;color:#7b869a;');column.addWidget(label);column.addWidget(field);grid.addWidget(wrap,0,col);grid.setColumnStretch(col,1)
 v.addLayout(grid);table=QTableWidget(3,2);table.setObjectName('supplierScopes');table.setHorizontalHeaderLabels(['Thông tin','Phạm vi']);table.verticalHeader().hide();table.setShowGrid(False);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);table.horizontalHeader().setFixedHeight(44)
 for i,values in enumerate([('Tên hiển thị','Chỉ đổi cách hiển thị trên máy'),('Cặp PR ↔ dòng giao đã gán','Đúng NCC / tên / mã / quy cách / đơn vị'),('Quy đổi / quy tắc NCC','Chỉ từ xác nhận nghiệp vụ đã có')]):
  for j,text in enumerate(values):table.setItem(i,j,QTableWidgetItem(text))
  table.setRowHeight(i,49)
 table.setFixedHeight(193);v.addWidget(table);status=QLabel();status.setObjectName('supplierDesignStatus');status.setWordWrap(True);v.addWidget(status)
 box=QDialogButtonBox(QDialogButtonBox.Save);save=box.button(QDialogButtonBox.Save);save.setText('Lưu tên hiển thị');save.setEnabled(False)
 notice=QLabel('Chỉ xem phạm vi các xác nhận đã có. Không thêm tự động học, xóa quy tắc hoặc chỉnh danh mục gốc trong đợt đổi UI.')
 flat_page(page,'NCC và những cặp gán đã nhớ','Tra NCC và tên hiển thị; không suy quy tắc từ AI',content,notice,box);page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'QWidget#supplierDesignPage {background:white;}')
 for label in page.findChildren(QLabel):
  if label.text()=='PR & đối chiếu / NCC và những cặp gán đã nhớ':label.setText('Danh mục & cấu hình / NCC và những cặp gán đã nhớ')
 def selected(*_):
  name=supplier.currentData();short.setText(nickname(w.root,name) if name else '');save.setEnabled(bool(name));status.setText('Tên ngắn chỉ thay cách hiển thị, không đổi tên NCC nghiệp vụ.' if name else 'Chưa có NCC hợp lệ trong danh mục.')
 supplier.currentIndexChanged.connect(selected)
 def save_name():
  if w.busy:status.setText('REC đang xử lý. Chờ hoàn tất trước khi lưu.');return
  name=supplier.currentData()
  if not name:return
  try:set_nickname(w.root,name,short.text());status.setText('Đã lưu tên hiển thị trên máy. Danh mục và quy tắc nghiệp vụ giữ nguyên.')
  except (OSError,ValueError):status.setText('Chưa lưu được tên hiển thị. Kiểm tra quyền ghi cấu hình.')
 box.accepted.connect(save_name)
 from receiving_qt import Worker
 def read():
  from supplier_directory import load_supplier_directory
  return load_supplier_directory(w.root/'DanhMuc.xlsm')
 def ready(directory):
  for code,name in sorted(directory.items()):supplier.addItem(name,name)
  current=sorted({str(x.get('Nhà cung cấp') or '') for _,x in w.data_by_sheet.get(w.current_sheet,[])})
  if len(current)==1 and supplier.findData(current[0])>=0:supplier.setCurrentIndex(supplier.findData(current[0]))
  selected()
 job=Worker(read);job.signals.result.connect(ready);job.signals.error.connect(lambda _:status.setText('Chưa đọc được DanhMucNCC. Kiểm tra danh mục trong Cài đặt.'));w._start_worker(job)
 w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
