"""Adapter to the original REC worker. Run as its own process, never in HTTP threads."""
import os,sys
from pathlib import Path

from local_runtime import APP,activate
activate()
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--day',required=True);parser.add_argument('--store',required=True);parser.add_argument('--profile',required=True);parser.add_argument('--quality-report',required=True);parser.add_argument('--enhanced',action='store_true')
    args=parser.parse_args()
    os.environ['REC_DATA_DIR']=args.profile
    from ocr_quality import install
    install(args.quality_report,enhanced=args.enhanced)
    import json
    from ocr_events import listener
    listener.set(lambda stage,message,details:print('REC_OCR_EVENT '+json.dumps({'stage':stage,'message':message,'details':details},ensure_ascii=False),flush=True))
    # Same launcher/auth/error handling and incremental worker used by desktop REC.
    import rec_launcher
    sys.argv=[str(APP/'rec_launcher.py'),'--rec-worker','--data-root',args.profile,args.day,args.store]
    raise SystemExit(rec_launcher.main())
