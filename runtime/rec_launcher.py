"""Single entry point for GUI, workers, diagnostics and frozen builds."""
import os
import sys


def main():
    for stream in (sys.stdout,sys.stderr):
        if stream is not None and hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8",errors="replace")
    args=sys.argv[1:]
    if '--data-root' in args:
        i=args.index('--data-root')
        os.environ['REC_DATA_DIR']=args[i+1]; del args[i:i+2]
    if '--cloud-viewer' in args:
        args.remove('--cloud-viewer')
        sys.argv=[sys.argv[0],*args]
        from rec_cloud_window import main as cloud_viewer
        return cloud_viewer()
    from rec_runtime import initialize
    root=initialize()
    os.environ['REC_DATA_DIR']=str(root)
    if '--rec-worker' in args:
        args.remove('--rec-worker')
        sys.argv=[sys.argv[0],'--worker',*args]
        if not os.environ.get('GEMINI_API_KEY','').strip():
            try:has_key=bool((root/'gemini_api_key.txt').read_text(encoding='utf-8-sig').strip())
            except OSError:has_key=False
            if not has_key:
                print('Chưa có khóa Gemini. Mở Cài đặt → Thiết lập máy để nhập khóa.',flush=True);return 2
        from receiving_app import worker
        try:return worker()
        except Exception as exc:
            detail=str(exc)
            secrets=[os.environ.get('GEMINI_API_KEY','').strip()]
            try:secrets.append((root/'gemini_api_key.txt').read_text(encoding='utf-8-sig').strip())
            except OSError:pass
            for secret in secrets:
                if secret:detail=detail.replace(secret,'[KEY]')
            print('Chưa xử lý được: '+type(exc).__name__+': '+detail,flush=True)
            return 1
    if '--rec-locate' in args:
        args.remove('--rec-locate')
        import json
        from receiving_review import locate_page
        try:print(json.dumps(locate_page(*args),ensure_ascii=False),flush=True);return 0
        except Exception:
            if os.environ.get('REC_DIAGNOSTICS')=='1':__import__('traceback').print_exc()
            print('Không định vị được ảnh; kiểm tra model OCR và ảnh nguồn.',file=sys.stderr);return 1
    if '--click-benchmark' in args:
        from rec_click_benchmark import run
        import json
        i=args.index('--click-benchmark')
        print(json.dumps(run(args[i+1] if len(args)>i+1 else None)),flush=True);return 0
    if '--check-config' in args:
        import json
        from rec_runtime import config_check
        print(json.dumps(config_check(root),ensure_ascii=False),flush=True);return 0
    if '--self-test' in args:
        from rec_acceptance import run
        import json
        result=run(root);print(json.dumps(result,ensure_ascii=False),flush=True)
        return 0 if result['ok'] else 1
    sys.argv=[sys.argv[0],*args]
    from receiving_qt import main as gui
    return gui()


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
