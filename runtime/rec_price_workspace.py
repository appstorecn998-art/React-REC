"""Price workspace and one-per-change daily price notifications."""
from datetime import date
from PySide6.QtCore import QDate,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDateEdit,QTabWidget,QDialog,QScrollArea
from shiboken6 import isValid

def day_changes(result,day):
 found=[];iso=day.isoformat()
 for warning in result['warnings']:
  today=[e for e in warning['entries'] if e['day']==iso];prior=[e for e in warning['entries'] if e['day']<iso]
  if not today or not prior:continue
  from decimal import Decimal
  old={Decimal(e['price']) for e in prior};new={Decimal(e['price']) for e in today}
  if any(price!=previous for price in new for previous in old):found.append(dict(warning,today=today,prior=prior))
 return found

def notify_day(w,result):
 if not isValid(w) or w.busy or w.main_pages.currentWidget() is not w.receipt_page:return
 changed=day_changes(result,w.day)
 if not changed:return
 key=(str(w.destination),w.day.isoformat(),tuple(sorted((r['key'],tuple(sorted({e['price'] for e in r['today']})),tuple(sorted({e['price'] for e in r['prior']}))) for r in changed)))
 seen=getattr(w,'_price_popup_seen',set())
 if key in seen:return
 existing=getattr(w,'_price_warning_popup',None)
 if existing is not None and isValid(existing) and existing.isVisible():return
 seen.add(key);w._price_popup_seen=seen
 dialog=QDialog(w);dialog.setObjectName('dailyPriceWarning');dialog.setWindowTitle('Cần rà đơn giá trong ngày');dialog.setModal(False);dialog.resize(820,560);v=QVBoxLayout(dialog);v.setContentsMargins(24,24,24,24);v.setSpacing(14)
 heading=QLabel(str(len(changed))+' mặt hàng có giá khác trong tháng');heading.setStyleSheet('font-size:19px;font-weight:600;color:#8a5209;');v.addWidget(heading)
 intro=QLabel('Ngày '+w.day.strftime('%d/%m/%Y')+' có giá khác một hoặc nhiều lần mua trước trong tháng. Ngày bên dưới là ngày lưu phiếu trong REC. Kiểm tra quy cách, VAT và chiết khấu trước khi kết luận.');intro.setWordWrap(True);v.addWidget(intro)
 scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();items=QVBoxLayout(body)
 for change in changed:
  label=QLabel(change_description(change,rich=True));label.setObjectName('dailyPriceItem');label.setWordWrap(True);label.setTextFormat(Qt.RichText);label.setStyleSheet('background:#fff8ed;border:1px solid #f1dfbd;border-radius:7px;padding:12px;color:#5a4b35;max-height:16777215px;');items.addWidget(label)
 items.addStretch();scroll.setWidget(body);v.addWidget(scroll,1)
 footer=QHBoxLayout();close=QPushButton('Đã xem');details=QPushButton('Mở trang Giá mua');footer.addWidget(close);footer.addStretch();footer.addWidget(details);v.addLayout(footer);close.clicked.connect(dialog.accept)
 def open_details():
  dialog.accept();w.fluent_nav.set_current('Giá mua')
  if w.main_pages.currentWidget() is not getattr(w,'price_workspace',None):show(w)
 details.clicked.connect(open_details);dialog.setStyleSheet('QDialog {background:white;font-family:"Segoe UI";font-size:13px;} QPushButton {min-height:36px;padding:0 16px;}');dialog.setAttribute(Qt.WA_DeleteOnClose);w._price_warning_popup=dialog;dialog.open()

