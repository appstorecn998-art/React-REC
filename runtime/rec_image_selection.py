"""Constrain a manual worker to explicitly selected source hashes."""
import json
def select_images(images,raw):
    if raw is None:return list(images)
    from receiving_service import digest
    hashes=json.loads(raw)
    if not isinstance(hashes,list) or not hashes or any(not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in hashes):
        raise ValueError('Danh sách ảnh chọn không hợp lệ. Chọn ảnh lại trước khi đọc.')
    expected=set(hashes);selected=[];seen=set()
    for p in images:
        key=digest(p)
        if key in expected and key not in seen:selected.append(p);seen.add(key)
    if seen!=expected:raise ValueError('Ảnh chọn đã thay đổi hoặc không còn trong ngày nhận.')
    return selected
