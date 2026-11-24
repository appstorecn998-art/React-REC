"""Presentation of computed PR comparison alerts; never infers from notes."""
def quantity(value):
    text=format(abs(value),'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text

def presentation(result):
    flags=set(result.get('alerts',[]));labels=[];cells={}
    if 'previous_receipt_invalid' in flags:labels.append('LẦN NHẬN TRƯỚC CẦN CẬP NHẬT')
    if 'price_approval_stale' in flags:labels.append('DUYỆT GIÁ CŨ — XÁC NHẬN LẠI')
    if result.get('price_approval'):labels.append('GIÁ MỚI ĐÃ DUYỆT')
    if 'price' in flags:
        delta=result['delivery_price']-result['price']
        direction='cao hơn' if delta>0 else 'thấp hơn'
        def money(value):
            return format(value,',f').rstrip('0').rstrip('.') if '.' in format(value,',f') else format(value,',f')
        unit=str(result.get('unit') or 'đơn vị PR')
        labels.append(f'LỆCH GIÁ: phiếu {direction} PR {money(abs(delta))}/{unit} (PR {money(result["price"])} → phiếu {money(result["delivery_price"])})');cells.update({6:('#fee2e2','#b91c1c'),7:('#fee2e2','#b91c1c')})
    if 'short' in flags:
        labels.append('THIẾU '+quantity(result['remaining']));cells.update({5:('#ffedd5','#9a3412'),8:('#ffedd5','#9a3412')})
    if 'over' in flags:
        labels.append('DƯ '+quantity(result['remaining']));cells.update({5:('#f3e8ff','#7e22ce'),8:('#f3e8ff','#7e22ce')})
    if 'receipt_correction' in flags:labels.append('NCC GHI SAI LƯỢNG/ĐVT · RÀ TIỀN')
    if 'unit' in flags:labels.append('CHƯA QUY ĐỔI')
    if 'unlinked' in flags:labels.append('CHƯA GÁN DÒNG')
    if 'duplicate_link' in flags:labels.append('TRÙNG GHÉP DÒNG')
    if 'code' in flags:labels.append('KHÁC MÃ')
    if 'specification' in flags:labels.append('RÀ QUY CÁCH')
    if not labels and {'unknown_quantity','unknown_price'}&flags:labels.append('SỐ LIỆU CHƯA RÕ')
    background='#fff1f2' if 'price' in flags else '#faf5ff' if 'over' in flags else '#fff7ed' if 'short' in flags else '#fffbeb' if labels else None
    return {'label':' · '.join(labels),'background':background,'cells':cells}
