import unittest
import numpy as np
from PIL import Image,ImageDraw
from paper_crop import crop_paper

class PaperCropTests(unittest.TestCase):
    def test_shadow_cannot_make_the_receipt_footer_disappear(self):
        im=Image.new('RGB',(1000,1000),(50,30,20));d=ImageDraw.Draw(im);d.rectangle((80,20,920,980),fill='white');d.rectangle((80,730,920,770),fill=(50,30,20));d.text((150,900),'TOTAL 12345',fill='black')
        out,cropped=crop_paper(im);self.assertFalse(cropped);self.assertIs(out,im)
    def test_contrasting_background_removed_and_internal_markers_retained(self):
        image=Image.new('RGB',(800,1100),(65,35,20));d=ImageDraw.Draw(image)
        d.rectangle((80,70,720,1030),fill=(225,225,215));d.rectangle((100,90,120,110),fill=(0,0,220));d.rectangle((680,980,700,1000),fill=(220,0,0))
        out,cropped=crop_paper(image);self.assertTrue(cropped)
        a=np.array(out);self.assertGreater(((a[:,:,2]>150)&(a[:,:,0]<80)).sum(),100);self.assertGreater(((a[:,:,0]>150)&(a[:,:,2]<80)).sum(),100)
        self.assertLess(((a[:,:,0]<100)&(a[:,:,1]<80)&(a[:,:,2]<60)).mean(),.01)
    def test_already_white_page_is_not_cut_to_internal_table(self):
        im=Image.new('RGB',(800,1100),'white');d=ImageDraw.Draw(im);d.rectangle((70,300,730,1000),outline='black',width=3)
        out,cropped=crop_paper(im);self.assertFalse(cropped);self.assertIs(out,im)

if __name__=='__main__':unittest.main()
