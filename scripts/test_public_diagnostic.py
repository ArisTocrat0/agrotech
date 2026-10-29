"""In-memory QA must preserve saved results and refuse private/busy input."""
import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.pilot.service import Pilot
from PIL import Image
class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name);self.p=Pilot.__new__(Pilot);self.p.base=root;self.p.registry=root/'registry.json';self.p.registry.write_text('{"models":[]}');key='a'*32;(root/key).mkdir();Image.new('RGB',(20,20)).save(root/key/'original',format='JPEG');(root/key/'result.json').write_text('{"historical":true}')
  self.row={'id':key,'state':'done','sha256':hashlib.sha256((root/key/'original').read_bytes()).hexdigest(),'analysis_mode':'environment'};self.p.ingest_lock=threading.Lock();self.p.store=SimpleNamespace(list=lambda:[self.row],get=lambda k:self.row);self.p.photos=lambda:[{**self.row,'presentation':{'kind':'public_demo'}}]
  digest=hashlib.sha256(self.p.registry.read_bytes()).hexdigest();self.p.detector=SimpleNamespace(registry_sha256=digest,metadata={'registry_sha256':digest,'backend':'TEST ONLY'},detect=Mock(return_value=[]));self.key=key
 def test_real_path_preserves_original_and_history(self):
  before={str(p):p.read_bytes() for p in self.p.base.rglob('*') if p.is_file()};r=self.p.diagnose_public_photo(self.key);self.assertFalse(r['persisted']);self.p.detector.detect.assert_called_once();self.assertEqual(before,{str(p):p.read_bytes() for p in self.p.base.rglob('*') if p.is_file()})
 def test_private_photo_refused_before_inference(self):
  self.p.photos=lambda:[{**self.row,'presentation':{'kind':'operator_upload'}}]
  with self.assertRaises(ValueError):self.p.diagnose_public_photo(self.key)
  self.p.detector.detect.assert_not_called()
 def test_busy_queue_refused(self):
  self.row['state']='queued'
  with self.assertRaises(ValueError):self.p.diagnose_public_photo(self.key)
  self.p.detector.detect.assert_not_called()
if __name__=='__main__':unittest.main()
