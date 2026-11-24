"""Screen32: background reads from authoritative directories; copy codes only."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLineEdit,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QApplication,QDialogButtonBox
from rec_pr_surface import flat_page
from supplier_rules import normalize_name

class DirectoryPage(QWidget):
 def __init__(self,w):
  super().__init__();self.owner=w;self.entries=[];self.visible_entries=[];self.generation=0;QVBoxLayout(self);self.setObjectName('directoryDesignPage')
  content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18);toolbar=QHBoxLayout();self.kind=QComboBox();self.kind.addItems(['Mã hàng','Mã nhà cung cấp','Mã kho / bộ phận']);self.search=QLineEdit();self.search.setPlaceholderText('Tìm mã hoặc tên');toolbar.addWidget(self.kind);toolbar.addWidget(self.search,1);v.addLayout(toolbar)
  self.table=QTableWidget(0,3);self.table.setObjectName('directoryDesignTable');self.table.setHorizontalHeaderLabels(['Mã','Tên chuẩn / kho','ĐVT / bộ phận']);self.table.verticalHeader().hide();self.table.setShowGrid(False);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);self.table.horizontalHeader().setFixedHeight(44);v.addWidget(self.table)
  self.note=QLabel();self.note.setWordWrap(True);self.note.setObjectName('directoryStatus');v.addWidget(self.note)
  box=QDialogButtonBox(QDialogButtonBox.Save);self.copy=box.button(QDialogButtonBox.Save);self.copy.setText('Sao chép mã đã chọn');self.copy.setEnabled(False);box.accepted.connect(self.copy_code)
  notice=QLabel('Từ dòng phiếu, chọn mã ở cửa sổ tra cứu rồi áp dụng vào đúng dòng. Trang tra cứu chung chỉ sao chép mã.')
  flat_page(self,'Tra cứu danh mục','Chỉ đọc từ DanhMuc.xlsm · Không có sửa / thêm mã gốc',content,notice,box);self.layout().setStretch(self.layout().indexOf(content),0);self.layout().addStretch();self.setStyleSheet(self.styleSheet()+'QWidget#directoryDesignPage {background:white;}')
  for label in self.findChildren(QLabel):
   if label.text()=='PR & đối chiếu / Tra cứu danh mục':label.setText('Danh mục & cấu hình / Tra cứu danh mục')
  self.kind.currentIndexChanged.connect(self.load);self.search.textChanged.connect(self.filter);self.table.itemSelectionChanged.connect(lambda:self.copy.setEnabled(self.table.currentRow()>=0));self.load()
 def load(self,*_):
  from receiving_qt import Worker
  self.generation+=1;generation=self.generation;index=self.kind.currentIndex();path=self.owner.root/'DanhMuc.xlsm';self.note.setText('Đang đọc danh mục…');self.entries=[];self.filter()
  def read():
   if index==0:
    import AutoWatcher as aw
    catalog=aw.load_catalog_data(path)[0];return [(str(k),str(v[0]),str(v[1])) for k,v in catalog.items()]
   if index==1:
    from supplier_directory import load_supplier_directory
    return [(str(k),str(v),'') for k,v in load_supplier_directory(path).items()]
   from warehouse_directory import load_warehouse_directory
   return [(str(k),str(v[0]),str(v[1])) for k,v in load_warehouse_directory(path).items()]
  def ready(entries):
   if generation!=self.generation:return
   self.entries=entries;self.note.setText(f'{len(entries)} mục trong danh mục.');self.filter()
  def failed(_):
   if generation==self.generation:self.entries=[];self.filter();self.note.setText('Không đọc được danh mục. Kiểm tra tệp DanhMuc.xlsm và các sheet bắt buộc trong Cài đặt.')
  job=Worker(read);job.signals.result.connect(ready);job.signals.error.connect(failed);self.owner._start_worker(job)
 def filter(self,*_):
  from rec_table_state import begin,end
  refresh_state=begin(self.table,self.visible_entries)
  query=normalize_name(self.search.text());rows=[r for r in self.entries if query in normalize_name(' '.join(r))];self.table.setRowCount(len(rows))
  for i,row in enumerate(rows):
   for col,text in enumerate(row):cell=QTableWidgetItem(text);cell.setToolTip(text);self.table.setItem(i,col,cell)
   self.table.setRowHeight(i,49)
  self.visible_entries=rows;end(self.table,rows,refresh_state)
  self.table.setFixedHeight(min(470,44+49*max(1,len(rows))+2));self.table.parentWidget().setFixedHeight(self.table.height()+115);self.copy.setEnabled(self.table.currentRow()>=0)
  if self.entries:self.note.setText(f'{len(rows)} kết quả phù hợp.' if rows else 'Không tìm thấy mã hoặc tên phù hợp.')
 def copy_code(self):
  row=self.table.currentRow()
  if row>=0:QApplication.clipboard().setText(self.table.item(row,0).text());self.note.setText('Đã sao chép mã; chưa thay đổi dòng phiếu.')

DirectoryDialog=DirectoryPage
