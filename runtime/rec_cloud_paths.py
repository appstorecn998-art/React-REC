"""Small reader profile storage; does not initialize/migrate the publisher profile."""
import os
import tempfile
from pathlib import Path


def user_root():
    return Path(os.environ.get('REC_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'REC')


def atomic_bytes(path, content):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
