import ctypes
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "06_Bat_dau_phien_moi.bat"


class ResetBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Auto reset ")
        self.root = Path(self.temporary.name)
        shutil.copy2(SOURCE, self.root / SOURCE.name)
        (self.root / "AutoWatcher.py").write_text("# placeholder", encoding="utf-8")
        (self.root / "01_Doc_mot_don.bat").write_bytes(b'@echo off\r\necho started>"%~dp0started.txt"\r\nexit /b 0\r\n')
        self.report = "TongHop_" + datetime.now().strftime("%Y-%m-%d") + ".xlsx"
        self.names = [".autowatcher-cache/result.json", ".autowatcher-processed-images.json",
                      ".autowatcher-pending-pair.json", self.report,
                      ".autowatcher-report-backups/" + self.report]
        self.preserved = ["DanhMuc.xlsm", "NhaCungCap.json", "gemini_api_key.txt",
                          "PhieuGiao_Input/new.jpg", "TongHop_2000-01-01.xlsx"]
        for name in self.names + self.preserved:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("fixture:" + name).encode("utf-8"))

    def tearDown(self):
        self.temporary.cleanup()

    def run_batch(self, *args):
        return subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "call",
                               str(self.root / SOURCE.name), *args],
                              input=b"\r\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              cwd=self.root.parent, timeout=40,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def test_dry_run_does_not_move_files_or_start_watcher(self):
        result = self.run_batch("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", errors="replace"))
        for name in self.names:
            self.assertTrue((self.root / name).is_file())
        self.assertFalse((self.root / "LuuTru").exists())
        self.assertFalse((self.root / "started.txt").exists())

    def test_reset_archives_exact_targets_and_starts_local_runner(self):
        result = self.run_batch()
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", errors="replace"))
        archives = list((self.root / "LuuTru").iterdir())
        self.assertEqual(len(archives), 1)
        for name in self.names:
            self.assertFalse((self.root / name).exists())
            self.assertEqual((archives[0] / name).read_bytes(), ("fixture:" + name).encode("utf-8"))
        for name in self.preserved:
            self.assertEqual((self.root / name).read_bytes(), ("fixture:" + name).encode("utf-8"))
        self.assertTrue((self.root / "started.txt").exists())
        result = self.run_batch()
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", errors="replace"))
        self.assertEqual(len(list((self.root / "LuuTru").iterdir())), 1)

    def test_locked_report_stops_before_any_file_is_moved(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                           ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        handle = create(str(self.root / self.report), 0x80000000, 0, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            result = self.run_batch()
        finally:
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(handle)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Đóng TongHop", result.stdout.decode("utf-8", errors="replace"))
        for name in self.names:
            self.assertTrue((self.root / name).exists())
        self.assertFalse((self.root / "started.txt").exists())
        self.assertFalse((self.root / "LuuTru").exists())

    def test_running_watcher_stops_reset_without_changing_files(self):
        (self.root / "AutoWatcher.py").write_text("import time; time.sleep(30)", encoding="utf-8")
        watcher = subprocess.Popen([sys.executable, str(self.root / "AutoWatcher.py")],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            result = self.run_batch()
        finally:
            watcher.terminate()
            watcher.wait(timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AutoWatcher còn đang chạy", result.stdout.decode("utf-8", errors="replace"))
        for name in self.names:
            self.assertTrue((self.root / name).exists())
        self.assertFalse((self.root / "started.txt").exists())
        self.assertFalse((self.root / "LuuTru").exists())
