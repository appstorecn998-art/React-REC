"""PR menu actions delegated to the same validators as desktop REC."""
from receiving_units import conversion, factor_for, converted


def apply(kind,item,delivery,row,entry,fields,previous=0):
    reason=fields.get('reason','')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Nhập căn cứ / người xác nhận.')
    value=fields.get('value','')
    if kind=='conversion':entry.update(conversion(row,item,delivery,value,reason))
    elif kind=='packaging':
        preview=package_preview(item,delivery,row,entry,fields)
        if fields.get('confirmed_quantity')!=preview['approved'] or fields.get('confirmed_cost')!=preview['extra_cost']:
            raise ValueError('Xem trước lượng mua và chi phí tăng trước khi xác nhận.')
        from receiving_packaging import approval
        entry['purchase_approval']=approval(item,delivery.get('Nhà cung cấp'),value,reason,entry)
    elif kind=='pr_quantity':
        from receiving_pr_quantity import approve
        entry['pr_quantity']=approve(item,entry,value,reason)
        entry.pop('purchase_approval',None)
    elif kind=='correction':
        from receiving_quantity_correction import correction
        entry['receipt_correction']=correction(row,item,delivery,value,fields.get('grams',''),reason)
    elif kind=='substitution':
        from receiving_substitution import approve
        entry['substitution_approval']=approve(row,item,delivery,entry,fields.get('department',''),fields.get('person',''),fields.get('date',''),reason)
    elif kind=='price':
        from receiving_price_approval import approve
        entry['price_approval']=approve(row,item,delivery,entry,value,fields.get('person',''),fields.get('date',''),reason)
    elif kind=='overreceipt':
        from receiving_pr import compare
        from receiving_overreceipt import approve
        result=compare([item],[(row,delivery)],{0:row},{0:entry})[0]
        if set(result['alerts']) & {'unit','specification','code','unknown_quantity','receipt_correction'}:
            raise ValueError('Xử lý quy cách, đơn vị, mã và lượng trước khi duyệt nhận dư.')
        entry['overreceipt_approval']=approve(row,item,delivery,entry,result['ordered'],result['received'],fields.get('person',''),reason,previous)
    else:raise ValueError('Thao tác PR không hợp lệ.')
    return entry


def package_preview(item,delivery,row,entry,fields):
    import AutoWatcher as aw
    from fractions import Fraction
    from receiving_units import exact_text
    from receiving_packaging import approval
    rule=approval(item,delivery.get('Nhà cung cấp'),fields.get('value',''),fields.get('reason',''),entry)
    factor,_=factor_for({0:entry},0,row,item,delivery)
    price=aw.parse_invoice_amount(delivery.get('Đơn giá'))
    if factor is None or price is None or price<0 or entry.get('receipt_correction'):
        raise ValueError('Cần xác nhận đúng quy đổi và giá giao trước khi duyệt đóng gói.')
    extra=Fraction(rule['approved'])-Fraction(rule['requested'])
    return dict(requested=rule['requested'],approved=rule['approved'],extra=exact_text(extra),extra_cost=exact_text(extra*Fraction(str(price))/factor),unit=item.get('unit',''))
