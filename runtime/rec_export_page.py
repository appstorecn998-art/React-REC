"""Design31 export preview, using saved report/approval guards and original exporter."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLabel,QLineEdit,QDialogButtonBox,QCheckBox,QFrame,QPushButton,QHBoxLayout,QMessageBox
from rec_pr_surface import flat_page
from PySide6.QtCore import Qt
from receiving_service import digest

def is_access_error(text):
    return any(part in text.casefold() for part in ["permission", "access is denied", "winerror 32", "winerror 33", "being used by another process", "đang mở", "quyền truy cập"])

def show(w):
    old=getattr(w,'export_design_page',None)
    if old is not None:w.main_pages.removeWidget(old);old.deleteLater()
    page=QWidget();page.setObjectName('exportDesignPage');QVBoxLayout(page);w.export_design_page=page
    report,day,expected=w.report,w.day,w.source_hash
    output=f'Phieu giao hang {day.day}-{day.month}-{day.year}.xlsx';destination=w.destination;root=w.root
    from receiving_service import day_directory
    folder=day_directory(destination,day);target=folder/output
    from receiving_export_distribution import destinations
    manager,archive=destinations(day)
    content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(0,0,0,0);v.setSpacing(18)
    locked=QLabel();locked.setObjectName('exportLockedBanner');locked.setWordWrap(True);locked.hide();locked.setStyleSheet('background:#fffaf0;color:#916c2b;border:1px solid #f2e6ca;border-radius:9px;padding:14px 16px;');v.addWidget(locked)
    title=QLabel('Xuất hồ sơ ngày '+day.strftime('%d/%m/%Y'));title.setStyleSheet('font-size:22px;font-weight:600;color:#24334b;');v.addWidget(title)
    description=QLabel('Một lần xuất tạo đủ 3 đầu ra • Số lượng theo thực nhận • Giờ HH:mm');description.setStyleSheet('color:#526079;font-size:13px;');v.addWidget(description)
    def open_output(index):
        from pathlib import Path
        location=Path(path_labels[index].text()).parent
        if location.is_dir():__import__('os').startfile(str(location))
        else:QMessageBox.information(page,'Chưa có thư mục','Thư mục này chưa tồn tại. Xuất hồ sơ để tạo đầu ra trước.')
    path_labels=[]
    for number,heading,path,detail in [(1,'Phiếu giao hàng trên máy',target,'Excel 19 cột và thư mục ảnh Phiếu giao hàng'),(2,'Báo cáo công việc gửi sếp',manager,'Checklist và nhật ký nhận hàng; giữ nguyên toàn bộ file nếu đã tồn tại'),(3,'ZIP ngoài Desktop',archive,'Chứa file phiếu và thư mục ảnh, sẵn sàng gửi')]:
        card=QFrame();card.setObjectName('exportOutputCard');column=QVBoxLayout(card);column.setContentsMargins(16,12,16,12);column.setSpacing(6)
        caption=QLabel(str(number)+'. '+heading);caption.setStyleSheet('font-size:15px;font-weight:600;color:#263750;');header=QHBoxLayout();header.addWidget(caption,1);opener=QPushButton('Mở thư mục');opener.setObjectName('exportOpenFolder'+str(number));opener.clicked.connect(lambda checked=False,index=number-1:open_output(index));header.addWidget(opener);column.addLayout(header)
        location=QLabel(str(path));location.setWordWrap(True);location.setTextInteractionFlags(Qt.TextSelectableByMouse);location.setStyleSheet('font-size:13px;color:#354861;');location.setObjectName('exportOutputPath');column.addWidget(location);path_labels.append(location)
        hint=QLabel(detail);hint.setWordWrap(True);hint.setStyleSheet('font-size:12px;color:#64748b;');column.addWidget(hint);v.addWidget(card)
    warning=QLabel();warning.setObjectName('exportPendingWarning');warning.setWordWrap(True);warning.setStyleSheet('background:#fff7e6;border:1px solid #edc675;border-radius:8px;color:#74490b;padding:12px;font-size:14px;');v.addWidget(warning)
    consent=QCheckBox('Tôi xác nhận xuất BẢN TẠM; còn phiếu chưa hoàn tất');consent.setObjectName('exportProvisionalConsent');consent.setStyleSheet('font-size:14px;color:#334155;padding:8px 0;');v.addWidget(consent)
    status=QLabel();status.setObjectName('exportDesignStatus');status.setWordWrap(True);status.setStyleSheet('font-size:14px;color:#334155;background:#f1f5f9;border:1px solid #dce4ee;border-radius:8px;padding:14px;');v.addWidget(status)
    box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);save=box.button(QDialogButtonBox.Save);save.setText('Xuất phiếu');box.button(QDialogButtonBox.Cancel).setText('Mở thư mục')
    notice=QLabel('Xuất đúng dữ liệu đã lưu. File đang mở trong Excel/WPS phải đóng trước khi cập nhật; không báo thành công khi chưa ghi được.')
    flat_page(page,'Xuất phiếu giao hàng','Xem nơi lưu, ngày và trạng thái nguồn trước khi xuất',content,notice,box);page.layout().setStretch(page.layout().indexOf(content),0);page.layout().addStretch();page.setStyleSheet(page.styleSheet()+'''QWidget#exportDesignPage {background:white;font-family:"Segoe UI";color:#334155;} QFrame#exportOutputCard {background:#f8fafc;border:1px solid #dbe2ec;border-radius:9px;} QPushButton {font-size:13px;min-height:38px;max-height:38px;padding:0 16px;} QPushButton:disabled {color:#64748b;}''')
    for label in page.findChildren(QLabel):
        if label.text()=='PR & đối chiếu / Xuất phiếu giao hàng':label.setText('Xuất & đồng bộ / Xuất phiếu giao hàng')
    def validate():
        if w.busy:raise ValueError('REC đang xử lý. Chờ hoàn tất trước khi xuất.')
        if not report or not w.data:raise ValueError('Chưa có dữ liệu. Chọn ngày có báo cáo tổng hợp trước.')
        if w.report!=report or w.day!=day or w.destination!=destination or digest(report)!=expected:raise ValueError('Nguồn hoặc ngày đã đổi. Mở lại bản xem trước sau khi tải lại báo cáo.')
        from receiving_provisional_export import pending
        return pending(w)
    def fit_buttons():
        for button in box.buttons():
            button.ensurePolished();button.setFixedSize(max(125,button.fontMetrics().horizontalAdvance(button.text())+56),42)
        box.setFixedWidth(sum(button.width() for button in box.buttons() if not button.isHidden())+48)
    def refresh_gate(*_):
        try:
            issues=validate();warning.setText(('Còn '+str(len(issues))+' phiếu chưa hoàn tất:\n'+'\n'.join(name+' · '+reason for name,reason in issues)) if issues else '')
            consent.setVisible(bool(issues));save.setEnabled(not issues or consent.isChecked())
            save.setText('Xuất BẢN TẠM' if issues else 'Xuất đủ 3 đầu ra');fit_buttons()
            from rec_workflow_status import paint
            paint(save,'Xuất BẢN TẠM' if issues else 'Xuất đủ 3 đầu ra','warning' if issues else 'ready');fit_buttons()
            from receiving_export_pr_notes import collect
            pr_notes=collect(report)
            if not issues and pr_notes:warning.setText('Được xuất phiếu giao hàng; các phiếu sau vẫn chờ PR, chưa ghi sổ:\n'+'\n'.join(pr_notes))
            warning.setVisible(bool(issues or pr_notes))
            if issues:
                temporary_manager,temporary_archive=destinations(day,provisional=True)
                path_labels[0].setText(str(target.with_name(target.stem+' - BẢN TẠM.xlsx')))
                path_labels[1].setText(str(temporary_manager));path_labels[2].setText(str(temporary_archive))
            else:
                for label,path in zip(path_labels,[target,manager,archive]):label.setText(str(path))
            status.setText('Bản tạm không xác nhận kiểm phiếu, không ghi sổ, không đồng bộ Sheets.' if issues else 'Dữ liệu giao hàng đã đủ điều kiện xuất. Phiếu chờ PR thay thế được ghi chú riêng, chưa ghi sổ PR.')
        except (OSError,ValueError) as exc:status.setText(str(exc));save.setEnabled(False)
    consent.toggled.connect(refresh_gate);refresh_gate()
    def submit():
        try:
            issues=validate()
            if issues and not consent.isChecked():raise ValueError('Tích xác nhận trước khi xuất bản tạm.')
        except (OSError,ValueError) as exc:status.setText('Chưa xuất: '+str(exc));save.setEnabled(False);return
        from receiving_qt import Worker,close_day
        w.set_busy(True,'Đang dựng phiếu giao hàng…');save.setEnabled(False);status.setText('Đang xuất. Chưa xác nhận thành công…')
        def export():
            if digest(report)!=expected:raise ValueError('Nguồn vừa đổi. Tải lại trước khi xuất.')
            if issues:
                from receiving_provisional_export import export as export_temporary
                return export_temporary(root,day,destination,report)
            from receiving_provisional_export import pending
            if pending(w):raise ValueError('Điều kiện kiểm/ghi sổ đã đổi; mở lại trang xuất.')
            result=close_day(root,day,destination,None,report)
            if not target.is_file():raise ValueError('Bộ xuất chưa tạo được file đích. Chưa báo thành công.')
            from receiving_export_distribution import distribute
            try:distribute(result,day)
            except Exception as exc:raise ValueError('Phiếu trên máy đã xuất; chưa hoàn tất đủ 3 đầu ra: '+str(exc))
            return result
        job=Worker(export)
        def done(_):
            if issues:
                locked.hide();save.setEnabled(False)
                status.setStyleSheet('font-size:14px;color:#9a3412;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:16px;');status.setText('Đã xuất đủ 3 đầu ra BẢN TẠM. Chưa thay đổi trạng thái kiểm, sổ hoặc Sheets.');w.show_top_notice('Đã xuất BẢN TẠM','Hai file Excel và ZIP có nhãn BẢN TẠM.');return
            locked.hide();save.setText('Xuất phiếu');fit_buttons();status.setStyleSheet('font-size:14px;font-weight:600;color:#166534;background:#ecfdf5;border:1px solid #bbf7d0;border-radius:8px;padding:16px;');status.setText('✓ Đã xuất đủ 3 đầu ra\nPhiếu giao hàng · Báo cáo công việc · ZIP ảnh phiếu\nBáo cáo công việc có sẵn được giữ nguyên toàn bộ.\nBấm Mở thư mục ở từng mục phía trên để xem file.');w.show_top_notice('Đã xuất đủ 3 đầu ra','Phiếu trên máy · Báo cáo công việc · ZIP ngoài Desktop')
        def failed(text):
            access=is_access_error(text)
            locked.setText('<b>Chưa xuất được — file có thể đang mở trong Excel/WPS</b><br>Đóng file rồi thử lại. Nếu vẫn lỗi, kiểm tra quyền ghi tại nơi lưu. Kết quả đã xử lý được giữ.');locked.setVisible(access)
            status.setStyleSheet('font-size:14px;color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:14px;');status.setText('Chưa xuất được: '+text);save.setText('Thử xuất lại');save.setEnabled(True)
            back.setVisible(True);fit_buttons()
        
        job.signals.result.connect(done);job.signals.error.connect(failed);job.signals.finished.connect(lambda:w.set_busy(False));w._start_worker(job)
    back=box.addButton('Trở lại',QDialogButtonBox.ActionRole);back.hide()
    def return_to_preview():
        locked.hide();back.hide();save.setText('Xuất phiếu')
        refresh_gate()
        fit_buttons()
    back.clicked.connect(return_to_preview)
    box.accepted.connect(submit)
    def open_folder():
        if folder.exists():__import__('os').startfile(str(folder))
    fit_buttons()
    box.rejected.connect(open_folder);w.main_pages.addWidget(page);w.main_pages.setCurrentWidget(page);return page
