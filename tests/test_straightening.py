import hashlib,unittest
import numpy as np
from PIL import Image,ImageDraw
from straightening import straighten,lines
from ocr_quality import prepare
import server

def tilt(image):
    ls,_,(h,w)=lines(image)
    return float(np.median([abs((yy-y)/(xx-x)) for x,y,xx,yy in ls if abs(xx-x)>w*.45 and abs(yy-y)<abs(xx-x)*.15]))

class StraighteningTests(unittest.TestCase):
    def test_fragments_of_one_line_do_not_trigger_deskew(self):
        from unittest.mock import patch
        from straightening import rectify_grid

        image=Image.new('RGB',(500,700),'white')
        segments=np.array([[25,100,475,118],[30,101,480,119],[35,102,485,120]])
        with patch('straightening.lines',return_value=(segments,1,(700,500))):
            result,method=rectify_grid(image)
        self.assertIs(result,image)
        self.assertEqual(method,'original')

    def test_new_image_lazily_gets_preview_and_ocr_uses_saved_orientation(self):
        import tempfile,io
        from pathlib import Path
        from unittest.mock import patch
        import preview_cache
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'new.png';Image.new('RGB',(200,300),'white').save(path)
            before=path.read_bytes()
            with patch.object(preview_cache,'ROOT',Path(directory)/'cache'):
                allowed={};urls=preview_cache.attach([path],allowed)
                self.assertEqual(len(urls),1);self.assertTrue(next(iter(allowed.values())).is_file())
                preview_cache.build(path,90)
                self.assertEqual(preview_cache.build(path)['rotation'],90)
                for enhanced in (True,False):
                    with patch('straightening.straighten',side_effect=lambda im:(im,'original')) as straighten_call:
                        output=Image.open(io.BytesIO(prepare(path,enhanced=enhanced)))
                        self.assertEqual(output.size,(300,200));straighten_call.assert_not_called()
                        prepare(path,enhanced=enhanced,processed=True)
                        straighten_call.assert_not_called()
                self.assertEqual(path.read_bytes(),before)

    def test_bad_preview_does_not_hide_other_receipt_pages(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import preview_cache
        with tempfile.TemporaryDirectory() as directory:
            bad=Path(directory)/'bad.png';bad.write_bytes(b'broken')
            good=Path(directory)/'good.png';Image.new('RGB',(100,100),'white').save(good)
            with patch.object(preview_cache,'ROOT',Path(directory)/'cache'):
                allowed={};urls=preview_cache.attach([bad,good],allowed)
                self.assertEqual(len(urls),2)
                self.assertEqual(allowed[urls[0].split('/')[-1]],bad)
                self.assertNotEqual(allowed[urls[1].split('/')[-1]],good)

    def test_rotation_change_rebuilds_cached_preview(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import preview_cache
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.png';Image.new('RGB',(100,200),'white').save(path)
            with patch.object(preview_cache,'ROOT',Path(directory)/'cache'):
                a=preview_cache.build(path,0);b=preview_cache.build(path,90)
                self.assertNotEqual(a['file'],b['file'])
                with Image.open(preview_cache.ROOT/b['file']) as im:self.assertEqual(im.size,(200,100))
                allowed={};urls=preview_cache.attach([path],allowed)
                self.assertEqual(allowed[urls[0].split('/')[-1]].name,b['file'])

    def test_real_day20_grid_straightened_and_sources_unchanged(self):
        doc=server.load('2026-11-20',True)['receipts'][0]
        path=server.allowed_images[doc['pages'][0].split('/')[-1]]
        before=hashlib.sha256(path.read_bytes()).digest()
        with Image.open(path) as im:image=im.convert('RGB')
        image.thumbnail((2200,2200));corrected,method=straighten(image)
        self.assertEqual(method,'paper-crop+table-perspective')
        self.assertLess(corrected.width,image.width*1.1)
        self.assertLess(tilt(corrected),.005)
        self.assertLess(tilt(corrected),tilt(image)*.3)
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).digest())
        self.assertNotIn('geometry',doc)
        self.assertEqual(len(doc['correctedPages']),len(doc['pages']))
        # OCR preparation keeps color and bounded resolution without any localization call.
        import io
        with Image.open(io.BytesIO(prepare(path))) as output:
            self.assertEqual(output.mode,'RGB');self.assertLessEqual(max(output.size),3200)

    def test_no_grid_leaves_blank_image_unchanged(self):
        image=Image.new('RGB',(500,700),'white');result,method=straighten(image)
        self.assertEqual(method,'original');self.assertIs(result,image)

if __name__=='__main__':unittest.main()
