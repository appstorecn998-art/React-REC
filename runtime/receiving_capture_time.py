"""Camera EXIF time only; never infer it from filesystem timestamps or OCR."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
from PIL import Image


def captured_at(path, originals=None):
    path = Path(path)
    try:
        manifest = path.parent / 'image-manifest.json'
        if manifest.is_file():
            for record in json.loads(manifest.read_text(encoding='utf-8')).get('files', []):
                if record.get('target') == path.name:
                    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('target_sha256'):
                        return ''
                    if originals is not None and not record.get('captured_at'):
                        original = Path(originals) / record.get('original', '')
                        if original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest() == record.get('source_sha256'):
                            return captured_at(original)
                    value = record.get('captured_at', '')
                    if value:
                        return datetime.fromisoformat(value).isoformat(timespec='seconds')
        with Image.open(path) as image:
            exif = image.getexif()
            # DateTimeOriginal belongs to the Exif sub-IFD on many cameras.
            value = exif.get(36867) or exif.get_ifd(34665).get(36867)
            if isinstance(value, bytes):
                value = value.decode('ascii')
            if not value:
                return ''
            return datetime.strptime(value.strip().strip('\x00'), '%Y:%m:%d %H:%M:%S').isoformat()
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        return ''


def capture_time(path, originals=None):
    value = captured_at(path, originals)
    return datetime.fromisoformat(value).strftime('%H:%M') if value else ''
