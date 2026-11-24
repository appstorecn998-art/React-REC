import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import rec_runtime as rt
from receiving_inbox import Inbox


class RuntimeTests(unittest.TestCase):
    def test_source_and_frozen_worker_arguments_preserve_spaces(self):
        executable,args=rt.process_command('worker',['2026-11-07','C:/Data With Spaces','--auto'],'C:/User Data')
        self.assertIn('C:/Data With Spaces',args)
        self.assertTrue(any('rec_launcher.py' in p for p in args))
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable','C:/REC App/REC.exe'):
            executable,args=rt.process_command('locate',['C:/Ảnh/a.jpg','C:/cache'],'C:/User Data')
        self.assertEqual(executable,'C:/REC App/REC.exe');self.assertEqual(args[0],'--rec-locate')
        self.assertNotIn('python.exe',' '.join(args))

    def test_explicit_profile_seeds_resources_but_never_legacy_credentials(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);resources=base/'bundle';resources.mkdir();legacy=base/'legacy';legacy.mkdir()
            for name in ['DanhMuc.xlsm','NhaCungCap.json']:(resources/name).write_bytes(b'fixture')
            (legacy/'gemini_api_key.txt').write_text('do-not-copy')
            with patch.dict(os.environ,{'REC_DATA_DIR':str(base/'profile')}),patch.object(rt,'resource_root',return_value=resources):
                root=rt.initialize(legacy)
                self.assertTrue((root/'DanhMuc.xlsm').exists());self.assertFalse((root/'gemini_api_key.txt').exists())
                (root/'NhaCungCap.json').write_text('user-change')
                rt.initialize(legacy);self.assertEqual((root/'NhaCungCap.json').read_text(),'user-change')

    def test_local_configuration_checks_do_not_leak_key_or_use_network(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'gemini_api_key.txt').write_text('fake-secret-never-print')
            with patch('requests.sessions.Session.request',side_effect=AssertionError('Network forbidden')):
                report=rt.config_check(root)
            self.assertEqual(report['network_requests'],0)
            self.assertTrue(report['checks']['gemini']['ok'])
            self.assertNotIn('fake-secret-never-print',json.dumps(report))


class RecoveryTests(unittest.TestCase):
    def state(self,p,done):p.write_text(json.dumps({'version':1,'done':done}),encoding='utf-8')
    def test_corrupt_primary_recovers_without_losing_duplicate_history(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'state.json';p.write_text('{');self.state(p.with_suffix('.backup.json'),['a'*64])
            inbox=Inbox(p);self.assertEqual(inbox.done,{'a'*64});self.assertFalse(inbox.blocked)
            self.assertTrue(list(p.parent.glob('*.corrupt-*')))
            self.assertEqual(Inbox.read_state(p),{'a'*64})
    def test_invalid_schema_no_backup_stops_scanning(self):
        for data in [[],{}, {'version':1,'done':['not-a-digest']}, {'version':2,'done':[]}]:
            with tempfile.TemporaryDirectory() as t:
                p=Path(t)/'state.json';p.write_text(json.dumps(data));inbox=Inbox(p)
                self.assertTrue(inbox.blocked)
                with self.assertRaises(ValueError):inbox.scan(Path(t))
                self.assertEqual(json.loads(p.read_text()),data)
    def test_newer_backup_is_retained_after_interrupted_primary_write(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'state.json';self.state(p,['a'*64]);self.state(p.with_suffix('.backup.json'),['a'*64,'b'*64])
            self.assertEqual(Inbox(p).done,{'a'*64,'b'*64})
    def test_explicit_restore_keeps_quarantined_file_and_requires_valid_schema(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'state.json';p.write_text('{');inbox=Inbox(p);backup=Path(t)/'good.json'
            self.state(backup,['c'*64]);inbox.restore_from(backup)
            self.assertFalse(inbox.blocked);self.assertEqual(inbox.done,{'c'*64})
            self.assertTrue(list(p.parent.glob('*.before-restore-*')))
