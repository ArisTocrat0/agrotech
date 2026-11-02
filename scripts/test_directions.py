"""Routing and training lifecycle contracts; synthetic fixtures are not quality metrics."""
import unittest,tempfile,threading,json,time,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.pilot.directions import detect_direction
from src.pilot.workspaces import Workspaces
from src.pilot.service import analysis_coverage
from PIL import Image
class Environment:
    metadata={'models':[{'id':'baseline','classes':['fire','smoke']} ]}
    def detect(self,image):return [{'class_name':'fire','confidence':.8,'bbox':[1,1,5,5]},{'class_name':'smoke','confidence':.7,'bbox':[1,1,5,5]}]
class Weed:
    metadata={'classes':['weed'],'backend':'test fixture'}
    def detect(self,image):return [{'class_name':'weed','confidence':.8,'bbox':[1,1,5,5]}]
class Routing(unittest.TestCase):
    def test_individual_and_common(self):
        app=SimpleNamespace(weed_detector=Weed());image=Image.new('RGB',(10,10))
        for mode,expected in [('trash',[]),('fire_smoke',['fire','smoke']),('weeds',['weed']),('common',['fire','smoke','weed'])]:
            rows,meta=detect_direction(app,mode,image,Environment());self.assertEqual([r['class_name'] for r in rows],expected)
    def test_common_partial_failure(self):
        from src.pilot.directions import UnavailableDetector
        rows,meta=detect_direction(SimpleNamespace(weed_detector=Weed()),'common',Image.new('RGB',(10,10)),UnavailableDetector('fixture failure'))
        self.assertEqual(rows[0]['class_name'],'weed');self.assertIn('environment',meta['errors'])
        coverage=analysis_coverage({'analysis_mode':'common','state':'done','result':{'model':meta,'events':rows}})
        self.assertEqual(coverage['fire']['status'],'error');self.assertEqual(coverage['weed']['status'],'analyzed_detections')
