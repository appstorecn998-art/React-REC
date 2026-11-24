"""Quantity validity independent of presentation/financial metadata changes."""
import json
from pathlib import Path
from receiving_service import snapshot,sheet_signature,digest
class Validation(dict):
    def __bool__(self):return not self.get('uncertain')
CRITICAL=('Ngày nhận hàng xác nhận','Tên hàng trên phiếu (Ảnh)','Mã vật tư','Đơn vị tính','Đơn vị trên phiếu','Số lượng','Thực nhận','Nhà cung cấp','Ảnh nguồn','Các ảnh cùng phiếu','SHA-256 ảnh nguồn')
def check(p,cache=None):
    all_indices=set(p.get('allocations',{}));bad=set();reasons=[]
    try:
        key=('rows',p['report']);cache=cache if cache is not None else {}
        if key not in cache:cache[key]=dict(snapshot(p['report'])[1])
        rows=cache[key].get(p['sheet']);current=sheet_signature(p['sheet'],rows) if rows else None
        reviews=json.loads(Path(p['reviews_path']).read_text(encoding='utf-8'))
        if reviews.get(p['sheet']) not in {p['signature'],current}:bad|=all_indices;reasons.append('Xác nhận bị gỡ hoặc không còn hợp lệ')
        if digest(p['pr_link_path'])!=p['pr_link_hash']:bad|=all_indices;reasons.append('Liên kết PR thay đổi')
        if any(not Path(name).is_file() or digest(name)!=h for name,h in {**p['source_images'],**p['pr_images']}.items()):bad|=all_indices;reasons.append('Ảnh nguồn thay đổi hoặc mất')
        if current!=p['signature']:
            before=dict(p.get('source_rows',[]));after=dict(rows or []);links=p.get('allocation_rows')
            if not before or links is None or before.keys()!=after.keys():bad|=all_indices;reasons.append('Nguồn cũ thiếu bản chụp hoặc số dòng thay đổi')
            else:
                changed={r for r in before if any(str(before[r].get(k,''))!=str(after[r].get(k,'')) for k in CRITICAL)}
                for index,row in links.items():
                    physical_rows = row if isinstance(row, (list, tuple)) else [row]
                    if changed.intersection(physical_rows):bad.add(str(index))
                if changed:reasons.append('Dữ liệu lượng/nhận diện thay đổi ở dòng '+','.join(map(str,sorted(changed))))
                else:reasons.append('Chỉ thay metadata/giá; lượng đã duyệt giữ nguyên')
        return Validation(uncertain=sorted(bad,key=int),reasons=reasons)
    except (OSError,ValueError,KeyError,TypeError):return Validation(uncertain=sorted(all_indices,key=int),reasons=['Không xác minh được nguồn'])
