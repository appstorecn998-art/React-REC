import unittest,hashlib
import server

class ReadOnlyBridgeTest(unittest.TestCase):
    def test_all_live_days_and_cached_snapshots(self):
        days=server.available_days()
        self.assertTrue(days)
        for day,report in days.items():
            before=hashlib.sha256(report.read_bytes()).hexdigest()
            data=server.load(day)
            expected=[(n,rs) for n,rs in server.snapshot(report)[1] if rs]
            self.assertEqual([d['file'] for d in data['receipts']],[n for n,_ in expected])
            self.assertEqual([len(d['rows']) for d in data['receipts']],[len(rs) for _,rs in expected])
            cached=server.load(day)['receipts']
            self.assertEqual(data['receipts'],cached)
            for original,again in zip(data['receipts'],cached):
                self.assertIs(original['rows'],again['rows'])
            for d in data['receipts']:
                self.assertTrue(d['id'].startswith(day+'::'))
                for page in d['pages']:self.assertTrue(server.allowed_images[page.rsplit('/',1)[-1]].is_file())
            self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(),before)
    def test_invalid_day_is_rejected(self):
        with self.assertRaises(ValueError):server.load('../../bad')
    def test_same_sheet_different_days_has_distinct_identity(self):
        ids=[]
        for day in server.available_days():ids.extend(d['id'] for d in server.load(day)['receipts'])
        self.assertEqual(len(ids),len(set(ids)))

if __name__=='__main__':unittest.main()
