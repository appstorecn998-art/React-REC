"""Cumulative PR context, excluding the receipt currently being edited."""
from fractions import Fraction
from decimal import Decimal

def context(path,order_id,receipt_id,validate):
    from receiving_ledger import summary,resolve_order
    order_id=resolve_order(path,order_id)
    _,history=summary(path,validate,order_id=order_id);totals={};uncertain=set();count=0
    for record in history:
        if record['order_id']!=order_id or record['receipt_id']==receipt_id or not record['active']:continue
        count+=1
        for index,value in record['allocations'].items():
            quantity=Fraction(value)
            if str(index) in record.get('uncertain_indices',list(record['allocations']) if not record['valid'] else []):
                uncertain.add(int(index))
            else:totals[int(index)]=totals.get(int(index),Fraction(0))+quantity
    from receiving_opening_balance import read,validate
    from receiving_ledger import list_orders
    saved=read(path,order_id).get(order_id)
    if saved:
        lines=next((lines for oid,_,lines in list_orders(path) if oid==order_id),[])
        try:validate(saved,lines);valid=True
        except (OSError,ValueError,KeyError):valid=False
        for index,quantity in saved['quantities'].items():
            if Fraction(quantity)>0:
                if valid:totals[int(index)]=totals.get(int(index),Fraction(0))+Fraction(quantity)
                else:uncertain.add(int(index))
        if any(Fraction(q)>0 for q in saved['quantities'].values()):count+=1
    return totals,uncertain,count

def apply(results,totals,uncertain,count):
    if not count and not totals and not uncertain:
        for r in results:
            approval=r.get('overreceipt_approval')
            if approval and Fraction(approval.get('previous','0')):
                r['alerts'].append('overreceipt_stale');r['status']+='; Lượng nhận trước đã đổi — duyệt nhận dư lại'
        return results
    for r in results:
        p=r.get('pr_index')
        if p is None:continue
        previous=totals.get(p,Fraction(0));previous=Decimal(previous.numerator)/Decimal(previous.denominator)
        r['previous_received']=previous;r['receipt_count']=count
        # A missing line must still be explicitly marked not delivered; the
        # cumulative view never silently records an unmatched delivery as zero.
        no_delivery='Chưa giao (đã xác định)' in r.get('status','')
        current=r.get('received') if r.get('row') is not None else Decimal(0) if no_delivery else None
        if p in uncertain:
            r['previous_received']=None
            r['remaining']=None;r['alerts']=[a for a in r.get('alerts',[]) if a not in ('short','over')];r['alerts'].append('previous_receipt_invalid');r['status']='Nguồn lần nhận khác đã đổi; cần cập nhật phiếu. '+r['status']
        if current is None:continue
        r['total_received']=previous+current
        r['alerts']=[a for a in r.get('alerts',[]) if a not in ('short','over')]
        if p in uncertain:
            r['remaining']=None;continue
        r['remaining']=r['ordered']-r['total_received'] if r.get('ordered') is not None else None
        if r['remaining'] is not None:
            if r['remaining']>0:r['alerts'].append('short')
            elif r['remaining']<0:
                approval=r.get('overreceipt_approval')
                if not approval or Fraction(str(previous))!=Fraction(approval.get('previous','0')) or Fraction(str(-r['remaining']))!=Fraction(approval['excess']):r['alerts'].append('over')
                elif 'Chờ bộ phận bổ sung PR' not in r['status']:r['status']+='; Đã duyệt nhận dư '+approval['excess']+' '+str(r.get('unit',''))+' — Chờ bộ phận bổ sung PR; '+approval['reason']
        r['status']=r['status'].replace('Thiếu trong lần giao này','').replace('Nhận vượt lượng đặt','').replace('Chưa giao (đã xác định)','Không giao trong phiếu này (đã xác định)')
        if p in uncertain:
            r['status']='Nhận trước chưa xác minh; lần này: '+str(current)+'. '+r['status']
        else:
            r['status']='Đã nhận trước: '+str(previous)+'; lần này: '+str(current)+'; tổng: '+str(r['total_received'])+'. '+r['status']
    return results
