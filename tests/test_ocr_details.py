import io,unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from PIL import Image
from ocr_details import content,install

def image(color):
    stream=io.BytesIO();Image.new('RGB',(200,300),color).save(stream,'JPEG');return stream.getvalue()

class DetailTests(unittest.TestCase):
    def test_overlapping_strips_keep_original_width(self):
        parts=content(image('blue'));images=[p for p in parts if p['type']=='image']
        self.assertEqual(len(images),3)
        import base64
        for p in images:
            crop=Image.open(io.BytesIO(base64.b64decode(p['data'])))
            self.assertEqual(crop.width,200);self.assertLess(crop.height,300)
    def test_parallel_context_does_not_mix_images_or_leak_after_error(self):
        aw=SimpleNamespace(receipt_example_content=lambda:[{'type':'text','text':'examples'}])
        def request(key,model,raw,groups,timeout):
            evidence=aw.receipt_example_content()
            self.assertEqual(evidence[1:],content(raw))
            if key=='fail':raise ValueError('expected')
            return evidence
        aw.request_batch_document=request;install(aw)
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda c:aw.request_batch_document('ok','model',image(c),{},10),['blue','red']))
        self.assertNotEqual(results[0],results[1])
        with self.assertRaises(ValueError):aw.request_batch_document('fail','model',image('red'),{},10)
        self.assertEqual(aw.receipt_example_content(),[{'type':'text','text':'examples'}])

if __name__=='__main__':unittest.main()
