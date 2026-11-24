"""Read-only PR provenance for price comparisons."""
import hashlib
import json
from pathlib import Path


def receipt_pr_numbers(sheet, rows, images, folder, orders):
    from receiving_service import invoice_images, digest
    from receiving_image_archive import image_name, source_digest
    manual=manual_reference(folder,sheet,rows)
    if manual:return [manual]
    refs = invoice_images(sheet, rows)
    sources = [p for p in images if image_name(p) in refs]
    if not sources:
        return []
    for hash_image in (source_digest, digest):
        identities = sorted((image_name(p), hash_image(p)) for p in sources)
        key = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
        path = Path(folder)/'.receiving'/'manual-pr-links'/(key+'.json')
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        record = orders.get(data.get('library_key'))
        if data.get('source') == 'pr-library' and record and record.get('images') == data.get('paths'):
            number = str(record.get('number') or '').strip()
            return [number] if number else []
        # Manually selected PR pages retain their number in the saved comparison.
        from receiving_pr_image_identity import pr_images_match
        if data.get('source') == 'pr-library':
            return []
        selected = [p for p in images if any(
            image_name(p) == image_name(name) and value in (source_digest(p), digest(p))
            for name, value in data.get('images', {}).items())]
        if not pr_images_match(data.get('images'), selected):
            return []
        comparison = path.with_suffix('.comparison.json')
        if comparison.exists():
            saved = json.loads(comparison.read_text(encoding='utf-8'))
            if pr_images_match(saved.get('images'), selected):
                return sorted({str(item.get('pr_reference_id') or '').strip()
                               for item in saved.get('pr_items', [])} - {''})
        return []
    return []


def pr_label(entry):
    if entry.get('pr_error'):return 'Chưa đọc được PR — cần kiểm tra liên kết'
    return ', '.join(entry.get('pr_numbers') or []) or 'Chưa rõ số PR'


def format_price(value):
    from decimal import Decimal
    text = format(Decimal(value), ',f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace(',', '_').replace('.', ',').replace('_', '.')


def reference_path(folder):return Path(folder)/'price-pr-references.json'


def manual_reference(folder,sheet,rows):
    from receiving_service import sheet_signature
    path=reference_path(folder)
    if not path.exists():return ''
    saved=json.loads(path.read_text(encoding='utf-8')).get('receipts',{}).get(sheet,{})
    return str(saved.get('number','')) if saved.get('signature')==sheet_signature(sheet,rows) else ''


def save_reference(report,sheet,number,expected_signature,expected_reference):
    from datetime import datetime
    from receiving_service import snapshot,sheet_signature,atomic_json
    from multi_delivery import output_lock
    report=Path(report);path=reference_path(report.parent/'.receiving')
    number=str(number).strip()
    if len(number)>120 or any(ord(c)<32 for c in number):raise ValueError('Số PR tối đa 120 ký tự, không xuống dòng.')
    path.parent.mkdir(parents=True,exist_ok=True)
    # Lock the source report too: bind to the exact receipt the user selected.
    with output_lock(report),output_lock(path):
        _,data=snapshot(report);rows=dict(data).get(sheet)
        if rows is None or sheet_signature(sheet,rows)!=expected_signature:raise ValueError('Phiếu đã đổi. Tải lại bảng Giá mua rồi nhập số PR.')
        stored=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'receipts':{},'history':[]}
        current=manual_reference(report.parent/'.receiving',sheet,rows)
        if current!=expected_reference:raise ValueError('Số PR vừa được sửa ở nơi khác. Tải lại trước khi lưu.')
        previous=stored['receipts'].get(sheet)
        if number:stored['receipts'][sheet]={'number':number,'signature':expected_signature,'source':'manual_reference'}
        else:stored['receipts'].pop(sheet,None)
        stored.setdefault('history',[]).append(dict(sheet=sheet,before=previous,number=number,time=datetime.now().astimezone().isoformat()))
        atomic_json(path,stored)
