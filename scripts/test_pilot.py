"""MariaDB-backed integration tests. Artificial detector exists only in tests."""
import base64,json,tempfile,time,unittest,uuid,sys
from io import BytesIO
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.pilot.service import Pilot,validate_photo
from PIL import Image

class FakeDetectorForTestsOnly:
    metadata={'backend':'TEST ONLY, not a real model'}
    def detect(self,image):return [{'class_name':'trash','confidence':.8,'bbox':[1,1,20,20],'model_id':'test-only'}]

class InputTests(unittest.TestCase):
    def payload(self):
        b=BytesIO();Image.new('RGB',(32,32),'white').save(b,format='JPEG')
        return {'mission':'unit-'+uuid.uuid4().hex,'name':'real-bytes.jpg','photo':base64.b64encode(b.getvalue()).decode()}
    def test_unknown_gps_stays_null(self):
        _,r=validate_photo(self.payload());self.assertIsNone(r['location']);self.assertIsNone(r['captured_at'])
    def test_bad_inputs_rejected(self):
        for extra in [{'mission':'../x'},{'captured_at':'2026-10-21T12:30:00'},
                      {'location':{'latitude':float('nan'),'longitude':1,'source':'operator_capture_position'}},
                      {'location':{'latitude':91,'longitude':1,'source':'operator_capture_position'}},
                      {'name':'clip.mp4'},{'photo':'not valid base64'},{'metadata':[]}]:
            with self.subTest(extra=extra),self.assertRaises(ValueError):validate_photo({**self.payload(),**extra})

