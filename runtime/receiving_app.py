from receiving_image_archive import image_name, source_digest
"""Receiving desktop app. --worker runs the existing processing engine headlessly."""
from pathlib import Path
from datetime import datetime
import os
import sys

BASE = Path(os.environ.get("REC_DATA_DIR") or Path(__file__).resolve().parent)

def worker():
    import argparse
    import logging
    import builtins
    import multi_delivery as md
    from receiving_service import paths, day_images, accounting_root
    from receiving_pr_auto import register_pages,link_report,possible_pr_continuation
    import receiving_pr_library as pr_library
    day = datetime.strptime(sys.argv[2], '%Y-%m-%d').date()
    destination = Path(sys.argv[3])
    folder, report = paths(BASE, day, destination)
    # Existing engine operates on one input directory; expose exactly the images
    # belonging to the selected accounting day through a disposable input view.
    import tempfile, shutil
    key = os.environ.get('GEMINI_API_KEY','').strip()
    if not key: key = (BASE/'gemini_api_key.txt').read_text(encoding='utf-8-sig').strip()
    def no_prompt(prompt=''):
        raise RuntimeError('File đang mở hoặc cần xác nhận thủ công. Đóng Excel/WPS rồi chạy tiếp trong ứng dụng.')
    builtins.input = no_prompt
    args = argparse.Namespace(input=None, output=report.parent, excel=BASE/'DanhMuc.xlsm',
        rules=BASE/'NhaCungCap.json', timeout=120, receipt_date=day,
        matching_fallback_model='gemini-3.1-flash-lite',
        web_receipts=bool(os.environ.get('REC_SELECTED_IMAGE_HASHES')))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    md.report_path = lambda _args: report
    ledger_path=accounting_root(destination)/'.receiving'/'receiving-ledger.sqlite'
    library_directory=pr_library.library_path(ledger_path)
    pr_pages=[];documents={};pending_count=0
    args.preclassified_documents={}
    source_images=day_images(report.parent)
    from rec_image_selection import select_images
    source_images=select_images(source_images,os.environ.get('REC_SELECTED_IMAGE_HASHES') if '--auto' not in sys.argv else None)
    known_po_pages={
        sha:order_id for order_id,record in pr_library.load(library_directory).items()
        if record.get('order_type')=='po'
        for sha in (record.get('source_ids') or {}).values()
    }
    remembered_orders=set()
    with tempfile.TemporaryDirectory(prefix='receiving-input-') as temp:
        args.input=Path(temp)
        names=set()
        import AutoWatcher as aw
        _,groups=aw.load_catalog_data(args.excel)
        saved_digests=md.saved_image_digests(report)
        def report_progress():
            if not os.environ.get('REC_DEBT_MODE'):return
            saved=md.saved_image_digests(report)
            count=sum(md.stable_image_digest(p) in saved or source_digest(p) in saved or (p.name in documents and documents[p.name].get('document_type')!='delivery') for p in source_images)
            print('REC_IMAGE_PROGRESS '+str(count)+'/'+str(len(source_images)),flush=True)
        report_progress()
        class SavedProgress(logging.Handler):
            def emit(self,record):
                if record.getMessage().startswith('ĐÃ LƯU '):report_progress()
        progress_handler=SavedProgress();logging.getLogger().addHandler(progress_handler)
        previous_document=None
        extraction_errors=[]
        args.failed_image_names=set()
        args.held_image_names=[]
        for image in source_images:
            if image_name(image) in names:raise ValueError('Hai ảnh trùng tên trong thư mục ngày; đổi tên để phân biệt trước khi đọc.')
            names.add(image_name(image))
            import AutoWatcher as aw
            import hashlib,json
            from receiving_service import atomic_json
            source_hash=md.stable_image_digest(image)
            if source_hash is None:raise ValueError('Ảnh đang thay đổi; chờ chép xong rồi thử lại: '+image.name)
            registry=folder/'inbox-documents'/f'{source_hash}.json'
            original_hash=source_digest(image)
            if original_hash in known_po_pages:
                previous_document={'document_type':'po'}
                remembered_orders.add(known_po_pages[original_hash])
                documents[image.name]=previous_document
                logging.info('Bỏ qua ảnh đã lưu: %s (PO đã có trong thư viện).',image.name)
                report_progress()
                continue
            # Completed delivery rows are authoritative and never re-read.
            # Reuse validated reference classification by content hash even if
            # supplier matching rules changed; references are not merchandise.
            document=None
            if registry.is_file():
                try:
                    cached=json.loads(registry.read_text(encoding='utf-8'))
                    aw.validate_batch_document(cached)
                    if cached.get('document_type') in ('pr','po') or (
                        cached.get('document_type')=='other' and cached.get('_po_classification')==1
                    ):
                        document=cached
                except (OSError,ValueError,KeyError,TypeError):pass
            completed=source_hash in saved_digests or original_hash in saved_digests
            if completed:
                logging.info('Bỏ qua ảnh đã lưu: %s (giữ nguyên dữ liệu đã sửa).',image.name)
                document=document or {'document_type':'delivery'}
            elif document is None:
                logging.info('Đang đọc ảnh mới/chưa hoàn tất: %s',image.name)
                try:
                    document=aw.extract_batch_document(image,args,key,groups)['document']
                    aw.validate_batch_document(document)
                except Exception as exc:
                    detail=str(exc).replace(key,'[KEY]') if key else str(exc)
                    status=getattr(exc,'status_code',None) or getattr(exc,'code',None)
                    if status in {401,403}:raise RuntimeError(image.name+': lỗi xác thực/quyền API; dừng để tránh gọi lại vô ích.') from exc
                    extraction_errors.append(image.name+': '+type(exc).__name__)
                    args.failed_image_names.add(image.name)
                    logging.error('Ảnh lỗi %s (%s); giữ cache, tiếp tục ảnh kế.',image.name,type(exc).__name__)
                    shutil.copy2(image,args.input/image.name)
                    previous_document=None
                    continue
                if md.stable_image_digest(image)!=source_hash:raise ValueError('Ảnh đã thay đổi trong khi đọc: '+image.name)
                # Persist only after contextual classification checks below.
            if not completed and possible_pr_continuation(previous_document,document):
                if not args.web_receipts:
                    raise ValueError(image.name+': có dấu hiệu là trang tiếp của PR. Cần xác định loại trang.')
                from ocr_events import emit
                emit('retry_held', 'Có thể là trang tiếp của PR. Kiểm tra loại chứng từ trước khi ghi nhận hàng.',
                     files=image.name)
                args.held_image_names.append(image.name)
                args.failed_image_names.add(image.name)
                shutil.copy2(image,args.input/image.name)
                previous_document=None
                continue
            previous_document=document
            if not completed:
                document['_po_classification']=1
                atomic_json(registry,document)
            if document['document_type']=='delivery' and not completed:
                pending_count+=1
                args.preclassified_documents[source_hash]=document
            documents[image.name]=document
            if document['document_type']!='delivery' and os.environ.get('REC_DEBT_MODE'):
                logging.info('Công nợ: bỏ qua ảnh không phải phiếu giao: %s (%s).',image.name,document['document_type']);report_progress();continue
            if document['document_type']!='delivery':
                if document['document_type'] in ('pr','po'):
                    if document.get('items'):pr_pages.append((image,document))
                if document['document_type']=='pr':
                    from receiving_pr import VERSION
                    signature=hashlib.sha256((VERSION+aw.MODEL+source_hash+json.dumps(groups,sort_keys=True,default=str)).encode()).hexdigest()
                    atomic_json(folder/'.receiving'/'pr-documents'/f'{signature}.json',document)
                logging.info('Bỏ qua ảnh đã lưu: %s (ảnh tham chiếu, không đọc lại khi nội dung không đổi).',image.name)
                logging.info('Ảnh tham chiếu %s (%s): đã lưu, chờ chọn ghép với phiếu; không đưa vào bảng hàng giao.',image.name,document['document_type'])
                continue
            if not completed:shutil.copy2(image,args.input/image.name)
        if (pr_pages or remembered_orders) and not os.environ.get('REC_DEBT_MODE'):
            keys=register_pages(library_directory,pr_pages) if pr_pages else []
            from ocr_events import emit
            from receiving_po_catalog import update_library
            if args.excel.is_file():
                for warning in update_library(library_directory,set(keys)|remembered_orders,args.excel):
                    emit('po_catalog_warning',warning)
            order_count=len(set(keys)|remembered_orders)
            emit('orders_saved','Đã lưu chứng từ đặt hàng vào thư viện.',count=order_count)
            logging.info('Thư viện đã nhận diện %s hồ sơ PR/PO.',order_count)
        logging.info('Chỉ xử lý %s ảnh giao chưa lưu; giữ nguyên %s ảnh giao đã lưu.',pending_count,len(list(args.input.iterdir()))-pending_count)
        from receiving_capture_time import capture_time
        try: original_inbox=json.loads((BASE/'.receiving'/'inbox-settings.json').read_text(encoding='utf-8')).get('source')
        except (OSError,ValueError,TypeError): original_inbox=None
        args.capture_times={p.name:capture_time(p,original_inbox) for p in source_images}
        result=md.run(args,key) if pending_count else 0
        if extraction_errors or args.held_image_names:
            raise RuntimeError('Đã giữ các phiếu đủ điều kiện và cache OCR. Chưa hoàn tất nhóm. Ảnh lỗi: '+('; '.join(extraction_errors) or 'không')+'; ảnh chờ đủ trang: '+(', '.join(args.held_image_names) or 'không')+'. Đọc lại cùng nhóm để tiếp tục phần chưa lưu.')
        if result in (0,None) and not os.environ.get('REC_DEBT_MODE'):
            for message in link_report(library_directory,ledger_path,folder,report,source_images,documents):logging.info(message)
        report_progress()
        logging.getLogger().removeHandler(progress_handler)
        return result

