"""Import the explicitly selected legacy snapshot; never write to its source."""
import argparse
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_runtime import activate
activate()
from multi_delivery import output_lock
from PySide6.QtCore import QLockFile

SKIP = {'.autowatcher-backups', 'ledger-backups', 'models', '__pycache__',
        'format-order-backups', 'settings-backups'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rebase(value, mappings):
    if isinstance(value, str):
        for source, target in mappings:
            value = value.replace(str(source), str(target)).replace(source.as_posix(), target.as_posix())
        return value
    if isinstance(value, list):
        return [rebase(v, mappings) for v in value]
    if isinstance(value, dict):
        return {rebase(k, mappings): rebase(v, mappings) for k, v in value.items()}
    return value


def combine(old, current, name):
    # Keep React-only PR records and archived images, with legacy values for shared records.
    if name == 'index.json' and isinstance(old, dict) and 'orders' in old:
        return {**old, 'orders': {**current.get('orders', {}), **old['orders']}}
    if name == 'image-archive.json':
        def directories(value):
            return value.get('directories', []) + ([value['directory']] if value.get('directory') else [])
        return {**old, 'directories': list(dict.fromkeys(directories(old) + directories(current)))}
    if name == 'image-manifest.json' and isinstance(old, dict) and isinstance(old.get('files'), list):
        entries = {v['target']: v for v in current.get('files', [])}
        entries.update({v['target']: v for v in old['files']})
        return {**old, 'files': list(entries.values())}
    if isinstance(old, dict) and isinstance(current, dict):
        return {**current, **{k: combine(v, current.get(k), '') for k,v in old.items()}}
    return old


def run(legacy, apply=False):
    desktop_lock = QLockFile(str(ROOT/'output/desktop.lock'))
    if apply and not desktop_lock.tryLock(0):
        raise ValueError('Close React REC before importing; desktop is running.')
    legacy = legacy.resolve()
    mappings = [(legacy/'Data/Phieu giao hang hang thang', ROOT/'local-data/receipts'),
                (legacy/'Data/REC_CongNo', ROOT/'local-data/debt'),
                (legacy/'Data/Phieu giao hang hang ngay', ROOT/'local-data/daily'),
                (legacy/'DN_Image', ROOT/'local-data/DN_Image'),
                (Path(os.environ['LOCALAPPDATA'])/'REC', ROOT/'local-profile')]
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    bundle = ROOT/'output'/('legacy-import-'+stamp)
    bundle.mkdir(parents=True)
    changes, sources, proofs = [], [], {}
    proof_path = ROOT/'local-data/receipts/.receiving/import-path-hashes.json'
    if proof_path.exists():
        proofs = json.loads(proof_path.read_text(encoding='utf8'))
    for index, (source, destination) in enumerate(mappings):
        if not source.is_dir():
            raise ValueError('Missing source directory: '+str(source))
        for path in sorted(source.rglob('*')):
            rel = path.relative_to(source)
            if not path.is_file() or any(p in SKIP for p in rel.parts):
                continue
            if path.suffix in ('.lock', '.tmp', '.pyc') or '.sqlite-' in path.name or path.name.startswith('~$'):
                continue
            # Import business data only; keep React's credentials and app settings.
            if index == 4 and rel.as_posix() not in {
                'DanhMuc.xlsm', 'NhaCungCap.json', 'QUY_TAC_NHA_CUNG_CAP.txt',
                'Phieu giao hang ngay X.xlsx', 'daily-work-template.xlsx'}:
                continue
            original = path.read_bytes()
            sources.append((path, sha(original)))
            target = destination/rel
            current = target.read_bytes() if target.exists() else None
            data = original
            if path.suffix == '.json':
                value = rebase(json.loads(original.decode('utf-8-sig')), mappings)
                if current is not None:
                    existing = json.loads(current.decode('utf-8-sig'))
                    value = combine(value, existing, path.name)
                    if value == existing:
                        continue
                data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf8')
                if index == 0:
                    proofs[str(target.resolve())] = {'source_sha256': sha(original), 'local_sha256': sha(data)}
            if data == current:
                continue
            if path.suffix == '.sqlite':
                raise ValueError('Ledger differs or is missing; requires a SQLite snapshot/record-level merge: '+str(target))
            key = target.relative_to(ROOT)
            staged = bundle/'staged'/key
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(data)
            changes.append(dict(target=str(target), relative=str(key), before=sha(current) if current is not None else None,
                                after=sha(data), source=str(path)))
    proof_data = json.dumps(proofs, ensure_ascii=False, indent=2).encode('utf8')
    current = proof_path.read_bytes() if proof_path.exists() else None
    if proof_data != current:
        key = proof_path.relative_to(ROOT)
        staged = bundle/'staged'/key
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(proof_data)
        changes.append(dict(target=str(proof_path), relative=str(key), before=sha(current) if current else None,
                            after=sha(proof_data), source=None))
    manifest = dict(status='staged', policy='legacy authoritative; retain React-only files and PR records',
                    changes=changes, source_hashes={str(p): h for p,h in sources})
    manifest_path = bundle/'manifest.json'
    def save():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    save()
    print(json.dumps({'bundle': str(bundle), 'changes': len(changes), 'apply': apply}), flush=True)
    if not apply:
        return bundle
    written = []
    with ExitStack() as stack:
        for entry in changes:
            target = Path(entry['target'])
            target.parent.mkdir(parents=True, exist_ok=True)
            stack.enter_context(output_lock(target))
        for path, expected in sources:
            if sha(path.read_bytes()) != expected:
                raise ValueError('Source changed during staging: '+str(path))
        for entry in changes:
            target = Path(entry['target'])
            actual = sha(target.read_bytes()) if target.exists() else None
            if actual != entry['before']:
                raise ValueError('React data changed during staging: '+str(target))
            if actual is not None:
                backup = bundle/'before'/entry['relative']
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
        try:
            for entry in changes:
                target = Path(entry['target'])
                actual = sha(target.read_bytes()) if target.exists() else None
                if actual != entry['before']:
                    raise ValueError('React data changed before replacement: '+str(target))
                data = (bundle/'staged'/entry['relative']).read_bytes()
                if sha(data) != entry['after']:
                    raise ValueError('Staged file changed: '+str(target))
                temporary = target.with_name(target.name+'.legacy-import.tmp')
                temporary.write_bytes(data)
                os.replace(temporary, target)
                written.append(entry)
            for entry in changes:
                assert sha(Path(entry['target']).read_bytes()) == entry['after']
            for path, expected in sources:
                if sha(path.read_bytes()) != expected:
                    raise ValueError('Legacy changed during import; retry from a stable snapshot: '+str(path))
        except BaseException:
            for entry in reversed(written):
                target = Path(entry['target'])
                if entry['before'] is None:
                    target.unlink()
                else:
                    shutil.copy2(bundle/'before'/entry['relative'], target)
            manifest['status'] = 'rolled-back'
            save()
            raise
    manifest['status'] = 'complete'
    save()
    return bundle


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--legacy', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    run(args.legacy, args.apply)
