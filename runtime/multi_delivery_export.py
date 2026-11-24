"""Gộp TongHop nhiều phiếu vào mẫu kế toán một sheet, ngày nhận đã xác nhận."""
import argparse
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

from openpyxl import load_workbook
import AutoWatcher as aw
from multi_delivery import output_lock
from supplier_directory import load_supplier_directory, supplier_aliases
from warehouse_directory import load_warehouse_directory
from delivery_export import fill_flat_delivery, LAYOUT_VERSION

BASE_DIR=Path(__file__).resolve().parent
RECEIPT_DATE_HEADER='Ngày nhận hàng xác nhận'


def export_multiple(report,catalog,excel,rules_path,output,template):
    report,excel,rules_path,output,template=map(Path,(report,excel,rules_path,output,template))
    if output.resolve() in {p.resolve() for p in (report,excel,rules_path,template)}:
        raise ValueError('File xuất phải khác TongHop, danh mục, quy tắc và mẫu nguồn.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output_lock(report),output_lock(output):
        source_digest=aw.delivery_report_digest(report)
        directory=load_supplier_directory(excel)
        warehouses=load_warehouse_directory(excel,required=False)
        rules=json.loads(rules_path.read_text(encoding='utf-8-sig'))
        aliases=supplier_aliases(rules,directory)
        signature=hashlib.sha256(template.read_bytes()+json.dumps(
            ['multi-export-receipt-date-v3',LAYOUT_VERSION,source_digest,catalog,directory,warehouses,aliases],
            ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
        backup=aw.delivery_backup_directory(output.parent)/output.name
        metadata=aw.delivery_backup_metadata_path(backup)
        previous={}
        if metadata.is_file():
            try:previous=json.loads(metadata.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
        if previous.get('export_signature')==signature:
            if output.exists():
                aw.backup_delivery_workbook(output,report,signature)
                logging.info('Nguồn không đổi; giữ phiếu đã xuất và các sửa tay: %s',output)
                return output
            if backup.is_file():
                aw.atomic_copy_file(backup,output)
                logging.info('Đã khôi phục phiếu xuất từ bản sao lưu: %s',output)
                return output
        rows=[r for batch in aw.reviewed_delivery_rows(report,catalog,directory,aliases,warehouses,
                                                      date_header=RECEIPT_DATE_HEADER) for r in batch]
        if not rows:raise ValueError('TongHop không có dòng phiếu giao để xuất.')
        for row in rows:
            if row['delivery_date'] is None:
                raise ValueError(f"Sheet {row['invoice_key']} thiếu {RECEIPT_DATE_HEADER}. Điền ngày vào cột này trong TongHop rồi chạy lại.")
        temporary=None
        workbook=None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.xlsx',delete=False) as handle:
                temporary=Path(handle.name)
            workbook=load_workbook(template)
            fill_flat_delivery(workbook,rows)
            aw.apply_delivery_font(workbook)
            workbook.active=0
            workbook.calculation.calcMode='auto'
            workbook.calculation.fullCalcOnLoad=True
            workbook.calculation.forceFullCalc=True
            workbook.save(temporary);workbook.close();workbook=None
            if aw.delivery_report_digest(report)!=source_digest:
                raise ValueError('TongHop thay đổi khi đang xuất. Lưu và đóng file rồi chạy lại.')
            if output.exists():
                history=output.parent/'.autowatcher-backups'/('multi-export-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
                aw.atomic_copy_file(output,history/output.name)
                logging.info('Nguồn thay đổi; đã sao lưu bản xuất trước tại %s. Sửa số liệu trong TongHop để áp dụng cho lần xuất mới.',history)
            os.replace(temporary,output)
            aw.backup_delivery_workbook(output,report,signature,aw.delivery_source_signature(rows))
        finally:
            if workbook is not None:workbook.close()
            if temporary is not None:temporary.unlink(missing_ok=True)
        logging.info('ĐÃ XUẤT: %s dòng / %s phiếu, một sheet: %s',len(rows),len({r['invoice_key'] for r in rows}),output)
        return output


def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',datefmt='%H:%M:%S')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--today',action='store_true',help='Xuất TongHop hôm nay thành Phieu giao hang D-M-YYYY.xlsx theo ngày máy tính.')
    parser.add_argument('--excel',type=Path,default=BASE_DIR/'DanhMuc.xlsm')
    parser.add_argument('--rules',type=Path,default=BASE_DIR/'NhaCungCap.json')
    parser.add_argument('--template',type=Path)
    args=parser.parse_args()
    if args.today:
        today=datetime.now().date()
        args.report=args.report or BASE_DIR/f'TongHopPhieuNgay_{today:%d-%m-%Y}.xlsx'
        args.output=args.output or BASE_DIR/f'Phieu giao hang {today.day}-{today.month}-{today.year}.xlsx'
    else:
        args.report=args.report or BASE_DIR/'TongHopNhieuPhieuGiaoHang.xlsx'
        args.output=args.output or BASE_DIR/'PhieuGiaoHangNhieuNgay.xlsx'
    try:
        if not args.report.is_file():
            runner='file BAT đọc nhiều phiếu hôm nay' if args.today else '03_Doc_nhieu_phieu_ngay_khac_nhau.bat'
            raise FileNotFoundError(f'Chưa có {args.report.name}. Chạy {runner} trước.')
        logging.info('Báo cáo nguồn: %s',args.report)
        template=args.template or aw.delivery_template_path(aw.delivery_output_directory())
        catalog,_=aw.load_catalog_data(args.excel)
        export_multiple(args.report,catalog,args.excel,args.rules,args.output,template)
        print(f'File kết quả: {args.output}\nDùng ngày nhận đã xác nhận cho từng phiếu. Không đọc lại ảnh/không gọi AI.')
        return 0
    except (OSError,ValueError) as exc:
        logging.error('Chưa xuất phiếu: %s. Đóng file Excel/WPS nếu file đang mở.',exc)
        return 1
    except KeyboardInterrupt:
        print('Đã hủy xuất.');return 1


if __name__=='__main__':sys.exit(main())
