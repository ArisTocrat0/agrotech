"""Regression tests for image adapter contracts, no recognition metrics."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from src.pilot.detector import Detector
class FakeNativeForTestOnly:
    def __init__(self,output):self.data=output
    def output(self,index):return 'output'
    def __call__(self,tensor):
        self.tensor=tensor
        return {'output':self.data}
class AdapterTests(unittest.TestCase):
    def detector(self,pred):
        net=FakeNativeForTestOnly(np.asarray(pred,dtype=np.float32).T[None])
        detector=Detector.__new__(Detector)
        detector.models=[({'id':'TEST ONLY','imgsz':100,'classes':['trash'],'threshold':.35},net)]
        return detector,net
    def test_disabled_registry_never_loads_weights(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as temp:
            registry=Path(temp)/'registry.json'
            registry.write_text(json.dumps({'models':[{'id':'quarantined','enabled':False,'path':'missing-no-load','classes':['trash']}]}))
            detector=Detector(registry)
            self.assertEqual(detector.models,[])
            self.assertEqual(detector.detect(Image.new('RGB',(20,20))),[])

    def test_nms_precedes_clipping(self):
        # Raw IoU 1/3: keep both. Clipping before NMS would falsely suppress one.
        d,_=self.detector([[-25,50,150,100,.9],[25,50,50,100,.8]])
        rows=d.detect(Image.new('RGB',(100,100),'white'))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['bbox'],[0,0,50,100])
        self.assertEqual(rows[1]['bbox'],[0,0,50,100])
    def test_explicitly_ignored_class_cannot_become_event(self):
        net=FakeNativeForTestOnly(np.asarray([[50,50,20,20,.1,.9,.1],[75,75,20,20,.1,.1,.8]],dtype=np.float32).T[None])
        d=Detector.__new__(Detector);d.models=[({'id':'TEST ONLY','imgsz':100,'classes':['fire',None,'smoke'],'threshold':.35},net)]
        self.assertEqual([r['class_name'] for r in d.detect(Image.new('RGB',(100,100),'white'))],['smoke'])

    def test_unrequested_network_is_not_executed(self):
        d,net=self.detector([[50,50,30,30,.9]])
        self.assertEqual(d.detect(Image.new('RGB',(100,100)),allowed_classes=['fire','smoke']),[])
        self.assertFalse(hasattr(net,'tensor'))

    def test_nonfinite_native_output_is_error(self):
        d,_=self.detector([[50,50,30,30,float('nan')]])
        with self.assertRaises(ValueError):d.detect(Image.new('RGB',(100,100),'white'))
    def test_rgb_nchw_and_letterbox(self):
        d,net=self.detector([[50,50,20,20,.9]])
        d.detect(Image.new('RGB',(100,50),(255,0,0)))
        self.assertEqual(net.tensor.shape,(1,3,100,100))
        self.assertEqual(float(net.tensor[0,0,50,50]),1.)
        self.assertEqual(float(net.tensor[0,2,50,50]),0.)
        self.assertAlmostEqual(float(net.tensor[0,0,0,0]),114/255,places=6)
if __name__=='__main__':unittest.main()
