import unittest
from receiving_service import invoice_images,sheet_signature

class NavigationTests(unittest.TestCase):
    def test_multipage_uses_each_source_without_guessing_other_invoice(self):
        rows=[(2,{'Ảnh nguồn':'IMG_1.JPG'}),(3,{'Ảnh nguồn':'IMG_2.JPG'})]
        self.assertEqual(invoice_images('merged',rows),{'img_1.jpg','img_2.jpg'})
        self.assertNotIn('img_3.jpg',invoice_images('merged',rows))
    def test_legacy_exact_stem_only(self):
        refs=invoice_images('IMG_4204',[(2,{'Tên':'fruit'})])
        self.assertIn('img_4204.jpg',refs);self.assertNotIn('img_4205.jpg',refs)
    def test_per_sheet_review_changes_only_edited_invoice(self):
        first=[(2,{'Thực nhận':0,'Đơn giá':15})];other=[(2,{'Thực nhận':2})]
        sig1=sheet_signature('one',first);sig2=sheet_signature('two',other)
        first[0][1]['Thực nhận']=1
        self.assertNotEqual(sig1,sheet_signature('one',first))
        self.assertEqual(sig2,sheet_signature('two',other))
        self.assertNotEqual(sig2,sheet_signature('renamed',other))
    def test_same_sheet_hash_independent_of_dictionary_order(self):
        self.assertEqual(sheet_signature('x',[(2,{'a':0,'b':None})]),sheet_signature('x',[(2,{'b':None,'a':0})]))

if __name__=='__main__':unittest.main()
