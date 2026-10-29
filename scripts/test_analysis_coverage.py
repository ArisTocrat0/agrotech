import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.pilot.service import analysis_coverage
class CoverageTests(unittest.TestCase):
    def photo(self,classes,state='done',events=None,mode='environment'):
        return {'state':state,'analysis_mode':mode,'result':{'model':{'models':[{'id':'test','classes':classes}]},'events':events or []}}
    def test_fire_success_is_not_trash_success(self):
        c=analysis_coverage(self.photo(['fire','smoke']))
        self.assertEqual(c['trash']['status'],'disabled');self.assertEqual(c['fire']['status'],'analyzed_no_detections')
    def test_actual_trash_no_detection_distinct(self):self.assertEqual(analysis_coverage(self.photo(['trash']))['trash']['status'],'analyzed_no_detections')
    def test_queue_error_and_weeds_distinct(self):
        self.assertEqual(analysis_coverage(self.photo(['trash'],'queued'))['trash']['status'],'not_analyzed')
        self.assertEqual(analysis_coverage(self.photo(['trash'],'error'))['trash']['status'],'error')
        self.assertEqual(analysis_coverage(self.photo(['weed'],mode='weeds'))['trash']['status'],'not_analyzed')
    def test_quarantined_result_not_valid_pollution(self):
        p=self.photo(['trash']);p['result']['model']['models'][0]['id']='trash-dronewaste500-v1-transfer-3e'
        self.assertEqual(analysis_coverage(p)['trash']['status'],'disabled')
if __name__=='__main__':unittest.main()
