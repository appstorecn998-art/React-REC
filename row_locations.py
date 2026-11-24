"""Local, persisted name anchors on the same prepared pixels used by OCR.

No cloud calls, model downloads or row-order guesses. Tesseract is optional:
unavailable/ambiguous anchors remain pending instead of inventing coordinates.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import preview_cache
from difflib import SequenceMatcher
from page_geometry import norm

VERSION = 'prepared-name-anchors-v1'
_lock = threading.Lock()


def executable():
    command = shutil.which('tesseract')
    if command:
        return command
    for base in (os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if base:
            path = Path(base) / 'Tesseract-OCR' / 'tesseract.exe'
            if path.is_file():
                return str(path)
    return None


def read_words(path, command):
    result = subprocess.run(
        [command, str(path), 'stdout', '-l', 'eng', '--psm', '6', 'tsv'],
        capture_output=True, check=True, timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    lines = {}
    for word in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')), delimiter='\t'):
        text = word.get('text', '').strip()
        if not text or float(word.get('conf', '-1')) < 30:
            continue
        key = tuple(word[k] for k in ('block_num', 'par_num', 'line_num'))
        lines.setdefault(key, []).append(word)
    output = []
    # Prefixes/suffixes allow names to match without numerical table columns.
    for words in lines.values():
        for start in range(len(words)):
            for stop in range(start + 1, min(len(words), start + 20) + 1):
                group = words[start:stop]
                left = min(int(w['left']) for w in group)
                top = min(int(w['top']) for w in group)
                right = max(int(w['left']) + int(w['width']) for w in group)
                bottom = max(int(w['top']) + int(w['height']) for w in group)
                output.append(([[left, top], [right, top], [right, bottom], [left, bottom]],
                               ' '.join(w['text'] for w in group),
                               min(float(w['conf']) for w in group) / 100))
    return output


def separators(path):
    import cv2
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []
    height, width = image.shape
    binary = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 15)
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, width//4), 1)))
    occupied = (horizontal > 0).sum(axis=1) > width * .45
    runs = []
    for y, active in enumerate(occupied):
        if active:
            if runs and y <= runs[-1][-1] + 2:
                runs[-1].append(y)
            else:
                runs.append([y])
    return [sum(run)/len(run)/height for run in runs]


def record_document(path, document):
    """Save optional row boxes returned by the existing OCR call, no extra call."""
    prepared = preview_cache.build(path)
    # The OCR wrapper tags the exact variant it sent. Rotation/content changes
    # during a request must never relabel old coordinates as a new variant.
    if document.get('_rec_prepared_key') != prepared['cache_key']:
        return
    boxes = []
    for item in document.get('items', []):
        try:
            values = [float(v.strip()) / 1000 for v in item.get('row_box', '').split(',')]
            if len(values) != 4:
                continue
            top, left, bottom, right = values
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1 and bottom-top <= .15):
                continue
            text = str(item.get('item_name') or '').strip()
            if not text:
                continue
            boxes.append(dict(text=text, normalized=norm(text), x=left, y=top,
                              right=right, bottom=bottom))
        except (ValueError, TypeError, AttributeError):
            continue
    if not boxes:
        return
    target = preview_cache.ROOT / 'row-locations' / (prepared['cache_key'] + '-ocr.json')
    data = dict(imageKey=prepared['cache_key'], candidates=boxes, status='ready',
                separators=separators(preview_cache.ROOT / prepared['file']))
    preview_cache._atomic_write(target, lambda p: p.write_text(json.dumps(data), encoding='utf-8'))


def prepare_page(path):
    prepared = preview_cache.build(path)
    evidence = preview_cache.ROOT / 'row-locations' / (prepared['cache_key'] + '-ocr.json')
    if evidence.is_file():
        try:
            data = json.loads(evidence.read_text(encoding='utf-8'))
            if data.get('imageKey') == prepared['cache_key']:
                return prepared, data
        except (OSError, ValueError):
            pass
    folder = preview_cache.ROOT / 'row-locations'
    target = folder / (prepared['cache_key'] + '-' + VERSION + '.json')
    with _lock:
        if target.is_file():
            try:
                data = json.loads(target.read_text(encoding='utf-8'))
                if data.get('imageKey') == prepared['cache_key']:
                    return prepared, data
            except (OSError, ValueError):
                pass
        command = executable()
        if not command:
            return prepared, dict(imageKey=prepared['cache_key'], candidates=[], status='unavailable')
        try:
            words = read_words(preview_cache.ROOT / prepared['file'], command)
        except (OSError, ValueError, subprocess.SubprocessError):
            return prepared, dict(imageKey=prepared['cache_key'], candidates=[], status='failed')
        width, height = prepared['width'], prepared['height']
        boxes = [dict(text=text, normalized=norm(text), x=poly[0][0]/width,
                      y=poly[0][1]/height, right=poly[2][0]/width,
                      bottom=poly[2][1]/height) for poly, text, _ in words]
        data = dict(imageKey=prepared['cache_key'], status='ready', candidates=boxes,
                    separators=separators(preview_cache.ROOT / prepared['file']))
        preview_cache._atomic_write(target, lambda p: p.write_text(json.dumps(data), encoding='utf-8'))
        return prepared, data


def match_rows(rows, pages):
    regions, pending = [], []
    for row in rows:
        name = norm(str(row.get('Tên hàng trên phiếu (Ảnh)') or '').split('Note:')[0])
        if not name:
            pending.append(row['sourceRow'])
            continue
        ranked = []
        for page, data in enumerate(pages):
            for box in data['candidates']:
                text = box.get('normalized') or norm(box['text'])
                if not .65 <= len(text) / len(name) <= 1.4:
                    continue
                score = SequenceMatcher(None, name, text).ratio()
                if score >= .70 and (len(name) >= 9 or name == text):
                    ranked.append((score, page, box))
        ranked.sort(key=lambda r: r[0], reverse=True)
        if not ranked or ranked[0][0] < .85:
            pending.append(row['sourceRow'])
            continue
        score, page, box = ranked[0]
        competing = [s for s, p, b in ranked[1:]
                     if p != page or min(b['bottom'], box['bottom']) <= max(b['y'], box['y'])]
        if competing and score - max(competing) < .09:
            pending.append(row['sourceRow'])
            continue
        top, bottom = max(0, box['y'] - .004), min(1, box['bottom'] + .004)
        above = [y for y in pages[page].get('separators', []) if y < box['y']]
        below = [y for y in pages[page].get('separators', []) if y > box['bottom']]
        method = 'local-name'
        if above and below and min(below) - max(above) <= .12:
            top, bottom = max(above), min(below)
            method = 'local-name-grid'
        regions.append(dict(sourceRow=row['sourceRow'], page=page, x=.005, y=top,
                            width=.99, height=bottom-top, score=round(score, 3),
                            anchor=box['text'], method=method))
    conflicts = set()
    for i, a in enumerate(regions):
        for b in regions[i+1:]:
            if a['page'] != b['page']:
                continue
            overlap = min(a['y']+a['height'], b['y']+b['height']) - max(a['y'], b['y'])
            if overlap > min(a['height'], b['height']) * .3:
                conflicts.update([a['sourceRow'], b['sourceRow']])
    return [r for r in regions if r['sourceRow'] not in conflicts], sorted(set(pending) | conflicts)


def reviewed_regions(rows,image_keys):
    """Reviewed bands stay bound to exact prepared pixels and row identity."""
    path=Path(__file__).with_name('reviewed_row_locations.json')
    if not path.is_file():return []
    try:records=json.loads(path.read_text(encoding='utf-8'))['regions']
    except (OSError,ValueError,KeyError):return []
    result=[]
    for row in rows:
        matches=[r for r in records if r['imageKey'] in image_keys and r['sourceRow']==row['sourceRow'] and r['name']==row.get('Tên hàng trên phiếu (Ảnh)') and r['code']==str(row.get('Mã vật tư',''))]
        if len(matches)!=1:continue
        r=matches[0]
        if not (0<=r['x']<r['x']+r['width']<=1 and 0<=r['y']<r['y']+r['height']<=1):continue
        result.append(dict(sourceRow=row['sourceRow'],page=image_keys.index(r['imageKey']),x=r['x'],y=r['y'],width=r['width'],height=r['height'],score=1,anchor=r['name'],method='visually-reviewed'))
    return result


def locate(paths, rows, allowed):
    """Return coordinates only on immutable prepared URLs, never on originals."""
    pages = []
    urls = []
    artifacts = []
    for path in paths:
        prepared, anchors = prepare_page(path)
        artifact = preview_cache.ROOT / prepared['file']
        token = 'prepared-' + prepared['cache_key']
        allowed[token] = artifact
        urls.append('/api/image/' + token)
        artifacts.append(prepared['cache_key'])
        pages.append(anchors)
    reviewed=reviewed_regions(rows,artifacts)
    key = hashlib.sha256(json.dumps([VERSION, artifacts, rows, pages, reviewed], sort_keys=True, default=str).encode()).hexdigest()
    target = preview_cache.ROOT / 'row-locations' / ('receipt-' + key + '.json')
    if target.is_file():
        try:
            cached = json.loads(target.read_text(encoding='utf-8'))
            if cached.get('imageKeys') == artifacts:
                return dict(cached, pages=urls)
        except (OSError, ValueError):
            pass
    regions, pending = match_rows(rows, pages)
    verified={r['sourceRow'] for r in reviewed}
    regions=[r for r in regions if r['sourceRow'] not in verified]+reviewed
    pending=[r for r in pending if r not in verified]
    weak = [r['sourceRow'] for r in regions if r['score'] < .85]
    regions = [r for r in regions if r['sourceRow'] not in weak]
    payload = dict(pages=urls, regions=regions, pending=sorted(set(pending + weak)),
                   status='ready' if all(p['status'] == 'ready' for p in pages) else 'unavailable',
                   imageKeys=artifacts)
    preview_cache._atomic_write(target, lambda p: p.write_text(json.dumps(payload), encoding='utf-8'))
    return payload
