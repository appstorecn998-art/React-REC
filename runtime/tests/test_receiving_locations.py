import tempfile
import unittest
from pathlib import Path
from PIL import Image
from receiving_locations import initial_region, save_verified_region
from receiving_review import choose_region

class LocationTests(unittest.TestCase):
    def test_initial_coordinates_survive_and_reject_changed_image_or_ambiguous_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'a.png';Image.new('RGB',(1000,2000),'white').save(p)
            values={'Tên hàng trên phiếu (Ảnh)':'Cam sành','STT trên phiếu':'2'}
            self.assertIsNone(initial_region(p,root/'.receiving',values))
            match={'box':(0,600,1000,660),'anchor':(100,600,900,660),'text':'Cam sành'}
            save_verified_region(p,root/'.receiving',values,match,(1000,2000))
            self.assertEqual(initial_region(p,root/'.receiving',values)['box'],[0,600,1000,660])
            self.assertIsNone(initial_region(p,root/'.receiving',dict(values,**{'STT trên phiếu':'3'})))
            Image.new('RGB',(1000,2000),'gray').save(p)
            self.assertIsNone(initial_region(p,root/'.receiving',values))
            save_verified_region(p,root/'.receiving',values,dict(match,box=[0,-1,1000,600]),(1000,2000))
            self.assertIsNone(initial_region(p,root/'.receiving',values))

    def test_local_fragments_combined_on_same_line_but_not_across_rows(self):
        words=[{'text':'Stationery Plastic','confidence':.9,'box':[100,300,260,320]},
               {'text':'Binder Sleeves','confidence':.9,'box':[265,300,400,320]}]
        self.assertIsNotNone(choose_region(words,'Stationery Plastic Binder Sleeves',(1000,1000)))
        words[1]['box']=[265,400,400,420]
        self.assertIsNone(choose_region(words,'Stationery Plastic Binder Sleeves',(1000,1000)))

if __name__=='__main__':unittest.main()
