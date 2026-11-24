import tempfile,unittest
from pathlib import Path
from openpyxl import Workbook,load_workbook
import server
from receipt_metadata import save
from receiving_service import digest

class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'report.xlsx'
        b=Workbook();s=b.active;s.title='Receipt';s.append(['Tên hàng trên phiếu (Ảnh)','Thời gian chụp','Thực nhận','Đơn giá','Mã kho','Tên kho','Bộ phận'])
        s.append(['A','08:15',2,120,'1103','Bếp','KC']);s.append(['B','08:15',0,90,'1103','Bếp','KC'])
        b.create_sheet('Other').append(['Keep']);b.save(self.path);b.close()
        self.directory={'1800':('Steward','ST'),'1103':('Bếp','KC')}
    def tearDown(self):self.tmp.cleanup()
    def test_time_and_warehouse_atomic_preserve_photo_time_quantity_other_sheets(self):
        before=digest(self.path);save(self.path,before,'Receipt',{'receiptTime':'14:35','warehouseCode':'1800'},self.directory)
        b=load_workbook(self.path);s=b['Receipt'];self.assertEqual(s.cell(2,8).value,'14:35');self.assertEqual(s.cell(3,8).value,'14:35')
        self.assertEqual([s.cell(2,c).value for c in range(2,8)],['08:15',2,120,'1800','Steward','ST'])
        self.assertEqual(s.cell(3,3).value,0);self.assertEqual(b['Other']['A1'].value,'Keep');b.close()
        self.assertTrue(list(self.path.parent.glob('.autowatcher-backups/*/report.xlsx')))
        with self.assertRaises(ValueError):save(self.path,before,'Receipt',{'receiptTime':'15:00'},self.directory)
    def test_invalid_fields_no_partial_save_and_explicit_clear(self):
        before=self.path.read_bytes()
        for changes in [{'receiptTime':'25:00','warehouseCode':'1800'},{'receiptTime':'12:00','warehouseCode':'BAD'},{'supplier':'X'}]:
            with self.assertRaises(ValueError):save(self.path,digest(self.path),'Receipt',changes,self.directory)
            self.assertEqual(self.path.read_bytes(),before)
        save(self.path,digest(self.path),'Receipt',{'receiptTime':'','warehouseCode':''},self.directory)
        b=load_workbook(self.path);s=b['Receipt'];self.assertTrue(all(s.cell(2,c).value in ('',None) for c in (5,6,7,8)));b.close()

    def test_legacy_receipt_time_and_explicit_override(self):
        rows=[(2,{'Thời gian chụp':'08:06'}),(3,{'Thời gian chụp':'08:05'})]
        self.assertEqual(server.receipt_time(rows),'08:05')
        for _,value in rows:value['Giờ nhận']='09:30'
        self.assertEqual(server.receipt_time(rows),'09:30')
        for _,value in rows:value['Giờ nhận']=None
        self.assertEqual(server.receipt_time(rows),'')

    def test_supplier_name_edit_preserves_other_fields(self):
        before=digest(self.path)
        save(self.path,before,'Receipt',{'supplierName':'NCC đã sửa'},self.directory)
        b=load_workbook(self.path);s=b['Receipt']
        self.assertEqual(s.cell(2,4).value,120)
        supplier_col=next(c.column for c in s[1] if c.value=='Nhà cung cấp')
        self.assertEqual(s.cell(2,supplier_col).value,'NCC đã sửa')
        self.assertEqual(s.cell(3,supplier_col).value,'NCC đã sửa');b.close()

    def test_bulk_time_selected_sheets_and_one_backup(self):
        b=load_workbook(self.path);b.copy_worksheet(b['Receipt']).title='Second';b.save(self.path);b.close()
        before=digest(self.path)
        save(self.path,before,['Receipt','Second'],{'receiptTime':'23:59'},self.directory)
        b=load_workbook(self.path)
        for name in ('Receipt','Second'):
            self.assertEqual(b[name].cell(2,8).value,'23:59')
            self.assertEqual(b[name].cell(3,8).value,'23:59')
            self.assertEqual(b[name].cell(2,2).value,'08:15')
            self.assertEqual(b[name].cell(2,5).value,'1103')
        self.assertEqual(b['Other']['A1'].value,'Keep');b.close()
        self.assertEqual(len(list(self.path.parent.glob('.autowatcher-backups/*/report.xlsx'))),1)
        with self.assertRaises(ValueError):save(self.path,before,['Receipt'],{'receiptTime':'12:00'},self.directory)

    def test_bulk_rejects_invalid_selection_without_partial_write(self):
        before=self.path.read_bytes()
        for names,changes in [([],{'receiptTime':'12:00'}),(['Receipt','Receipt'],{'receiptTime':'12:00'}),(['Receipt','Missing'],{'receiptTime':'12:00'}),(['Receipt','Other'],{'receiptTime':'12:00'}),(['Receipt'],{'receiptTime':'25:00'}),(['Receipt'],{'warehouseCode':'1800'}),([None],{'receiptTime':'12:00'})]:
            with self.subTest(names=names,changes=changes):
                with self.assertRaises(ValueError):save(self.path,digest(self.path),names,changes,self.directory)
                self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(list(self.path.parent.glob('.autowatcher-backups/*/report.xlsx')))

if __name__=='__main__':unittest.main()

