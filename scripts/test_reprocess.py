import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.test_pilot import MariaIntegration
class ReprocessTests(MariaIntegration):
    def test_new_version_preserves_history_and_original(self):
        payload=self.payload();key=self.app.ingest(payload)['photo']['id'];self.keys.append(key);old=self.wait(key)
        folder=self.app.base/key;original=(folder/'original').read_bytes();old_image=(folder/'annotated.jpg').read_bytes()
        self.app.registry.parent.mkdir(exist_ok=True);self.app.registry.write_text(json.dumps({'models':[{'id':'test-new','classes':['trash'],'enabled':False}]}))
        digest=hashlib.sha256(self.app.registry.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):self.app.reprocess(key,digest)
        self.app.registry.write_text(json.dumps({'models':[{'id':'test-new','classes':['trash'],'enabled':True}]}));digest=hashlib.sha256(self.app.registry.read_bytes()).hexdigest()
        self.app.detector.registry_sha256=digest;self.app.detector.metadata={'registry_sha256':digest,'models':[{'id':'test-new','classes':['trash']}]}
        with self.assertRaises(ValueError):self.app.reprocess(key,'stale')
        self.assertFalse(self.app.reprocess(key,digest)['duplicate']);new=self.wait(key);self.assertEqual(new['state'],'done')
        archive=self.app.root/new['analysis_history'][0]['evidence_directory']
        self.assertEqual((folder/'original').read_bytes(),original);self.assertEqual((archive/'annotated.jpg').read_bytes(),old_image)
        self.assertEqual(json.loads((archive/'photo.json').read_text())['result'],old['result'])
        self.assertTrue(self.app.reprocess(key,digest)['duplicate'])
        self.assertTrue(self.app.ingest(payload)['duplicate']);self.assertEqual(len(new['analysis_history']),1)