class Queue(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'scripts').mkdir();(self.root/'artifacts').mkdir();(self.root/'artifacts/yolo11n.pt').write_bytes(b'fixture')
        (self.root/'artifacts/ecokineu-models.json').write_text(json.dumps({'models':[{'id':'rejected','classes':['trash'],'enabled':False,'disabled_reason':'fixture'}]}))
        for name in ('litter-v3-land','smoke-pyrosdis-v1'):
            d=self.root/'datasets'/name;d.mkdir(parents=True);(d/'data.yaml').write_text('fixture');(d/'snapshot-lock.json').write_text('{}')
            for split in ('train','val'):
                (d/'images'/split).mkdir(parents=True);(d/'labels'/split).mkdir(parents=True)
                Image.new('RGB',(20,20),'white').save(d/'images'/split/'fixture.jpg');(d/'labels'/split/'fixture.txt').write_text('')
        (self.root/'scripts/train_direction.py').write_text("import time;time.sleep(.15)")
        self.app=SimpleNamespace(root=self.root,compute_lock=threading.RLock(),ingest_lock=threading.Lock(),store=SimpleNamespace(list=lambda:[]))
        self.manager=Workspaces(self.app)
    def tearDown(self):self.manager.close();self.temp.cleanup()
    def wait(self,predicate):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.03)
        self.fail('deadline')
    def test_isolation_serial_execution_and_cancel(self):
        with self.app.compute_lock:
            first=self.manager.enqueue('trash',{'epochs':1});second=self.manager.enqueue('fire_smoke',{'epochs':1})
            self.manager.cancel('fire_smoke',second['id'])
            self.assertEqual(self.manager.runs('trash')[0]['dataset'],'litter-v3-land')
            self.assertEqual(self.manager.runs('fire_smoke')[0]['state'],'cancelled')
        self.wait(lambda:self.manager.runs('trash')[0]['state']=='candidate')
        self.assertFalse((self.root/'datasets/litter-v3-land/weights').exists())
    def test_rejected_model_and_missing_weed_labels(self):
        with self.assertRaises(ValueError):self.manager.select('trash','rejected')
        with self.assertRaises(ValueError):self.manager.enqueue('weeds',{'epochs':1})
        with self.assertRaises(ValueError):self.manager.enqueue('trash',{'epochs':True})
    def test_dataset_validation_and_isolation(self):
        import base64
        from io import BytesIO
        def payload(color,split='train',labels='0 .5 .5 .5 .5'):
            stream=BytesIO();Image.new('RGB',(20,20),color).save(stream,format='PNG')
            return {'photo':base64.b64encode(stream.getvalue()).decode(),'name':'test.png','split':split,'labels':labels}
        record=self.manager.add_sample('weeds',payload('red'))
        self.assertEqual(self.manager.dataset('trash')['records'],[])
        self.assertEqual(len(self.manager.dataset('weeds')['records']),1)
        self.assertFalse(self.manager.status('weeds')['training']['available'])
        with self.assertRaises(ValueError):self.manager.add_sample('weeds',payload('red','val'))
        with self.assertRaises(ValueError):self.manager.add_sample('weeds',payload('blue',labels='1 .5 .5 .5 .5'))
        self.manager.add_sample('weeds',payload('blue','val'))
        self.assertTrue(self.manager.status('weeds')['training']['available'])
        self.assertIn('0 0.5',self.manager.sample('weeds',record['id'],'labels')['labels'])
    def test_two_successful_runs_are_serial(self):
        (self.root/'scripts/train_direction.py').write_text("import sys,time,json;from pathlib import Path;p=Path(sys.argv[2]);(p/'times.json').write_text(json.dumps({'start':time.time()}));time.sleep(.2);d=json.loads((p/'times.json').read_text());d['end']=time.time();(p/'times.json').write_text(json.dumps(d))")
        first=self.manager.enqueue('trash',{'epochs':1});second=self.manager.enqueue('fire_smoke',{'epochs':1})
        self.wait(lambda:all(self.manager.runs(k)[0]['state']=='candidate' for k in ('trash','fire_smoke')))
        a=json.loads((self.root/'outputs/directions/trash/runs'/first['id']/'times.json').read_text());b=json.loads((self.root/'outputs/directions/fire_smoke/runs'/second['id']/'times.json').read_text())
        self.assertLessEqual(a['end'],b['start'])
    def test_source_view_verifies_linked_public_image(self):
        import hashlib
        source=self.root/'source.jpg';Image.new('RGB',(20,20),'red').save(source)
        base=self.root/'datasets/litter-v3-land';target=base/'images/train/linked.jpg';target.symlink_to(source)
        (base/'labels/train/linked.txt').write_text('0 .5 .5 .5 .5')
        (base/'manifest.json').write_text(json.dumps({'records':[{'path':'images/train/linked.jpg','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'split':'train'}]}))
        self.assertEqual(self.manager.source_sample('trash','litter-v3-land',0,'labels')['status'],'available')
        self.assertTrue(self.manager.source_sample('trash','litter-v3-land',0,'image').startswith(b'\xff\xd8'))
        source.write_bytes(b'changed');
        with self.assertRaises(ValueError):self.manager.source_sample('trash','litter-v3-land',0,'image')
        with self.assertRaises(ValueError):self.manager.source_sample('weeds','litter-v3-land',0,'labels')
    def test_smoke_selection_preserves_saved_fire(self):
        baseline={'id':'saved-fire','classes':['fire',None,'smoke'],'path':'artifacts/fire.xml','assets':[]}
        registry=self.root/'artifacts/ecokineu-models.json';original=json.dumps({'models':[baseline]});registry.write_text(original)
        path=self.root/'outputs/directions/fire_smoke/models.json'
        path.write_text(json.dumps({'active':[],'history':[],'versions':[{'id':'smoke-only','accepted':True,'spec':{'id':'smoke-only','classes':['smoke'],'path':'artifacts/smoke.xml','assets':[]}}]}))
        self.app.direction_detectors={};self.app.compiled_models={};self.app.weed_detector=Weed()
        self.manager.select('fire_smoke','smoke-only')
        effective=json.loads(self.app.registry.read_text())['models'];self.assertEqual([s['classes'] for s in effective],[['smoke'],['fire',None,None]])
        self.assertEqual(registry.read_text(),original)
    def test_selected_weed_version_uses_its_native_detector(self):
        from unittest.mock import patch
        from src.pilot.service import Pilot
        path=self.root/'outputs/directions/weeds/models.json';path.write_text(json.dumps({'active':['new-weed'],'history':[],'versions':[{'id':'new-weed','accepted':True,'spec':{'id':'new-weed','classes':['weed'],'path':'artifacts/new.xml','assets':[]}}]}))
        self.app.workspaces=self.manager;self.app.compiled_models={}
        sentinel=SimpleNamespace(metadata={'classes':['weed']})
        with patch('src.pilot.detector.Detector',return_value=sentinel) as detector:
            self.assertIs(Pilot.load_weed_detector(self.app),sentinel)
            self.assertEqual(detector.call_args.kwargs['allowed_classes'],['weed'])
            registry=json.loads((self.manager.base/'weeds/effective-models.json').read_text());self.assertEqual(registry['models'][0]['id'],'new-weed')
    def test_candidate_cannot_register_without_real_reports(self):
        with self.app.compute_lock:
            run=self.manager.enqueue('trash',{'epochs':1});folder=self.root/'outputs/directions/trash/runs'/run['id'];run['state']='candidate';(folder/'run.json').write_text(json.dumps(run))
        with self.assertRaisesRegex(ValueError,'реальная оценка'):self.manager.register_reviewed('trash',run['id'])
    def test_external_training_lock_keeps_job_queued(self):
        import fcntl
        path=self.root/'outputs/pilot-training/training.lock';path.parent.mkdir(parents=True)
        with path.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);self.manager.enqueue('trash',{'epochs':1});time.sleep(.7)
            self.assertEqual(self.manager.runs('trash')[0]['state'],'queued')
        self.wait(lambda:self.manager.runs('trash')[0]['state']=='candidate')
    def test_running_job_cancel(self):
        (self.root/'scripts/train_direction.py').write_text('import time;time.sleep(5)')
        run=self.manager.enqueue('trash',{'epochs':1});self.wait(lambda:self.manager.runs('trash')[0]['state']=='running')
        self.manager.cancel('trash',run['id']);self.wait(lambda:self.manager.runs('trash')[0]['state']=='cancelled')
    def test_orphan_process_is_detected_and_can_be_cancelled(self):
        import subprocess
        self.manager.close();(self.root/'scripts/train_direction.py').write_text('import time;time.sleep(5)')
        run={'id':'b'*32,'direction':'trash','state':'running','created':0};folder=self.root/'outputs/directions/trash/runs'/run['id'];folder.mkdir()
        process=subprocess.Popen([sys.executable,str(self.root/'scripts/train_direction.py'),'--run',str(folder)])
        try:
            run['pid']=process.pid;(folder/'run.json').write_text(json.dumps(run));self.manager=Workspaces(self.app)
            self.assertEqual(self.manager.runs('trash')[0]['state'],'orphan_running');self.assertTrue(self.manager.orphan_busy())
            self.manager.cancel('trash',run['id']);process.wait(timeout=5);self.wait(lambda:self.manager.runs('trash')[0]['state']=='cancelled')
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=5)
    def test_error_and_restart(self):
        (self.root/'scripts/train_direction.py').write_text('raise RuntimeError("fixture")')
        self.manager.enqueue('trash',{'epochs':1});self.wait(lambda:self.manager.runs('trash')[0]['state']=='error')
        self.manager.close();p=self.root/'outputs/directions/trash/runs/restart';p.mkdir();(p/'run.json').write_text(json.dumps({'id':'restart','state':'running','created':0}))
        self.manager=Workspaces(self.app);self.assertEqual(next(r for r in self.manager.runs('trash') if r['id']=='restart')['state'],'interrupted')
if __name__=='__main__':unittest.main()
