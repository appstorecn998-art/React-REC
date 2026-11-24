"""Gộp các sheet của cùng một phiếu đã đọc; không đọc lại ảnh hoặc gọi AI."""
import argparse
import logging
from pathlib import Path
import re
import shlex

from openpyxl import load_workbook
import AutoWatcher as aw
from manual_invoice_links import find_sheets, sheet_images, merge_saved_invoices, valid_image_reference
from multi_delivery import output_lock

BASE_DIR=Path(__file__).resolve().parent


def parse_names(answer):
    if ',' in answer or ';' in answer:
        names=[part.strip().strip('"\'') for part in re.split(r'[,;]',answer) if part.strip()]
    else:
        names=[part.strip('"\'') for part in shlex.split(answer,posix=False)]
    names=list(dict.fromkeys(names))
    if len(names)<2 or any(not valid_image_reference(name) for name in names):
        raise ValueError('Nhập ít nhất hai tên ảnh, không cần đuôi. Ví dụ: ANH_A, ANH_B')
    return names


def retry_merge_write(error):
    print('CHƯA GHI ĐƯỢC: Windows từ chối thay file TongHop. File có thể đang mở trong Excel/WPS hoặc bị giữ quyền ghi.')
    print('Kết quả gộp đang giữ trong file tạm. Lưu và đóng TongHop trong Excel/WPS trước khi thử lại.')
    answer=input('Enter=thử ghi lại nhóm này; Q=hủy và giữ báo cáo cũ: ').strip()
    return answer.casefold()!='q'


def show_invoices(report,refs=None):
    workbook=load_workbook(report,read_only=True)
    try:
        sheets=find_sheets(workbook,refs) if refs else workbook.worksheets
        for sheet in sheets:
            images=sheet_images(sheet)
            print(f'  {sheet.title}: {max(0,sheet.max_row-1)} dòng | '+('; '.join(images) or 'không có cột Ảnh nguồn'))
        return len(sheets)
    finally:workbook.close()


def run(report):
    if not report.is_file():
        print(f'Không tìm thấy báo cáo: {report}')
        return 1
    print(f'Báo cáo: {report}\nĐóng báo cáo trong Excel/WPS và dừng bước 03 trước khi gộp.')
    print('Chỉ chọn những ảnh bạn xác nhận thuộc CÙNG MỘT PHIẾU. Không gọi AI.')
    print('Các sheet hiện có:')
    show_invoices(report)
    while True:
        answer=input('\nNhập các tên ảnh cần gộp (ANH_A, ANH_B; không cần đuôi; Q=thoát): ').strip()
        if answer.casefold()=='q':return 0
        try:
            refs=parse_names(answer)
            with output_lock(report):
                digest=aw.delivery_report_digest(report)
                print('Các sheet được chọn:')
                count=show_invoices(report,refs)
                if count<2:
                    print('Các ảnh đã nằm chung một sheet. Không thay đổi báo cáo.')
                    continue
                confirmation=input('Nhập CO để gộp các sheet trên (Enter=hủy nhóm này): ').strip()
                if aw.normalize_name(confirmation)!='co':
                    print('Đã hủy nhóm này. Báo cáo giữ nguyên.')
                    continue
                if aw.delivery_report_digest(report)!=digest:
                    raise ValueError('Báo cáo vừa thay đổi. Chọn lại để xem dữ liệu mới trước khi gộp.')
                title=merge_saved_invoices(report,refs,retry_write=retry_merge_write)
                print(f'ĐÃ GỘP → sheet {title}. Giữ các dòng và sửa tay; đã sao lưu bản trước trong .autowatcher-backups.')
                print('Có thể nhập nhóm khác để tiếp tục. Gộp xong, chạy bước 04 để xuất lại phiếu kế toán.')
        except (OSError,ValueError) as exc:
            print(f'CHƯA GỘP: {exc}')
            print('Nếu ngày nhận khác nhau, rà/sửa ngày trong TongHop rồi thử lại. Nếu file đang mở, đóng Excel/WPS.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=BASE_DIR/'TongHopNhieuPhieuGiaoHang.xlsx')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    try:return run(args.report.resolve())
    except (KeyboardInterrupt,EOFError):
        print('\nĐã dừng. Các nhóm lưu thành công vẫn được giữ.')
        return 0
    except (OSError,ValueError) as exc:
        print(f'Chưa mở được báo cáo: {exc}')
        return 1


if __name__=='__main__':raise SystemExit(main())
