"""Synthetic geometry only; no model quality claims or persisted fake coordinates."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from scripts.analyze_v2_errors import tiled
class MaskDetectorForTestOnly:
    def detect(self,image):
        import numpy as np
        a=np.asarray(image);ys,xs=np.where((a[:,:,0]==255)&(a[:,:,1]==0)&(a[:,:,2]==0))
        if not len(xs):return []
        return [{'class_name':'trash','confidence':.9,'bbox':[int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]}]
class TileGeometryTests(unittest.TestCase):
    def test_overlapping_crop_offsets_dedup_and_bottom_right_coverage(self):
        image=Image.new('RGB',(1300,800),'black');draw=ImageDraw.Draw(image);draw.rectangle([500,300,549,349],fill='red');draw.rectangle([1270,770,1299,799],fill='red')
        rows,info=tiled(MaskDetectorForTestOnly(),image)
        self.assertEqual(sorted(r['bbox'] for r in rows),[[500,300,550,350],[1270,770,1300,800]])
        self.assertGreater(info['detections_before_global_nms'],len(rows));self.assertTrue(any(w[2:]==(1300,800) for w in info['windows']))
    def test_smaller_than_tile_uses_single_unshifted_window(self):
        image=Image.new('RGB',(480,320),'black');ImageDraw.Draw(image).rectangle([12,19,31,40],fill='red');rows,info=tiled(MaskDetectorForTestOnly(),image)
        self.assertEqual(info['tiles'],1);self.assertEqual(rows[0]['bbox'],[12,19,32,41])
if __name__=='__main__':unittest.main()
