"""Inventory of source receipts, including receipts never posted to the ledger."""
import json
from pathlib import Path
from datetime import datetime
from functools import lru_cache

@lru_cache(maxsize=128)
def _sheets(path, size, mtime):
    return snapshot(Path(path))[1]

from receiving_service import snapshot,sheet_signature,invoice_images,day_images

def collect(root,history,*,reports=None):
    recorded={(str(Path(p['report']).resolve()).casefold(),p['sheet']):p for p in history if p['active']};result=[]
    for report in Path(root).rglob('TongHopPhieuNgay_*.xlsx') if reports is None else reports:
        if '.autowatcher-backups' in str(report):continue
        try:
            day=datetime.strptime(report.stem.removeprefix('TongHopPhieuNgay_'),'%d-%m-%Y').date().isoformat()
            stat=report.stat();sheets=_sheets(str(report.resolve()),stat.st_size,stat.st_mtime_ns);folder=report.parent/'.receiving'
            from receiving_no_po import active
            images=day_images(report.parent)
            # Respect the app's existing per-day data folder convention.
            from receiving_service import paths
            for sheet,rows in sheets:
                if not rows:continue
                record=recorded.get((str(report.resolve()).casefold(),sheet));supplier=' / '.join(sorted({str(v.get('Nhà cung cấp') or '').strip() for _,v in rows}-{''}))
                no_po=active(folder,sheet,rows,images) if not record and (folder/'.receiving/no-po').is_dir() else False
                status='Đã ghi sổ' if record and record['valid'] else 'Cần kiểm tra lại' if record else 'Không có PR/PO' if no_po else 'Chưa ghi sổ'
                result.append(dict(day=day,sheet=sheet,report=str(report),supplier=supplier,count=len(rows),status=status,record=record,rows=rows))
        except (OSError,ValueError,KeyError):continue
    # Include historical reports outside the currently selected source tree.
    seen={(str(Path(r['report']).resolve()).casefold(),r['sheet']) for r in result}
    for p in history:
        key=(str(Path(p['report']).resolve()).casefold(),p['sheet'])
        if not p['active'] or key in seen:continue
        result.append(dict(day=p['day'],sheet=p['sheet'],report=p['report'],supplier=p.get('supplier_name',''),count=len(p['allocations']),status='Đã ghi sổ' if p['valid'] else 'Cần kiểm tra lại',record=p,rows=[]));seen.add(key)
    return sorted(result,key=lambda r:(r['day'],r['sheet']),reverse=True)
