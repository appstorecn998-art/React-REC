"""Offline acceptance inside an isolated temporary folder, including frozen builds."""
def run(data_root):
    from pathlib import Path
    import tempfile
    from datetime import date
    from unittest.mock import patch
    from PIL import Image,ImageDraw
    from openpyxl import Workbook,load_workbook
    import receiving_service as rs
    from receiving_inbox import Inbox
    from receiving_review import crop_region
    results=[]
    def receipt_assets():
        from receipt_rules import receipt_rules_fingerprint
        assert receipt_rules_fingerprint()
    def check(name, action):
        try:action();results.append({'name':name,'ok':True})
        except Exception as exc:
            results.append({'name':name,'ok':False,'error_type':type(exc).__name__})
    check('receipt_rule_assets',receipt_assets)
    with tempfile.TemporaryDirectory(prefix='REC-acceptance-') as temp:
        root=Path(temp);day=date(2026,11,7)
        source=root/'source';source.mkdir();image=source/'receipt.png'
        im=Image.new('RGB',(1000,700),'white');draw=ImageDraw.Draw(im)
        for y in [240,340,440]:draw.line((0,y,999,y),fill='black',width=3)
        draw.text((250,260),'Xoai cat chu',fill='black');draw.text((250,310),'DP',fill='black');im.save(image)
        original=rs.digest(image)
        def import_once():
            assert len(rs.import_images(root,day,[image]))==1
            assert rs.import_images(root,day,[image])==[]
            assert rs.digest(image)==original
        check('import_and_duplicate_protection',import_once)
        def row_image():
            crop=crop_region(image,(0,255,1000,290),(250,260,550,285))
            assert crop.height>=95 and rs.digest(image)==original
        check('multiline_crop_preserves_source',row_image)
        _,report=rs.paths(root,day)
        book=Workbook();sheet=book.active;sheet.title='Invoice'
        sheet.append(['Tên hàng trên phiếu (Ảnh)','Mã vật tư','Tên chuẩn hệ thống','Đơn vị tính','Số lượng','Thực nhận','Đơn giá','Thành tiền','Ghi chú'])
        sheet.append(['Cá','001','Cá','kg',10,7,50000,'=F2*G2','']);book.save(report);book.close()
        def edit_and_stale():
            old=rs.digest(report)
            rs.edit_row(report,old,'Invoice',2,{'Thực nhận':'0','Ghi chú':'=not-a-formula'},{'001':('Cá','kg')})
            wb=load_workbook(report);assert wb.active['F2'].value==0 and wb.active['I2'].data_type=='s';wb.close()
            try:rs.edit_row(report,old,'Invoice',2,{'Thực nhận':'1'},{'001':('Cá','kg')})
            except ValueError:pass
            else:raise AssertionError('Stale edit accepted')
        check('excel_edit_zero_formula_and_stale_guard',edit_and_stale)
        def locked_write():
            before=rs.digest(report)
            with patch('receiving_service.os.replace',side_effect=PermissionError('offline-lock')):
                try:rs.edit_row(report,before,'Invoice',2,{'Thực nhận':'1'},{'001':('Cá','kg')})
                except PermissionError:pass
                else:raise AssertionError('Lock ignored')
            assert rs.digest(report)==before
        check('locked_excel_preserves_original',locked_write)
        def export():
            # Exercise actual export with the user's catalog, only under temp.
            import shutil
            for name in ['DanhMuc.xlsm','NhaCungCap.json']:shutil.copy2(Path(data_root)/name,root/name)
            import AutoWatcher as aw
            from multi_delivery_export import export_multiple
            wb=load_workbook(report);ws=wb.active
            for col,name in enumerate(['Độ khớp AI đề xuất','Trạng thái','Đối chiếu PR'],10):ws.cell(1,col,name)
            ws.cell(2,11,'CẦN KIỂM TRA');ws.cell(1,13,'Ngày nhận hàng xác nhận');ws.cell(2,13,'07/11/2026');wb.save(report);wb.close()
            cat,_=aw.load_catalog_data(root/'DanhMuc.xlsm')
            out=root/'export.xlsx'
            export_multiple(report,cat,root/'DanhMuc.xlsm',root/'NhaCungCap.json',out,Path(data_root)/'Phieu giao hang ngay X.xlsx')
            wb=load_workbook(out);assert len(wb.sheetnames)==1 and wb.active.max_column==19;wb.close()
        check('actual_19_column_excel_export',export)
        def recovery():
            inbox=Inbox(root/'inbox.json');inbox.scan(source);inbox.prepare(source,root,day,root/'reports');inbox.finish()
            (root/'inbox.json').write_text('{',encoding='utf-8')
            restored=Inbox(root/'inbox.json');assert not restored.blocked and restored.warning
            restored.scan(source);assert restored.scan(source)==[]
            (root/'inbox.json').write_text('{',encoding='utf-8')
            (root/'inbox.backup.json').write_text('{',encoding='utf-8')
            blocked=Inbox(root/'inbox.json');assert blocked.blocked
            try:blocked.scan(source)
            except ValueError:pass
            else:raise AssertionError('Unsafe scan')
        check('restart_corrupt_state_recovery_and_safe_stop',recovery)
    return {'ok':all(r['ok'] for r in results),'results':results,'network_requests':0,'real_reports_modified':False}
