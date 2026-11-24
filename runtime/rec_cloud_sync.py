"""Durable per-day outbox, triggered by review confirmation, never OCR."""
import hashlib
import json
import tempfile
import uuid
from datetime import date
from pathlib import Path
from PySide6.QtCore import QObject, QTimer
from rec_cloud_paths import atomic_bytes
from receiving_cloud_client import CloudError
from receiving_cloud_snapshot import build_snapshot, canonical


def merge_day(current, fresh, day):
    """Replace a day's approved receipts; retain other days and prune unused images."""
    result = dict(fresh)
    result['receipts'] = [r for r in current.get('receipts', []) if r['day'] != day]
    result['receipts'] += [r for r in fresh['receipts'] if r.get('reviewed') and r.get('departments')]
    days = [day] + [r['day'] for r in result['receipts']]
    result['scope'] = dict(start=min(days), end=max(days), summary='all_posted')
    assets = {**current.get('assets', {}), **fresh['assets']}
    wanted = {key for r in result['receipts'] + result['orders'] for key in r['images']}
    result['assets'] = {k: assets[k] for k in wanted}
    result.pop('source_revision', None)
    result['source_revision'] = hashlib.sha256(canonical(result)).hexdigest()
    return result


class CloudSync(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.path = owner.root/'.receiving'/'cloud-sync-queue.json'
        self.checkpoint = owner.root/'.receiving'/'cloud-sync-checkpoint.json'
        self.running = False
        self.stop_requested = False
        self.message = "REC Cloud · Chưa đồng bộ"
        from PySide6.QtWidgets import QLabel
        self.label = QLabel(self.message); self.label.setMinimumWidth(320)
        owner.statusBar().addPermanentWidget(self.label, 1)
        self.bootstrap_done = False
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self.flush)
        self.timer.start()
        QTimer.singleShot(2000, self.flush)

    def status(self, message):
        self.message = message
        self.label.setText(message); self.label.setToolTip(message)
        self.owner.statusBar().showMessage(message)

    def fingerprint(self, report, reviews):
        from receiving_service import digest
        return [digest(p) if p.exists() else None for p in [report, reviews]]

    def read(self):
        if not self.path.exists(): return {}
        # A corrupt queue is an error, never silently replace it with an empty queue.
        value = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(value, dict): raise ValueError('Invalid outbox')
        return value

    def save(self, queue):
        atomic_bytes(self.path, json.dumps(queue, ensure_ascii=False).encode('utf-8'))

    def enqueue(self):
        queue = self.read()
        key = str(self.owner.destination.resolve()) + '|' + self.owner.day.isoformat()
        queue[key] = dict(day=self.owner.day.isoformat(), destination=str(self.owner.destination), version=uuid.uuid4().hex)
        self.save(queue)
        self.owner.statusBar().showMessage('Đã lưu trên máy · Đang chờ đồng bộ REC Cloud.')
        QTimer.singleShot(0, self.flush)

    def flush(self):
        w = self.owner
        if self.stop_requested: return
        if self.running or w.busy or getattr(w, 'sheets_sync_running', False): return
        view = getattr(w, '_cloud_window', None)
        if view and view.busy: return
        if getattr(w, 'cloud_manual_publish', False): return
        client = getattr(w, '_cloud_client', None)
        if not client or not client.token or client.role != 'publisher': return
        try: queue = self.read()
        except (OSError, ValueError):
            w.statusBar().showMessage('Chưa đọc được hàng chờ REC Cloud; cần kiểm tra, dữ liệu trên máy được giữ.'); return
        selected = next(((k, v) for k, v in queue.items() if Path(v['destination']).resolve() == w.destination.resolve()), None)
        if not selected and not self.bootstrap_done:
            self.bootstrap_done = True
            from receiving_service import paths, snapshot, sheet_signature
            from datetime import timedelta
            # Import existing confirmed days once per app run; queue survives restart.
            try:
                queue = self.read()
                try: checkpoints = json.loads(self.checkpoint.read_text(encoding='utf-8'))
                except FileNotFoundError: checkpoints = {}
                for report in w.destination.rglob('TongHop*.xlsx'):
                    import re
                    match = re.search(r'(20\d{2})-(\d{2})-(\d{2})', report.stem)
                    if match:
                        day = date(*map(int, match.groups()))
                    else:
                        match = re.search(r'(\d{2})-(\d{2})-(20\d{2})', report.stem)
                        if not match: continue
                        day = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                    folder, actual = paths(w.root, day, w.destination)
                    if actual.resolve() != report.resolve(): continue
                    reviews_path = folder/'reviewed.json'
                    if not reviews_path.exists(): continue
                    reviews = json.loads(reviews_path.read_text(encoding='utf-8'))
                    if not reviews: continue
                    key = str(w.destination.resolve())+'|'+day.isoformat()
                    if checkpoints.get(key) == self.fingerprint(report, reviews_path): continue
                    queue.setdefault(key, dict(day=day.isoformat(), destination=str(w.destination), version=uuid.uuid4().hex))
                self.save(queue)
                selected = next(((k,v) for k,v in queue.items() if Path(v['destination']).resolve() == w.destination.resolve()), None)
            except (OSError, ValueError):
                w.statusBar().showMessage('Chưa chuẩn bị được đồng bộ các ngày đã kiểm; dữ liệu trên máy được giữ.')
        if not selected:
            self.status('REC Cloud · Đã hoàn tất đồng bộ, không còn ngày chờ.'); return
        key, entry = selected
        root = w.root
        completed_fingerprint = []
        from rec_cloud_window import Task
        from receiving_service import paths, digest

        def work(emit):
            def progress(message):
                if self.stop_requested: raise CloudError('Đã yêu cầu dừng đồng bộ; hàng chờ được giữ.')
                emit(message)
            progress('Đang kết nối…')
            build = client.request('GET', '/health').get('build')
            if build not in {'department-acl-5', 'access-admin-6'}:
                raise CloudError('Cần cập nhật Worker phân quyền trước khi tự đồng bộ.')
            from warehouse_directory import load_warehouse_directory
            departments = {d.casefold() for _,d in load_warehouse_directory(root/'DanhMuc.xlsm').values() if d} if (root/'DanhMuc.xlsm').exists() else set()
            if build == 'access-admin-6' and 'kc' in departments and 'kitchen' not in departments:
                for account in client.request('GET', '/access')['accounts']:
                    if account['username'] == 'kit' and account['departments'] == ['kitchen']:
                        client.request('PUT', '/access', {'username': 'kit', 'departments': ['KC']})
            day = date.fromisoformat(entry['day'])
            folder, report = paths(root, day, Path(entry['destination']))
            evidence = [report, folder/'reviewed.json']
            before = {p: digest(p) if p.exists() else None for p in evidence}
            def unchanged():
                if self.stop_requested: raise CloudError('Đã dừng đồng bộ; hàng chờ được giữ.')
                if any((digest(p) if p.exists() else None) != signature for p, signature in before.items()):
                    raise CloudError('Phiếu vừa đổi; sẽ chuẩn bị lại bản đồng bộ.')
            with tempfile.TemporaryDirectory(prefix='rec-sync-') as stage:
                fresh, files = build_snapshot(root, Path(entry['destination']), day, day, stage, evidence=before)
                try:
                    remote = client.dataset()
                    current, revision = remote['dataset'], remote['revision']
                except CloudError as error:
                    if error.status != 404: raise
                    current, revision = {}, client.state()['revision']
                dataset = merge_day(current, fresh, entry['day'])
                unchanged()
                completed_fingerprint[:] = self.fingerprint(report, folder/'reviewed.json')
                if current.get('source_revision') == dataset['source_revision']: return {'revision': revision}
                return client.publish(dataset, files, revision, progress, before_commit=unchanged, known_assets=current.get('assets', {}))

        self.running = True; self.last_success = False
        job = Task(work); self.job = job
        self.status('REC Cloud · Ngày '+entry['day']+' · Còn '+str(len(queue))+' ngày dữ liệu chờ đồng bộ')
        job.signals.progress.connect(lambda text: self.status('REC Cloud · '+entry['day']+' · '+text+' · Còn '+str(len(queue))+' ngày dữ liệu chờ đồng bộ'))
        def done(result):
            self.last_success = True
            try:
                pending = self.read()
                if completed_fingerprint:
                    try: checkpoints = json.loads(self.checkpoint.read_text(encoding='utf-8'))
                    except FileNotFoundError: checkpoints = {}
                    checkpoints[key] = completed_fingerprint; atomic_bytes(self.checkpoint, canonical(checkpoints))
                if pending.get(key, {}).get('version') == entry['version']:
                    pending.pop(key); self.save(pending)
            except (OSError, ValueError):
                w.statusBar().showMessage('Cloud đã nhận dữ liệu; hàng chờ chưa lưu được, sẽ thử lại an toàn.'); return
            self.status('REC Cloud · Đã đồng bộ bản '+str(result['revision'])+' · Còn '+str(len(pending))+' ngày dữ liệu chờ đồng bộ')
        def failed(message):
            try:
                pending = self.read()
                if key in pending:
                    failed_entry = pending.pop(key); pending[key] = failed_entry; self.save(pending)
            except (OSError, ValueError): pass
            self.status('REC Cloud chưa đồng bộ · '+message+' · Hàng chờ được giữ.')
        def finished():
            self.running = False
            self.job = None
            if self.stop_requested:
                QTimer.singleShot(0, w.close); return
            QTimer.singleShot(1000, self.flush) if getattr(self, 'last_success', False) else None
        job.signals.result.connect(done); job.signals.error.connect(failed); job.signals.finished.connect(finished)
        w.thread_pool.start(job)


def attach(owner):
    owner._cloud_sync = CloudSync(owner)


def enqueue(owner):
    sync = getattr(owner, '_cloud_sync', None)
    if sync:
        try: sync.enqueue()
        except (OSError, ValueError):
            owner.statusBar().showMessage('Đã lưu phiếu nhưng chưa ghi được hàng chờ REC Cloud; cần thử đồng bộ lại.')