def show(w):
 page=getattr(w,'price_workspace',None)
 if page is not None:
  w.main_pages.setCurrentWidget(page);page.refresh_prices();return page
 page=QWidget();page.setObjectName('priceWorkspace');w.price_workspace=page;v=QVBoxLayout(page);v.setContentsMargins(24,24,24,24);v.setSpacing(14)
 title=QLabel('Giá mua');title.setStyleSheet('font-size:23px;font-weight:600;color:#26324b;');v.addWidget(title)
 intro=QLabel('Theo dõi và kiểm tra đơn giá mua theo tháng.');v.addWidget(intro)
 tools=QHBoxLayout();tools.addWidget(QLabel('Tháng theo dõi'));month=QDateEdit();month.setObjectName('priceWorkspaceMonth');month.setDisplayFormat('MM/yyyy');month.setCalendarPopup(True);month.setDate(QDate(w.day.year,w.day.month,1));tools.addWidget(month);refresh=QPushButton('Tải lại dữ liệu');tools.addWidget(refresh);tools.addStretch();v.addLayout(tools)
 tabs=QTabWidget();v.addWidget(tabs,1);tab=QWidget();layout=QVBoxLayout(tab);layout.setContentsMargins(0,12,0,0);tabs.addTab(tab,'Biến động giá');status=QLabel();status.setWordWrap(True);layout.addWidget(status)
 state={'generation':0,'view':None}
 def load(*_):
  from receiving_monthly_prices import scan
  from receiving_qt import Worker
  state['generation']+=1;generation=state['generation'];root=w.root;destination=w.destination;selected=month.date().toPython();status.setText('Đang kiểm tra giá tháng '+month.date().toString('MM/yyyy')+'…');refresh.setEnabled(False)
  def ready(result):
   if not isValid(page) or generation!=state['generation']:return
   if w.root!=root or w.destination!=destination:status.setText('Nơi lưu dữ liệu đã đổi. Tải lại để kiểm tra.');return
   from rec_monthly_prices import show as build
   new=build(w,result,load,embedded=True)
   old=state['view']
   if old is not None:layout.removeWidget(old);old.hide();old.deleteLater()
   state['view']=new;layout.addWidget(new,1);status.setText('Tháng '+result['month']+' · '+str(len(result['warnings']))+' mặt hàng cần rà')
  def failed(message):
   if isValid(status) and generation==state['generation']:status.setText('Chưa tải được: '+message)
  def finished():
   if isValid(refresh) and generation==state['generation']:refresh.setEnabled(True)
  task=Worker(scan,root,destination,selected);task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished);w._start_worker(task)
 month.dateChanged.connect(load);refresh.clicked.connect(load);page.refresh_prices=load
 page.setStyleSheet('QWidget#priceWorkspace {background:white;color:#475569;font-family:"Segoe UI";font-size:13px;} QDateEdit,QPushButton {min-height:36px;} QTabWidget::pane {border:0;}');w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);load();return page


def change_description(change,rich=False):
 from collections import defaultdict
 from decimal import Decimal
 from html import escape
 from receiving_price_pr import pr_label,format_price
 def safe(value):return escape(str(value)) if rich else str(value)
 def lines(entries):
  groups=defaultdict(set)
  for entry in entries:
   groups[(entry['day'],entry.get('supplier') or 'Chưa rõ NCC',Decimal(entry['price']))].add(pr_label(entry))
  result=[]
  for (day,supplier,price),numbers in sorted(groups.items(),reverse=True):
   money=safe(format_price(price))+' / '+safe(change['unit'])
   if rich:money='<span style="font-size:17px;font-weight:700;color:#334155;">'+money+'</span>'
   pr=safe(', '.join(sorted(numbers)))
   if rich:pr='<span style="font-size:15px;font-weight:700;color:#334155;">PR: '+pr+'</span>'
   else:pr='PR: '+pr
   result.append('• '+safe(date.fromisoformat(day).strftime('%d/%m/%Y'))+' · '+safe(supplier)+'\n  '+money+('&nbsp;&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;&nbsp;' if rich else '    ·    ')+pr)
  return '\n'.join(result)
 text=safe(change['name'])+'\n\nLẦN MUA ĐANG XEM\n'+lines(change['today'])+'\n\nCÁC LẦN MUA TRƯỚC TRONG THÁNG\n'+lines(change['prior'])
 return text.replace('\n','<br>') if rich else text
