"""Evaluation bookkeeping regressions, not actual recognition results."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_quality_v2 import metrics,iou
class QualityMetricTests(unittest.TestCase):
    def test_matching_does_not_credit_duplicate_boxes(self):
        rows=[{'source_image_id':1,'gt':[[0,0,10,10]],'image_role':'positive','path':'fixture','site':'fixture','split':'val_development'}]
        pred={'1':[{'bbox':[0,0,10,10],'confidence':.9},{'bbox':[0,0,10,10],'confidence':.8}]}
        result=metrics(rows,pred,.5);self.assertEqual((result['tp'],result['fp'],result['fn']),(1,1,0));self.assertEqual(result['precision'],.5)
    def test_negative_alarm_is_image_rate_not_box_rate(self):
        row={'source_image_id':1,'gt':[],'image_role':'verified_negative','path':'fixture','site':'fixture','split':'val_development'}
        preds={'1':[{'bbox':[0,0,10,10],'confidence':.9},{'bbox':[0,0,20,20],'confidence':.8}]};r=metrics([row],preds,.5)
        self.assertEqual(r['negative_images_with_alarm'],1);self.assertEqual(r['negative_image_alarm_rate'],1);self.assertEqual(r['fp'],2)
    def test_threshold_rejects_prediction_without_losing_ground_truth(self):
        row={'source_image_id':1,'gt':[[0,0,10,10]],'image_role':'positive','path':'fixture','site':'fixture','split':'val_development'}
        r=metrics([row],{'1':[{'bbox':[0,0,10,10],'confidence':.2}]},.5);self.assertEqual((r['tp'],r['fp'],r['fn']),(0,0,1));self.assertEqual(iou([0,0,10,10],[5,0,15,10]),1/3)
if __name__=='__main__':unittest.main()