def main():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import threading
    import queue
    import subprocess
    import json
    from PIL import Image, ImageTk, ImageOps
    from receiving_service import paths, import_images, snapshot, edit_row, close_day, digest, atomic_json, day_images, day_directory, accounting_root, display_rows, sheet_signature, invoice_images

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title('Auto Receiving · Báo cáo nhận hàng')
            self.geometry('1480x900');self.minsize(1120,720)
            self.configure(bg='#f3f6fa')
            self.day=datetime.now().date();self.busy=False;self.proc=None
            self.events=queue.Queue();self.rows={};self.data=[];self.images=[];self.source_hash=None
            self.photo=None;self.zoom=1.;self.original_image=None;self.image_offset=[0.,0.];self.fit_scale=1.
            self.render_job=None;self.image_cache={};self.reviews={};self.syncing=False;self.pending_message=None
            self.config_file=BASE/'.receiving'/'settings.json'
            self.settings=json.loads(self.config_file.read_text(encoding='utf-8')) if self.config_file.exists() else {}
            self.destination=str(accounting_root(self.settings.get('destination',str(Path.home()/'Desktop'/'Công việc'/'Kế toán'/'Phieu giao hang hang thang'))))
            style=ttk.Style(self);style.theme_use('clam')
            style.configure('.',font=('Segoe UI',10),background='#f3f6fa',foreground='#1b2d40')
            style.configure('TButton',padding=(12,8),background='#ffffff',borderwidth=0)
            style.map('TButton',background=[('active','#e5edf5')])
            style.configure('Primary.TButton',background='#087f8c',foreground='white',font=('Segoe UI',10,'bold'))
            style.map('Primary.TButton',background=[('active','#066674'),('disabled','#b4cbd0')],foreground=[('disabled','#ffffff')])
            style.configure('Title.TLabel',font=('Segoe UI',21,'bold'))
            style.configure('Muted.TLabel',foreground='#64758a')
            style.configure('Card.TFrame',background='#ffffff')
            style.configure('Card.TLabel',background='#ffffff')
            style.configure('Head.TLabel',background='#ffffff',font=('Segoe UI',12,'bold'))
            style.configure('Treeview',background='#ffffff',fieldbackground='#ffffff',foreground='#24374a',rowheight=34,borderwidth=0,font=('Segoe UI',10))
            style.configure('Treeview.Heading',background='#eaf0f6',foreground='#31475d',font=('Segoe UI',9,'bold'),padding=(8,12),borderwidth=0)
            style.map('Treeview',background=[('selected','#d8edf0')],foreground=[('selected','#103e48')])
            style.configure('TPanedwindow',background='#e1e7ef')
            top=ttk.Frame(self,padding=(20,16,20,10));top.pack(fill='x')
            ttk.Label(top,text='Receiving',style='Title.TLabel').pack(side='left')
            ttk.Label(top,text='Nhận hàng & báo cáo ngày',style='Muted.TLabel').pack(side='left',padx=18)
            ttk.Button(top,text='Thư mục kế toán',command=lambda:self.guard(self.choose_root)).pack(side='right')
            ttk.Button(top,text='Mở ngày',command=self.open_day).pack(side='right',padx=8)
            self.date_var=tk.StringVar(value=self.day.strftime('%d/%m/%Y'))
            self.date_entry=ttk.Entry(top,textvariable=self.date_var,width=13,font=('Segoe UI',11));self.date_entry.pack(side='right')
            self.date_entry.bind('<Return>',lambda e:self.open_day())
            ttk.Label(top,text='Ngày báo cáo',style='Muted.TLabel').pack(side='right',padx=10)
            flow=ttk.Frame(self,padding=(20,0,20,10));flow.pack(fill='x')
            for i,(title,detail) in enumerate([('01  ĐỌC ẢNH','Lưu dữ liệu vào Excel tổng hợp'),('02  KIỂM TRA PHIẾU','Rà ảnh, sửa dòng và xác nhận'),('03  XUẤT BÁO CÁO','Tạo phiếu giao hàng để gửi')]):
                card=ttk.Frame(flow,style='Card.TFrame',padding=(14,10));card.pack(side='left',fill='x',expand=True,padx=(0,8 if i<2 else 0))
                ttk.Label(card,text=title,style='Head.TLabel').pack(anchor='w')
                ttk.Label(card,text=detail,style='Card.TLabel').pack(anchor='w',pady=(4,0))
            toolbar=ttk.Frame(self,padding=(20,0,20,8));toolbar.pack(fill='x')
            self.action_buttons=[]
            for label,func in [('Thêm ảnh',self.add),('Đọc ảnh mới → TongHop',self.read),('Tải lại Excel',self.reload),('Ghép ảnh cùng phiếu',self.merge)]:
                button=ttk.Button(toolbar,text=label,command=lambda f=func:self.guard(f));button.pack(side='left',padx=(0,6));self.action_buttons.append(button)
            self.summary=tk.StringVar(value='Đang tải ngày…');ttk.Label(toolbar,textvariable=self.summary,style='Muted.TLabel').pack(side='right')
            bottom=ttk.Frame(self,padding=(20,10));bottom.pack(side='bottom',fill='x')
            self.output_info=tk.StringVar()
            ttk.Label(bottom,textvariable=self.output_info,style='Muted.TLabel',wraplength=800).pack(side='left',fill='x',expand=True)
            ttk.Button(bottom,text='Mở thư mục',command=lambda:self.guard(self.open_folder)).pack(side='right',padx=(8,0))
            self.export_button=ttk.Button(bottom,text='Xuất phiếu giao hàng.xlsx',style='Primary.TButton',command=lambda:self.guard(self.publish));self.export_button.pack(side='right')
            self.progress=ttk.Progressbar(self,mode='indeterminate');self.progress.pack(side='bottom',fill='x',padx=20)
            self.status=tk.StringVar(value='Sẵn sàng')
            ttk.Label(self,textvariable=self.status,style='Muted.TLabel',padding=(20,6),wraplength=1300).pack(side='bottom',fill='x')
            logbar=ttk.Frame(self,padding=(20,0));logbar.pack(side='bottom',fill='x')
            ttk.Button(logbar,text='Nhật ký xử lý',command=self.toggle_log).pack(side='left')
            self.log=tk.Text(self,height=5,font=('Consolas',9),bg='#182b3d',fg='#e0eaf3',relief='flat',state='disabled')
            self.logbar=logbar;self.log_visible=False
            main=ttk.Panedwindow(self,orient='horizontal');main.pack(fill='both',expand=True,padx=20,pady=(0,8))
            sidebar=ttk.Frame(main,style='Card.TFrame',padding=10);workspace=ttk.Frame(main)
            main.add(sidebar,weight=0);main.add(workspace,weight=1)
            ttk.Label(sidebar,text='PHIẾU TRONG NGÀY',style='Head.TLabel').pack(anchor='w',pady=(3,8))
            self.invoice_list=ttk.Treeview(sidebar,columns=('name','state'),show='headings',selectmode='browse',height=9)
            self.invoice_list.heading('name',text='Phiếu / sheet');self.invoice_list.heading('state',text='Kiểm tra')
            self.invoice_list.column('name',width=142);self.invoice_list.column('state',width=85)
            scroll=ttk.Scrollbar(sidebar,command=self.invoice_list.yview);scroll.pack(side='right',fill='y')
            self.invoice_list.configure(yscrollcommand=scroll.set);self.invoice_list.pack(fill='both',expand=True)
            self.invoice_list.bind('<<TreeviewSelect>>',self.invoice_selected)
            ttk.Label(sidebar,text='ẢNH TRONG NGÀY',style='Head.TLabel').pack(anchor='w',pady=(16,8))
            self.image_list=tk.Listbox(sidebar,height=7,exportselection=False,bg='white',fg='#33485d',selectbackground='#d8edf0',selectforeground='#103e48',borderwidth=0,highlightthickness=0,font=('Segoe UI',10))
            self.image_list.pack(fill='x');self.image_list.bind('<<ListboxSelect>>',self.image_selected)
            nav=ttk.Frame(workspace);nav.pack(fill='x',pady=(0,8))
            self.prev_button=ttk.Button(nav,text='← Phiếu trước',command=lambda:self.move_sheet(-1));self.prev_button.pack(side='left')
            self.next_button=ttk.Button(nav,text='Phiếu sau →',command=lambda:self.move_sheet(1));self.next_button.pack(side='left',padx=6)
            self.sheet=tk.StringVar();self.selector=ttk.Combobox(nav,textvariable=self.sheet,state='readonly',width=24);self.selector.pack(side='left',fill='x',expand=True)
            self.selector.bind('<<ComboboxSelected>>',lambda e:self.select_sheet(self.sheet.get()))
            self.position=tk.StringVar();ttk.Label(nav,textvariable=self.position).pack(side='left',padx=10)
            self.review_button=ttk.Button(nav,text='Xác nhận đã kiểm tra',command=lambda:self.guard(self.approve));self.review_button.pack(side='right')
            split=ttk.Panedwindow(workspace,orient='horizontal');split.pack(fill='both',expand=True)
            left=ttk.Frame(split,style='Card.TFrame');right=ttk.Frame(split,style='Card.TFrame');split.add(left,weight=2);split.add(right,weight=3)
            z=ttk.Frame(left,style='Card.TFrame',padding=8);z.pack(fill='x')
            self.image_title=tk.StringVar(value='Chưa có ảnh');ttk.Label(z,textvariable=self.image_title,style='Card.TLabel').pack(side='left')
            for text,fn in [('−',lambda:self.scale(1/1.2)),('+',lambda:self.scale(1.2)),('Vừa khung',self.fit_image)]:ttk.Button(z,text=text,command=fn,width=8).pack(side='right',padx=2)
            self.canvas=tk.Canvas(left,bg='#e2e8f0',highlightthickness=0,cursor='fleur');self.canvas.pack(fill='both',expand=True)
            self.canvas.bind('<MouseWheel>',self.wheel_zoom);self.canvas.bind('<ButtonPress-1>',self.pan_start);self.canvas.bind('<B1-Motion>',self.pan_move)
            self.canvas.bind('<Double-Button-1>',lambda e:self.fit_image());self.canvas.bind('<Configure>',lambda e:self.schedule_render())
            self.zoom_label=tk.StringVar(value='Lăn chuột để zoom · Kéo để di chuyển')
            ttk.Label(left,textvariable=self.zoom_label,style='Card.TLabel',padding=8).pack(fill='x')
            meta=ttk.Frame(right,style='Card.TFrame',padding=10);meta.pack(fill='x')
            self.invoice_meta=tk.StringVar();ttk.Label(meta,textvariable=self.invoice_meta,style='Head.TLabel',wraplength=700).pack(anchor='w')
            self.review_status=tk.StringVar();ttk.Label(meta,textvariable=self.review_status,style='Card.TLabel',wraplength=700).pack(anchor='w',pady=(4,8))
            mode=ttk.Frame(meta,style='Card.TFrame');mode.pack(fill='x')
            self.show_all=tk.BooleanVar(value=False)
            ttk.Checkbutton(mode,text='Hiện đủ cột',variable=self.show_all,command=self.show_sheet).pack(side='left')
            ttk.Button(mode,text='Sửa dòng',command=lambda:self.guard(self.edit)).pack(side='right')
            ttk.Button(mode,text='Tra mã hàng',command=lambda:self.guard(self.search)).pack(side='right',padx=5)
            grid=ttk.Frame(right);grid.pack(fill='both',expand=True)
            self.cols=[];self.tree=ttk.Treeview(grid,show='headings',selectmode='browse')
            self.tree.tag_configure('review',background='#fff6e7');self.tree.tag_configure('alternate',background='#f6f9fc')
            sy=ttk.Scrollbar(grid,command=self.tree.yview);sy.pack(side='right',fill='y')
            tx=ttk.Scrollbar(grid,orient='horizontal',command=self.tree.xview);tx.pack(side='bottom',fill='x')
            self.tree.configure(yscrollcommand=sy.set,xscrollcommand=tx.set);self.tree.pack(fill='both',expand=True)
            self.tree.bind('<Double-1>',lambda e:self.guard(self.edit));self.tree.bind('<<TreeviewSelect>>',self.row_selected)
            self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll);self.after(80,self.reload)
            self.bind('<Alt-Left>',lambda e:self.move_sheet(-1));self.bind('<Alt-Right>',lambda e:self.move_sheet(1))
            self.after(120,lambda:main.sashpos(0,260))


        def guard(self,fn):
            if self.busy: messagebox.showinfo('Đang xử lý','Đợi bước hiện tại kết thúc. Không mở BAT cùng lúc.'); return
            try: fn()
            except Exception as e: messagebox.showerror('Chưa hoàn tất',str(e))

        def open_day(self):
            if self.busy:return
            try:
                selected=datetime.strptime(self.date_var.get().strip(),'%d/%m/%Y').date()
            except ValueError: messagebox.showerror('Ngày không hợp lệ','Nhập đủ dd/mm/yyyy.');return
            self.day=selected
            self.guard(self.reload)

        def choose_root(self):
            dest=filedialog.askdirectory(title='Chọn thư mục Phieu giao hang hang thang (hoặc thư mục năm)',initialdir=self.destination)
            if not dest:return
            self.destination=str(accounting_root(dest));atomic_json(self.config_file,{'destination':self.destination});self.reload()

        def add(self):
            files=filedialog.askopenfilenames(title='Chọn ảnh phiếu giao của ngày đang làm',filetypes=[('Ảnh','*.jpg *.jpeg *.png *.webp *.heic *.heif')])
            if files:
                added=import_images(BASE,self.day,files,self.destination); self.reload()
                self.status.set(f'Đã thêm {len(added)} ảnh; ảnh trùng nội dung trong ngày được bỏ qua. Ảnh nguồn được giữ nguyên.')

        def fit_image(self):
            if self.original_image is None:return
            self.update_idletasks()
            w,h=self.original_image.size;cw,ch=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())
            self.fit_scale=min(cw/w,ch/h);self.zoom=self.fit_scale
            self.image_offset=[(cw-w*self.zoom)/2,(ch-h*self.zoom)/2];self.render()

        def scale(self,factor,x=None,y=None):
            if self.original_image is None:return
            x=self.canvas.winfo_width()/2 if x is None else x;y=self.canvas.winfo_height()/2 if y is None else y
            old=self.zoom;new=max(self.fit_scale*.2,min(8,old*factor))
            self.image_offset=[x-(x-self.image_offset[0])*new/old,y-(y-self.image_offset[1])*new/old]
            self.zoom=new;self.schedule_render()

        def wheel_zoom(self,event):
            self.scale(1.15**max(-4,min(4,event.delta/120)),event.x,event.y);return 'break'

        def pan_start(self,event):self.pan_anchor=(event.x,event.y,*self.image_offset)

        def pan_move(self,event):
            if not hasattr(self,'pan_anchor'):return
            x,y,ox,oy=self.pan_anchor;self.image_offset=[ox+event.x-x,oy+event.y-y];self.schedule_render()

        def read(self):
            if not self.images:raise ValueError('Thêm ảnh vào ngày đang làm trước.')
            if not messagebox.askyesno('Đọc ảnh qua Gemini',f'Đọc {len(self.images)} ảnh trong ngày {self.day:%d/%m/%Y}. Ảnh chưa có cache có thể được gửi đến Gemini và tính phí. Tiếp tục?'):return
            self.set_busy(True)
            self.proc=subprocess.Popen([sys.executable,'-B','-X','utf8','-u',str(Path(__file__)),'--worker',self.day.isoformat(),self.destination],cwd=BASE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def consume():
                for line in self.proc.stdout:self.events.put(('log',line))
                code=self.proc.wait(); self.events.put(('done','Đọc xong; cần rà kết quả.' if code==0 else 'Chưa đọc xong; kết quả đã lưu vẫn giữ. Xem nhật ký rồi chạy tiếp.'))
            threading.Thread(target=consume,daemon=True).start()

        def edit(self):
            selected=self.tree.selection()
            if not selected:raise ValueError('Chọn một dòng trong bảng trước.')
            row=int(selected[0]); values=self.rows[str(row)]; window=tk.Toplevel(self); window.title('Rà và sửa dòng'); window.transient(self); window.grab_set()
            fields={}; headers=[h for h in ['Nhà cung cấp','Ngày nhận hàng xác nhận','Ngày giao hàng','Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Mã kho','Ghi chú'] if h in values]
            for i,h in enumerate(headers):
                ttk.Label(window,text=h).grid(row=i,column=0,sticky='w',padx=10,pady=5)
                v=values.get(h); fields[h]=tk.StringVar(value='' if v is None else str(v))
                ttk.Entry(window,textvariable=fields[h],width=70).grid(row=i,column=1,padx=10,pady=5)
            ttk.Label(window,text='Số: dùng dấu chấm thập phân, không dấu nghìn. Chọn mã hợp lệ sẽ lấy tên chuẩn/ĐVT từ danh mục.').grid(row=len(headers),columnspan=2,padx=10,pady=8)
            def save():
                try:
                    import AutoWatcher as aw
                    catalog,_=aw.load_catalog_data(BASE/'DanhMuc.xlsm')
                    changes={h:v.get() for h,v in fields.items() if v.get()!=('' if values.get(h) is None else str(values[h]))}
                    if changes:edit_row(self.report,self.source_hash,self.sheet.get(),row,changes,catalog)
                    window.destroy(); self.reload()
                except Exception as e:messagebox.showerror('Chưa lưu',str(e),parent=window)
            ttk.Button(window,text='Lưu sửa',command=save).grid(row=len(headers)+1,column=1,sticky='e',padx=10,pady=10)

        def search(self):
            import AutoWatcher as aw
            catalog,_=aw.load_catalog_data(BASE/'DanhMuc.xlsm')
            w=tk.Toplevel(self); w.title('Tra toàn danh mục — sao chép mã vào dòng cần sửa'); w.geometry('900x520')
            q=tk.StringVar(); ttk.Entry(w,textvariable=q).pack(fill='x',padx=8,pady=8)
            tree=ttk.Treeview(w,columns=('code','name','unit'),show='headings')
            for c,t,width in [('code','Mã',140),('name','Tên chuẩn',600),('unit','ĐVT',90)]:tree.heading(c,text=t);tree.column(c,width=width)
            tree.pack(fill='both',expand=True)
            def update(*args):
                tree.delete(*tree.get_children()); words=q.get().casefold().split()
                for code,(name,unit) in catalog.items():
                    if all(word in (code+' '+name).casefold() for word in words):tree.insert('','end',values=(code,name,unit))
            def copy():
                if tree.selection():self.clipboard_clear();self.clipboard_append(tree.item(tree.selection()[0],'values')[0])
            ttk.Button(w,text='Sao chép mã đã chọn',command=copy).pack(pady=5);q.trace_add('write',update);update()

        def merge(self):
            from manual_invoice_links import merge_saved_invoices
            from multi_delivery import output_lock
            w=tk.Toplevel(self);w.title('Chọn ảnh cùng một phiếu');w.geometry('680x440');w.transient(self);w.grab_set()
            ttk.Label(w,text='Giữ Ctrl để chọn các ảnh thuộc cùng một phiếu đã đọc.').pack(pady=8)
            items=tk.Listbox(w,selectmode='extended',exportselection=False);items.pack(fill='both',expand=True,padx=10)
            names=sorted({str(values.get('Ảnh nguồn')) for _,rows in self.data for _,values in rows if values.get('Ảnh nguồn')})
            for name in names:items.insert('end',name)
            def save():
                refs=[names[i] for i in items.curselection()]
                if len(refs)<2:messagebox.showinfo('Ghép phiếu','Chọn ít nhất hai ảnh.',parent=w);return
                if not messagebox.askyesno('Xác nhận ghép','Ghép cùng một phiếu:\n'+'\n'.join(refs),parent=w):return
                try:
                    with output_lock(self.report):merge_saved_invoices(self.report,refs)
                    w.destroy();self.reload()
                except Exception as e:messagebox.showerror('Chưa ghép',str(e),parent=w)
            ttk.Button(w,text='Ghép các ảnh đã chọn',command=save).pack(pady=10)

        def open_folder(self):
            target=day_directory(self.destination,self.day)
            if not target.exists():messagebox.showinfo('Chưa có thư mục',str(target)+'\nThêm ảnh hoặc chốt ngày để tạo thư mục.');return
            os.startfile(target)

        def set_busy(self,value):
            self.busy=value
            for button in [*self.action_buttons,self.export_button,self.review_button]:button.configure(state='disabled' if value else 'normal')
            if value:self.progress.start()
            else:self.progress.stop()

        def toggle_log(self):
            if self.log_visible:self.log.pack_forget()
            else:self.log.pack(side='bottom',fill='x',padx=20,before=self.logbar)
            self.log_visible=not self.log_visible

        def reload(self):
            if self.busy:return
            self.set_busy(True);self.status.set('Đang tải báo cáo và danh sách ảnh…')
            day,dest=self.day,self.destination
            def task():
                try:
                    folder,report=paths(BASE,day,dest);source_hash,data=snapshot(report)
                    images=day_images(report.parent)
                    saved={str(v.get('Ảnh nguồn','')).casefold() for _,rows in data for _,v in rows}
                    signatures={name:sheet_signature(name,rows) for name,rows in data}
                    review=folder/'reviewed.json'
                    reviews=json.loads(review.read_text(encoding='utf-8')) if review.exists() else {}
                    self.events.put(('loaded',(folder,report,source_hash,data,images,saved,signatures,reviews)))
                except Exception as e:self.events.put(('load_error',str(e)))
            threading.Thread(target=task,daemon=True).start()

        def loaded(self,payload):
            self.folder,self.report,self.source_hash,self.data,self.images,saved,self.signatures,self.reviews=payload
            self.data_by_sheet=dict(self.data)
            self.sheet_names=[name for name,_ in self.data]
            self.image_to_sheets={}
            for name,rows in self.data:
                refs=invoice_images(name,rows)
                for ref in refs:self.image_to_sheets.setdefault(ref,[]).append(name)
            saved=set(self.image_to_sheets)
            self.syncing=True
            self.image_list.delete(0,'end')
            for p in self.images:self.image_list.insert('end',('✓ ' if image_name(p) in saved else '• ')+p.name)
            self.selector['values']=self.sheet_names
            self.syncing=False
            self.refresh_invoice_list()
            selected=self.sheet.get() if self.sheet.get() in self.sheet_names else (self.sheet_names[0] if self.sheet_names else '')
            self.set_busy(False)
            self.select_sheet(selected)
            self.output_info.set(f'Nguồn: {self.report.name}\nXuất: Phieu giao hang {self.day.day}-{self.day.month}-{self.day.year}.xlsx')
            self.status.set(self.pending_message or str(self.report.parent));self.pending_message=None
            if not self.sheet_names and self.images:self.image_list.selection_set(0);self.image_selected()

        def approved(self,name):
            return self.reviews.get(name)==self.signatures.get(name) and bool(self.signatures.get(name))

        def refresh_invoice_list(self):
            self.syncing=True;self.invoice_list.delete(*self.invoice_list.get_children())
            for i,(name,rows) in enumerate(self.data):
                self.invoice_list.insert('','end',iid=str(i),values=(name,'Đã kiểm' if self.approved(name) else 'Chưa kiểm'))
            checked=sum(self.approved(name) for name,_ in self.data)
            self.summary.set(f'{len(self.images)} ảnh  ·  {len(self.data)} phiếu  ·  {checked} đã kiểm')
            self.syncing=False

        def invoice_selected(self,event=None):
            if self.syncing:return
            selected=self.invoice_list.selection()
            if selected:
                name=self.sheet_names[int(selected[0])]
                if name!=self.sheet.get():self.select_sheet(name)

        def move_sheet(self,delta):
            if not getattr(self,'sheet_names',[]):return
            current=self.sheet_names.index(self.sheet.get()) if self.sheet.get() in self.sheet_names else 0
            self.select_sheet(self.sheet_names[max(0,min(len(self.sheet_names)-1,current+delta))])

        def select_sheet(self,name,preferred_image=None):
            self.syncing=True;self.sheet.set(name)
            if name in getattr(self,'sheet_names',[]):
                index=self.sheet_names.index(name)
                if self.invoice_list.selection()!=(str(index),):self.invoice_list.selection_set(str(index))
                self.invoice_list.see(str(index))
                self.position.set(f'{index+1} / {len(self.sheet_names)}')
                self.prev_button.configure(state='normal' if index else 'disabled')
                self.next_button.configure(state='normal' if index<len(self.sheet_names)-1 else 'disabled')
            else:
                self.position.set('Chưa có dữ liệu');self.invoice_list.selection_remove(*self.invoice_list.selection())
                self.prev_button.configure(state='disabled');self.next_button.configure(state='disabled')
            self.show_sheet()
            refs=invoice_images(name,self.data_by_sheet.get(name,[])) if name else set()
            images=[p for p in self.images if image_name(p) in refs]
            self.image_list.selection_clear(0,'end')
            if preferred_image in images:chosen=preferred_image
            else:chosen=images[0] if images else None
            if chosen:
                ix=self.images.index(chosen);self.image_list.selection_set(ix);self.image_list.see(ix);self.load_image(chosen)
            else:
                self.original_image=None;self.canvas.delete('all');self.image_title.set('Không tìm thấy ảnh của phiếu này')
            self.syncing=False

        def image_selected(self,event=None):
            if self.syncing:return
            ix=self.image_list.curselection()
            if not ix:return
            image=self.images[ix[0]];matches=self.image_to_sheets.get(image_name(image),[])
            if getattr(self,'current_image',None)==image and self.original_image is not None and self.sheet.get() in matches:return
            if len(matches)==1:self.select_sheet(matches[0],image)
            elif self.sheet.get() in matches:self.select_sheet(self.sheet.get(),image)
            else:
                self.select_sheet('');self.image_list.selection_set(ix[0]);self.load_image(image)
                self.status.set('Ảnh chưa liên kết duy nhất với phiếu đã đọc. Bảng được để trống để tránh rà nhầm; chọn phiếu trong danh sách hoặc đọc ảnh mới.')

        def show_sheet(self):
            self.tree.delete(*self.tree.get_children());self.rows={}
            name=self.sheet.get();rows=getattr(self,'data_by_sheet',{}).get(name,[])
            available=list(dict.fromkeys(h for _,v in rows for h in v if h))
            core=['STT trên phiếu','Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Thành tiền','Mã kho','Bộ phận','Ghi chú']
            self.cols=[h for h in core if h in available]+[h for h in available if h not in core]
            self.tree.configure(columns=self.cols)
            shown=self.cols if self.show_all.get() else [h for h in core if h in available]
            self.tree.configure(displaycolumns=shown)
            labels={'STT trên phiếu':'STT','Tên hàng trên phiếu (Ảnh)':'Mặt hàng','Mã vật tư':'Mã hàng','Đơn vị tính':'ĐVT','Số lượng':'SL giao','Thực nhận':'SL nhận','Đơn giá':'Đơn giá','Thành tiền':'Tiền thực nhận'}
            for c in self.cols:
                self.tree.heading(c,text=labels.get(c,c))
                width=255 if c in ('Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống','Ghi chú') else (65 if c in ('STT trên phiếu','Đơn vị tính') else 115)
                self.tree.column(c,width=width,stretch=False,anchor='e' if c in ('Số lượng','Thực nhận','Đơn giá','Thành tiền') else 'w')
            self.displayed=display_rows(rows)
            for i,(row,values) in enumerate(self.displayed):
                self.rows[str(row)]=dict(rows[i][1]) # Original values used by the editor.
                issue=not values.get('Mã vật tư') or values.get('Mã vật tư')=='CHUA CO MA' or values.get('Thực nhận') is None or values.get('Đơn giá') is None or 'KIỂM' in str(values.get('Trạng thái',''))
                def text(c):
                    v=values.get(c)
                    if v is None:return ''
                    if c in ('Đơn giá','Thành tiền') and isinstance(v,(int,float)):return f'{v:,.2f}'.rstrip('0').rstrip('.')
                    return str(v)
                self.tree.insert('','end',iid=str(row),values=[text(c) for c in self.cols],tags=('review',) if issue else (('alternate',) if i%2 else ()))
            self.tree.xview_moveto(0)
            first=rows[0][1] if rows else {}
            received=first.get('Ngày nhận hàng xác nhận','')
            self.invoice_meta.set(str(first.get('Nhà cung cấp') or name or 'Chọn phiếu để kiểm tra')+('  ·  '+str(received) if received else ''))
            self.review_status.set(('Đã kiểm tra' if name and self.approved(name) else 'Chưa kiểm tra')+f'  ·  {len(rows)} dòng  ·  {len(self.cols)} cột'+('\nBật “Hiện đủ cột” để xem ngày, tên chuẩn, tổng tiền và dữ liệu đối chiếu.' if rows else ''))

        def row_selected(self,event=None):
            selected=self.tree.selection()
            if not selected:return
            ref=str(self.rows[selected[0]].get('Ảnh nguồn','')).casefold()
            matches=[p for p in self.images if image_name(p)==ref]
            if len(matches)==1:
                self.syncing=True;self.image_list.selection_clear(0,'end');self.image_list.selection_set(self.images.index(matches[0]));self.syncing=False
                self.load_image(matches[0])

        def load_image(self,path):
            if getattr(self,'current_image',None)==path and self.original_image is not None:return
            try:
                cache_key=(str(path),path.stat().st_mtime_ns,path.stat().st_size)
                if cache_key not in self.image_cache:
                    with Image.open(path) as source:self.image_cache[cache_key]=ImageOps.exif_transpose(source).convert('RGB')
                    while len(self.image_cache)>3:self.image_cache.pop(next(iter(self.image_cache)))
                self.original_image=self.image_cache[cache_key];self.current_image=path;self.image_title.set(path.name)
                self.fit_image()
            except Exception as e:self.original_image=None;self.canvas.delete('all');self.status.set(f'Chưa xem được ảnh: {e}')

        def schedule_render(self):
            if self.render_job is None:self.render_job=self.after(20,self.flush_render)

        def flush_render(self):
            self.render_job=None;self.render()

        def render(self):
            if self.original_image is None:return
            try:
                cw,ch=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())
                w,h=self.original_image.size;ox,oy=self.image_offset
                left=max(0,-ox/self.zoom);top=max(0,-oy/self.zoom);right=min(w,(cw-ox)/self.zoom);bottom=min(h,(ch-oy)/self.zoom)
                if right<=left or bottom<=top:self.canvas.delete('all');return
                box=(int(left),int(top),min(w,int(right+.999)),min(h,int(bottom+.999)))
                crop=self.original_image.crop(box)
                crop=crop.resize((max(1,round(crop.width*self.zoom)),max(1,round(crop.height*self.zoom))),Image.Resampling.BILINEAR)
                self.photo=ImageTk.PhotoImage(crop)
                self.canvas.delete('all');self.canvas.create_image(ox+box[0]*self.zoom,oy+box[1]*self.zoom,anchor='nw',image=self.photo)
                self.zoom_label.set(f'{self.zoom:.0%}  ·  Lăn chuột: zoom  ·  Kéo: di chuyển  ·  Nhấp đúp: vừa khung')
            except Exception as e:self.status.set(f'Chưa xem được ảnh: {e}')

        def approve(self):
            name=self.sheet.get()
            if not name:raise ValueError('Chọn một phiếu đã có dữ liệu trước.')
            if digest(self.report)!=self.source_hash:raise ValueError('Excel đã đổi. Bấm Tải lại Excel và kiểm tra dữ liệu mới.')
            if not messagebox.askyesno('Xác nhận phiếu đã kiểm tra',f'Đã kiểm tra đủ tên, mã, đơn vị, giá, ngày và số thực nhận của {name}?\nThao tác này không xuất Excel.'):return
            self.reviews[name]=self.signatures[name];atomic_json(self.folder/'reviewed.json',self.reviews)
            self.refresh_invoice_list();self.select_sheet(name,getattr(self,'current_image',None))
            self.status.set(f'Đã xác nhận {name}. Chọn Phiếu sau để kiểm tra tiếp; xong tất cả thì Xuất phiếu giao hàng.xlsx.')

        def publish(self):
            if not self.report.exists():raise ValueError('Chưa có Excel tổng hợp. Thêm ảnh và bấm Đọc ảnh mới trước.')
            if digest(self.report)!=self.source_hash:raise ValueError('Excel đã đổi. Tải lại và kiểm tra dữ liệu mới trước khi xuất.')
            pending=[name for name,_ in self.data if not self.approved(name)]
            if pending:raise ValueError('Chưa xuất: còn phiếu chưa xác nhận kiểm tra.\n'+', '.join(pending))
            if not self.data:raise ValueError('Báo cáo chưa có dữ liệu.')
            output=f'Phieu giao hang {self.day.day}-{self.day.month}-{self.day.year}.xlsx'
            if not messagebox.askyesno('Xuất phiếu giao hàng',f'File được tạo/cập nhật:\n{output}\n\nNguồn:\n{self.report.name}\n\nNơi lưu:\n{self.report.parent}\n\nBản xuất cũ được sao lưu. File TongHop vẫn là bản dữ liệu bạn đang rà.'):return
            self.set_busy(True);day,dest,report=self.day,self.destination,self.report
            def task():
                try:target=close_day(BASE,day,dest,report_override=report);self.events.put(('done',f'ĐÃ XUẤT {output} — {target}'))
                except Exception as e:self.events.put(('done','CHƯA XUẤT: '+str(e)))
            threading.Thread(target=task,daemon=True).start()

        def poll(self):
            for _ in range(80):
                try:kind,value=self.events.get_nowait()
                except queue.Empty:break
                if kind=='loaded':self.loaded(value);continue
                if kind=='load_error':self.set_busy(False);self.status.set('Chưa tải được: '+value);continue
                self.log.configure(state='normal');self.log.insert('end',value.rstrip()+'\n');self.log.see('end');self.log.configure(state='disabled')
                if kind=='done':
                    self.set_busy(False);self.proc=None;self.pending_message=value;self.reload()
                elif kind=='log':self.status.set(value.strip())
            self.after(100,self.poll)


        def close(self):
            if self.busy:messagebox.showinfo('Đang xử lý','Đợi bước hiện tại kết thúc để giữ kết quả đang ghi.');return
            self.destroy()

    globals()["ReceivingApp"] = App
    App().mainloop()

if __name__=='__main__':
    if '--worker' in sys.argv:
        try:sys.exit(worker())
        except Exception as exc:
            # Exceptions from external APIs might contain credentials; never echo raw errors.
            print('Chưa xử lý được: '+type(exc).__name__+'. Kiểm tra cấu hình API, kết nối hoặc file đang mở.');sys.exit(1)
    main()
