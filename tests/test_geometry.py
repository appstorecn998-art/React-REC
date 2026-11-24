import json,unittest
from pathlib import Path
from page_geometry import match_rows,signature,attach,ROOT
import server

class GeometryTests(unittest.TestCase):
    def test_overlapping_product_anchors_are_not_published(self):
        rows=[{'sourceRow':2,'Tên hàng trên phiếu (Ảnh)':'Cu rieng trang'},{'sourceRow':3,'Tên hàng trên phiếu (Ảnh)':'Cu cai trang'}]
        cs=[dict(text='Cu rieng trang',x=.1,y=.2,right=.6,bottom=.25),dict(text='Cu cai trang',x=.1,y=.23,right=.6,bottom=.26)]
        regions,pending=match_rows(rows,[{'candidates':cs}])
        self.assertEqual(regions,[]);self.assertEqual(pending,[2,3])

    def test_reviewed_day20_has_exact_source_rows_and_valid_page_bounds(self):
        data=server.load('2026-11-20',True)
        self.assertEqual(len(data['receipts']),10)
        count=0
        for d in data['receipts']:
            paths=[server.allowed_images[p.split('/')[-1]] for p in d['pages']]
            g=attach(paths,d['rows'],{});self.assertIsNotNone(g)
            self.assertEqual(sorted(r['sourceRow'] for r in g['regions']),sorted(r['sourceRow'] for r in d['rows']))
            for r in g['regions']:
                self.assertTrue(0<=r['page']<len(d['pages']))
                self.assertTrue(0<=r['x']<r['x']+r['width']<=1)
                self.assertTrue(0<=r['y']<r['y']+r['height']<=1)
            count+=len(g['regions'])
            paths=[server.allowed_images[p.split('/')[-1]] for p in d['pages']]
            changed=[dict(r) for r in d['rows']];changed[0]['Tên hàng trên phiếu (Ảnh)']='CHANGED'
            self.assertIsNone(attach(paths,changed,{}))
        self.assertEqual(count,70)

if __name__=='__main__':unittest.main()
