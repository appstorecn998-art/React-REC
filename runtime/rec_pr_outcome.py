from decimal import Decimal

def receipt_outcome(result,prior_count=0):
    if result.get('pr_index') is None and result.get('received')==0:return 'Không nhận lần này'
    if result.get('deposit'):return 'Tiền cọc ngoài PR đã xác nhận'
    flags=result.get('alerts',[])
    if result.get('pr_index') is None:return 'Chưa gán PR'
    if result.get('row') is None and 'đã xác định' not in str(result.get('status','')).lower():return 'Chưa gán dòng'
    if 'unit' in flags:return 'Cần quy đổi ĐVT'
    if 'duplicate_link' in flags:return 'Cần sửa cặp gán trùng'
    current_only='previous_receipt_invalid' in flags
    remaining=result.get('remaining')
    if current_only:
        received=result.get('received') if result.get('row') is not None else 0
        ordered=result.get('ordered')
        remaining=Decimal(str(ordered))-Decimal(str(received)) if ordered is not None and received is not None else None
    if remaining is None:return 'Chưa rõ lượng'
    remaining=Decimal(str(remaining))
    if not remaining:return 'Đủ lần này' if current_only else 'Đủ'
    amount=format(abs(remaining),'f')
    if '.' in amount:amount=amount.rstrip('0').rstrip('.')
    unit=str(result.get('unit') or '')
    return ('Thiếu ' if remaining>0 else 'Dư ')+amount.replace('.',',')+(' '+unit if unit else '')+(' lần này' if current_only else '')

def has_previous_receipts(results,prior_count):
    return prior_count>0 or any(r.get('previous_received') is not None and Decimal(str(r['previous_received']))!=0 for r in results)


def price_summary(result):
    def money(value):
        if value is None:return '—'
        return format(Decimal(str(value)),',.2f').rstrip('0').rstrip('.')
    unit=str(result.get('unit') or '')
    pr='PR: '+money(result.get('price'))
    if result.get('price_approval'):pr='PR gốc: '+money(result.get('original_pr_price'))+' → duyệt: '+money(result.get('price'))
    if 'unit' in result.get('alerts',[]):return pr+(' đ/'+unit if unit else '')+' · Phiếu: '+money(result.get('delivery_price'))+' (chưa quy đổi)'
    return pr+' · Phiếu: '+money(result.get('delivery_price'))+(' đ/'+unit if unit else '')

def review_outcome(result,prior_count=0):
    text=receipt_outcome(result,prior_count)
    if result.get('no_topup'):text+=(' · Tiếp tục giao bù' if result['no_topup'].get('action')=='reopen' else ' · Không cần giao bù')
    flags=set(result.get('alerts',[]))
    warnings=[label for flag,label in [('price','Lệch giá'),('unknown_price','Chưa rõ giá'),('price_approval_stale','Duyệt giá cần rà lại'),('substitution_stale','Duyệt hàng thay thế cần rà lại'),('specification','Cần rà quy cách'),('code','Khác mã'),('receipt_correction','Cần xác minh tiền NCC')] if flag in flags]
    if 'Hàng thay thế đã duyệt:' in str(result.get('status','')):text+=' · Hàng thay thế đã duyệt'
    if warnings:text+=' · '+ ' · '.join(warnings)
    show_price=bool(flags & {'price','unknown_price','price_approval_stale','unit'})
    return text+('\n'+price_summary(result) if show_price else '')


def outcome_color(result,prior_count=0):
    text=receipt_outcome(result,prior_count)
    if result.get('no_topup'):text+=(' · Tiếp tục giao bù' if result['no_topup'].get('action')=='reopen' else ' · Không cần giao bù')
    flags=set(result.get('alerts',[]))
    if text.startswith('Thiếu'):return '#b91c1c'
    if text.startswith('Dư'):return '#2563eb'
    if flags & {'price','unknown_price','price_approval_stale'}:return '#b91c1c'
    if text.startswith('Đủ'):return '#15803d'
    return '#b7791f'
