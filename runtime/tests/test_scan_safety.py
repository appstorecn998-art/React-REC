import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import AutoWatcher as aw
class ScanSafetyTests(unittest.TestCase):
 def test_high_confidence_does_not_hide_ambiguity(self):
  catalog={'a':('Thanh long ruot trang','kg'),'b':('Thanh long ruot do','kg')};groups={c:('1410','Trai cay') for c in catalog}
  extracted={'supplier_name':'unknown','items':[{'invoice_name':'Thanh long','group_id':'1410'}]}
  plans=aw.build_plans(extracted,catalog,groups,{'suppliers':[]})
  result={'items':[dict(invoice_name='Thanh long',catalog_code='a',confidence=99,needs_review=False,note='fixture')]}
  row=aw.validate_rows(result,catalog,plans,groups)[0]
  self.assertEqual(row[1],'CHUA CO MA');self.assertIn('nhiều mã',row[6])
 def test_failed_replace_preserves_complete_cache(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'cache.json';aw.atomic_cache_json(p,{'old':1})
   with patch.object(aw.os,'replace',side_effect=OSError('fixture')):
    with self.assertRaises(OSError):aw.atomic_cache_json(p,{'new':2})
   self.assertEqual(json.loads(p.read_text()),{'old':1});self.assertEqual(len(list(Path(d).iterdir())),1)
 def test_corrupt_ocr_cache_is_rebuilt(self):
  from argparse import Namespace
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'image.jpg';p.write_bytes(b'fixture');c=Path(d)/'bad.json';c.write_text('{')
   with patch.object(aw,'wait_ready'),patch.object(aw,'batch_document_cache_path',return_value=c),patch.object(aw,'prepare_image',return_value=b''),patch.object(aw,'request_batch_document',return_value={'document_type':'delivery'}) as request:
    value=aw.extract_batch_document(p,Namespace(timeout=90),'',{})
   self.assertEqual(value['document']['document_type'],'delivery');self.assertEqual(request.call_count,1);self.assertEqual(json.loads(c.read_text()),value['document'])
