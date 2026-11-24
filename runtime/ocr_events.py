"""Optional per-call diagnostics; no global handlers or credentials."""
from contextvars import ContextVar
listener=ContextVar('ocr_event_listener',default=None)

def emit(stage,message,**details):
    callback=listener.get()
    if callback:callback(stage,message,details)
