"""Stable-file inbox with durable content identity; no API calls here."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from receiving_service import IMAGE_EXTENSIONS, atomic_json, import_images

class Inbox:
    def __init__(self, state_path):
        self.path=Path(state_path)
        self.observed={}
        self.batch=[]
        self.done=set();self.warning='';self.blocked=False
        backup=self.path.with_suffix('.backup.json')
        if self.path.exists():
            try:
                self.done=self.read_state(self.path)
                if backup.exists():
                    try:self.done |= self.read_state(backup)
                    except (OSError,ValueError,KeyError,TypeError):
                        self.warning='Bản dự phòng lịch sử bị hỏng; lịch sử chính vẫn hợp lệ. Bản dự phòng sẽ được tạo lại sau lượt thành công.'
            except (OSError,ValueError,KeyError,TypeError):
                try:
                    self.done=self.read_state(backup)
                    quarantine=self.path.with_name(self.path.name+'.corrupt-'+datetime.now().strftime('%Y%m%d%H%M%S%f'))
                    quarantine.write_bytes(self.path.read_bytes())
                    atomic_json(self.path,{'version':1,'done':sorted(self.done)})
                    self.warning='Lịch sử nhận ảnh bị hỏng; đã phục hồi từ bản dự phòng. Bản lỗi được giữ để kiểm tra.'
                except (OSError,ValueError,KeyError,TypeError):
                    self.blocked=True
                    self.warning='Lịch sử nhận ảnh bị hỏng, tự đọc đã dừng để tránh đọc trùng. Khôi phục lịch sử trong Cài đặt.'
        elif backup.exists():
            try:
                self.done=self.read_state(backup)
                atomic_json(self.path,{'version':1,'done':sorted(self.done)})
                self.warning='Đã khôi phục lịch sử nhận ảnh từ bản dự phòng.'
            except (OSError,ValueError,KeyError,TypeError):
                self.blocked=True;self.warning='Bản dự phòng lịch sử không hợp lệ. Khôi phục trong Cài đặt trước khi tự đọc.'

    @staticmethod
    def read_state(path):
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('done'),list):raise ValueError('Invalid inbox schema')
        if any(not isinstance(v,str) or not re.fullmatch('[a-f0-9]{64}',v) for v in data['done']):raise ValueError('Invalid inbox digest')
        return set(data['done'])

    def restore_from(self,path):
        done=self.read_state(path) | self.done
        if self.path.exists():
            quarantine=self.path.with_name(self.path.name+'.before-restore-'+datetime.now().strftime('%Y%m%d%H%M%S%f'))
            quarantine.write_bytes(self.path.read_bytes())
        payload={'version':1,'done':sorted(done)}
        atomic_json(self.path.with_suffix('.backup.json'),payload)
        atomic_json(self.path,payload)
        self.done=done;self.blocked=False;self.warning='Đã khôi phục lịch sử. Bật tự đọc khi sẵn sàng.'

    def scan(self, source):
        if self.blocked:raise ValueError(self.warning)
        source=Path(source)
        if not source.is_dir():raise ValueError('Không tìm thấy thư mục nhận ảnh. Kiểm tra lại đường dẫn.')
        files=sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
        result=[];keys=set();all_stable=True
        for path in files:
            stat=path.stat();stamp=(stat.st_size,stat.st_mtime_ns)
            previous=self.observed.get(str(path));self.observed[str(path)]=stamp
            if previous!=stamp or not stat.st_size:
                all_stable=False;continue
            content=path.read_bytes()
            after=path.stat()
            if (after.st_size,after.st_mtime_ns)!=stamp:
                all_stable=False;continue
            key=hashlib.sha256(content).hexdigest()
            if key not in self.done and key not in keys:result.append((path,key));keys.add(key)
        # Wait for the whole incoming group to settle before grouping pages.
        return result if all_stable else []

    def prepare(self, source, root, day, destination, progress=None):
        batch=self.scan(source)
        if not batch:return []
        self.batch=batch
        added=import_images(root,day,[p for p,_ in batch],destination,progress=progress)
        return batch # Existing copies may still need reading after a prior failure.

    def finish(self,day=None,report=None):
        done=self.done | {key for _,key in self.batch}
        payload={'version':1,'done':sorted(done)}
        atomic_json(self.path.with_suffix('.backup.json'),payload)
        atomic_json(self.path,payload)
        if day is not None:atomic_json(self.path.with_name('inbox-last-result.json'),dict(day=day,report=report,images=[str(p) for p,_ in self.batch],finished_at=datetime.now().astimezone().isoformat()))
        self.done=done
        self.batch=[]
