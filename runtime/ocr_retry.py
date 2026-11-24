"""Bounded retries for transient API failures; never retries invalid credentials or data."""
import logging,time
import httpx

def transient(exc):
    status=getattr(exc,'status_code',None) or getattr(exc,'code',None)
    response=getattr(exc,'response',None)
    status=status or getattr(response,'status_code',None)
    return status in {408,429,500,502,503,504} or isinstance(exc,(TimeoutError,ConnectionError,httpx.TransportError)) or type(exc).__name__ in {'APIConnectionError','APITimeoutError'}

def retry_delay(exc,attempt):
    response=getattr(exc,'response',None)
    try:value=float(response.headers.get('Retry-After','0')) if response is not None else 0
    except (ValueError,TypeError):value=0
    return min(60,max(value,(15,30)[attempt-1]))

def call(operation,label,unchanged=lambda:True):
    for attempt in range(1,4):
        try:return operation()
        except Exception as exc:
            if not transient(exc) or attempt==3:raise
            delay=retry_delay(exc,attempt)
            logging.warning('%s: lỗi tạm thời %s; chờ %.0f giây, thử lại %s/3.',label,type(exc).__name__,delay,attempt+1)
            time.sleep(delay)
            if not unchanged():raise ValueError('Ảnh thay đổi trong lúc thử lại: '+label) from None

def explicit_start(document):
    items=document.get('items') or []
    first=str(items[0].get('source_stt','')).strip() if items else ''
    from delivery_pages import page_number, stt_number
    page = page_number(document.get('page_number'))
    if page and page > 1:
        return False
    return bool(document.get('supplier_name') and (stt_number(first) == 1 or page == 1))
