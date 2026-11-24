import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
import AutoWatcher as aw
from delivery_export import vietnamese_item_name

class ExportNamesTests(unittest.TestCase):
    def test_vietnamese_without_accents_preserves_specification(self):
        for source,expected in [('Hải sản','Hai san'),('DRIED SHRIMP/TÔM KHÔ','DRIED SHRIMP/TOM KHO'),('SF Clam 30-35 Pcs/KG/Ngheu 30-35 Pcs/KG','SF Clam 30-35 Pcs/KG/Ngheu 30-35 Pcs/KG'),('SF Squid/Muc Lam Sach 4-5 Con /kg','SF Squid/Muc Lam Sach 4-5 Con /kg'),('Saigon Special 330ml - 24 cans/lon','Saigon Special 330ml - 24 cans/lon'),('Perrier 330ml - 24 bottles/chai','Perrier 330ml - 24 bottles/chai'),('Tôm 20 con/kg','Tom 20 con/kg'),('Shellfish Prawn King Fresh/kg 15-20pcs/Tom Su Bien Tuoi','Shellfish Prawn King Fresh/kg 15-20pcs/Tom Su Bien Tuoi'),('Đậu đỏ','Dau do'),('Hải sản/đông lạnh','Hai san/dong lanh')]:
            self.assertEqual(vietnamese_item_name(source),expected)

    def test_readable_sheet_names_collision_and_same_identity_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx'
            row=['a']*len(aw.HEADERS)
            aw.write_result(p,Path('identity1'),[row],sheet_title='IMG_4051.JPG')
            aw.write_result(p,Path('identity2'),[row],sheet_title='IMG_4051.PNG')
            aw.write_result(p,Path('identity1'),[row],sheet_title='IMG_4051.JPG')
            w=load_workbook(p)
            self.assertEqual(set(w.sheetnames),{'IMG_4051','IMG_4051 (2)'})
            w.close()
