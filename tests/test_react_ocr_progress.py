import json,tempfile,time,unittest
from pathlib import Path
from ocr_jobs import Jobs

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.jobs=Jobs(root/'data',root/'jobs',profile=root/'profile')
        self.jobs.current={'id':'test','startedAt':time.time()-3,'status':'running','logs':[],'events':[],'count':2}
    def test_worker_events_reach_counts_and_milestones(self):
        for stage,details in [('image_start',{'file':'first.jpg'}),('image_done',{'file':'first.jpg','rows':7}),('image_error',{'file':'second.jpg','exception':'TimeoutError'})]:
            self.jobs._log('REC_OCR_EVENT '+json.dumps({'stage':stage,'details':details}))
        self.jobs._log('12:00:00 Đang đối chiếu một phiếu gồm 1 ảnh')
        self.jobs._log('12:00:01 ĐÃ LƯU first.jpg: 7 dòng')
        job=self.jobs.public()['job']
        self.assertEqual(job['imagesRead'],1);self.assertEqual(job['imagesFailed'],1);self.assertEqual(job['savedCount'],1)
        self.assertEqual([e['stage'] for e in job['events']],['read','image_done','warning','match','saved'])
        saved=json.loads((self.jobs.root/'test/status.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['imagesRead'],1)
    def test_estimate_uses_complete_batches_and_freezes_terminal_clock(self):
        p=self.jobs.root/'old';p.mkdir(parents=True)
        (p/'status.json').write_text(json.dumps({'status':'complete','enhanced':True,'count':2,'startedAt':100,'finishedAt':120}))
        self.assertEqual(self.jobs._estimate(5,True),(50,1))
        self.jobs.current.update(finishedAt=self.jobs.current['startedAt']+2,status='complete')
        self.assertEqual(self.jobs.public()['job']['elapsed'],2)
    def test_no_unstructured_log_can_fake_worker_completion(self):
        self.jobs._log('REC_OCR_EVENT broken-json')
        self.jobs._log('Worker hoàn tất')
        self.assertEqual(self.jobs.current['status'],'running')

if __name__=='__main__':unittest.main()
