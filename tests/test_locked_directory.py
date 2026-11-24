import unittest
from unittest.mock import patch
import server

class LockedDirectoryTests(unittest.TestCase):
    def test_receipts_remain_available_and_directory_recovers_on_cache_hit(self):
        server.cache.clear()
        server._department_cache.clear()
        day=next(iter(server.available_days()))
        with patch.object(server,'load_warehouse_directory',side_effect=PermissionError('locked')):
            first=server.load(day)
        self.assertTrue(first['receipts'])
        self.assertEqual(first['departments'],[])
        self.assertIn('DanhMuc.xlsm',first['directoryWarning'])
        directory={'TEST':('Kho kiểm thử','Bộ phận kiểm thử')}
        with patch.object(server,'load_warehouse_directory',return_value=directory):
            recovered=server.load(day)
        self.assertEqual(recovered['directoryWarning'],'')
        self.assertEqual(recovered['departments'][0]['code'],'TEST')
        self.assertIs(first['receipts'][0]['rows'],recovered['receipts'][0]['rows'])
        server._department_cache.clear()
        with patch.object(server,'load_warehouse_directory',side_effect=PermissionError('locked')):
            locked_again=server.load(day)
        self.assertEqual(locked_again['departments'],[])
        self.assertTrue(locked_again['directoryWarning'])

if __name__=='__main__':unittest.main()