class MariaIntegration(InputTests):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ecokineu-test-');self.root=Path(self.tmp.name)
        d=self.root/'outputs/pilot-db';d.mkdir(parents=True)
        settings=json.loads((ROOT/'outputs/pilot-db/client.json').read_text());settings['_table']='photos_tests'
        (d/'client.json').write_text(json.dumps(settings))
        self.app=Pilot(self.root,detector_factory=FakeDetectorForTestsOnly)
        self.keys=[]
    def tearDown(self):
        self.app.close()
        import pymysql
        with pymysql.connect(**json.loads((ROOT/'outputs/pilot-db/client.json').read_text()),autocommit=True) as db:
            with db.cursor() as c:
                for key in self.keys:c.execute('DELETE FROM photos_tests WHERE id=%s',(key,))
        self.tmp.cleanup()
    def wait(self,key):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            row=self.app.store.get(key)
            if row['state'] in ('done','error'):return row
            time.sleep(.05)
        self.fail('worker deadline')
    def test_queue_duplicate_evidence_review_restart(self):
        p=self.payload();r=self.app.ingest(p);key=r['photo']['id'];self.keys.append(key)
        duplicate=self.app.ingest(p);self.assertTrue(duplicate['duplicate']);self.assertEqual(key,duplicate['photo']['id'])
        with self.assertRaises(ValueError):self.app.ingest({**p,'captured_at':'2026-10-21T12:30:00+05:00'})
        row=self.wait(key);self.assertEqual('done',row['state'],row.get('error'));self.assertIsNone(row['result']['events'][0]['object_location'])
        self.assertTrue((self.app.base/key/'original').exists());self.assertTrue((self.app.base/key/'annotated.jpg').exists())
        e=row['result']['events'][0];self.app.review(key,e['id'],'confirmed');self.assertIsNone(self.app.geojson()['features'][-1]['geometry'])
        self.app.close();self.app=Pilot(self.root,detector_factory=FakeDetectorForTestsOnly)
        saved=self.app.store.get(key);self.assertEqual('confirmed',saved['result']['events'][0]['review_status'])
    def test_capture_position_not_object(self):
        p={**self.payload(),'location':{'latitude':53.2,'longitude':63.6,'source':'operator_capture_position'}}
        # Coordinates here are synthetic TEST data; never written into a demo or production job.
        row=self.app.ingest(p)['photo'];self.keys.append(row['id']);row=self.wait(row['id'])
        self.assertEqual(row['result']['events'][0]['location']['precision'],'capture_position_not_object')
        feature=next(f for f in self.app.geojson()['features'] if f['properties']['photo_id']==row['id'])
        self.assertEqual(feature['geometry']['coordinates'],[63.6,53.2]);self.assertIsNone(feature['properties']['object_location'])
    def test_public_origin_is_detected_by_hash_without_demo_flag(self):
        payload=self.payload();_,fields=validate_photo(payload)
        folder=self.root/'datasets/uavvaste-pilot-v1';folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps({'record':'https://zenodo.org/records/8214061','license':'TEST ONLY','records':[{'sha256':fields['sha256'],'file':'TEST.jpg'}]}))
        row=self.app.ingest(payload)['photo'];self.keys.append(row['id']);self.wait(row['id'])
        shown=next(r for r in self.app.photos() if r['id']==row['id'])
        self.assertEqual(shown['presentation']['kind'],'public_demo')
        self.assertIn('Казахстане',shown['presentation']['notice'])
        self.assertNotIn('presentation',self.app.store.get(row['id']))

    def test_training_statuses_stay_separate(self):
        self.app.registry.parent.mkdir(parents=True,exist_ok=True)
        for pointer,run in [('quality-active-run.json','TEST-TRASH'),('smoke-active-run.json','TEST-SMOKE')]:
            (self.root/'artifacts'/pointer).write_text(json.dumps({'run':run}))
            base=self.root/'outputs/pilot-training'/run;base.mkdir(parents=True)
            (base/'quality-report.json').write_text(json.dumps({'state':'TEST-ONLY','class':run}))
        status=self.app.status()
        self.assertEqual(status['quality_training']['quality-report.json']['class'],'TEST-TRASH')
        self.assertEqual(status['smoke_training']['quality-report.json']['class'],'TEST-SMOKE')
        self.assertFalse(status['smoke_training']['live_process']['training_alive'])

    def test_status_distinguishes_loaded_and_configured_registry(self):
        import hashlib
        self.app.registry.parent.mkdir(parents=True,exist_ok=True)
        before={'models':[{'id':'TEST-OLD','classes':['trash'],'scope':'TEST ONLY','license':'TEST ONLY'}]}
        self.app.registry.write_text(json.dumps(before))
        detector=FakeDetectorForTestsOnly();detector.metadata={'models':before['models']}
        detector.registry_sha256=hashlib.sha256(self.app.registry.read_bytes()).hexdigest()
        self.app.detector=detector
        self.assertFalse(self.app.status()['activation_requires_restart'])
        after={'models':[{'id':'TEST-NEW','classes':['trash'],'scope':'TEST ONLY','license':'TEST ONLY'}]}
        self.app.registry.write_text(json.dumps(after))
        status=self.app.status();self.assertTrue(status['activation_requires_restart'])
        self.assertEqual(status['models'][0]['id'],'TEST-OLD')
        self.assertEqual(status['configured_models'][0]['id'],'TEST-NEW')

    def test_model_failure_retains_original_and_can_retry(self):
        def unavailable():raise ValueError('TEST ONLY: missing model')
        self.app.detector_factory=unavailable
        row=self.app.ingest(self.payload())['photo'];key=row['id'];self.keys.append(key)
        failed=self.wait(key);self.assertEqual(failed['state'],'error')
        self.assertTrue((self.app.base/key/'original').exists())
        self.app.detector_factory=FakeDetectorForTestsOnly
        self.app.retry(key);ready=self.wait(key);self.assertEqual(ready['state'],'done')
        self.assertEqual(ready['attempts'],2)

    def test_second_worker_does_not_recover_active_jobs(self):
        with self.assertRaises(RuntimeError):Pilot(self.root,detector_factory=FakeDetectorForTestsOnly)

if __name__=='__main__':unittest.main(verbosity=2)
