import json,unittest
from pathlib import Path
import server,AutoWatcher,receiving_app
from local_runtime import ROOT,APP,PROFILE,STORE

class IsolationTests(unittest.TestCase):
    def test_live_modules_and_profile_are_independent(self):
        for module in (AutoWatcher,receiving_app):self.assertTrue(Path(module.__file__).is_relative_to(APP))
        self.assertEqual(server.ocr_jobs.profile,PROFILE)
        self.assertTrue(STORE.is_relative_to(ROOT))
        self.assertNotEqual(STORE,Path('C:/Users/Fenn/Desktop/REC_Software/Data/Phieu giao hang hang thang'))
    def test_all_live_report_and_image_paths_are_inside_copy(self):
        days=server.available_days()
        self.assertEqual(len(days),15)
        for day,report in days.items():
            self.assertTrue(report.is_relative_to(STORE))
            server.load(day)
        self.assertGreater(len(server.allowed_images),0)
        for image in server.allowed_images.values():self.assertTrue(image.is_relative_to(ROOT),str(image))
    def test_archive_links_do_not_escape_independent_data(self):
        for link in STORE.rglob('image-archive.json'):
            data=json.loads(link.read_text(encoding='utf-8'))
            for path in data.get('directories') or [data['directory']]:self.assertTrue((link.parent / path).resolve().is_relative_to(STORE),path)

if __name__=='__main__':unittest.main()
