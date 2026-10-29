import importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('recovery',Path(__file__).resolve().with_name('recover_quality_training.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RecoveryTests(unittest.TestCase):
 def test_live_execute_is_noop(self):
  with patch.object(m,'live_workers',return_value=[{'pid':260666}]),patch('sys.argv',['recovery','--run',next(iter(m.RUNS)),'--execute']),patch('builtins.print') as output,patch.object(m,'read',side_effect=AssertionError('must not read/write run')):
   m.main();self.assertIn('no_op_live_workers',output.call_args.args[0])
 def test_unstarted_smoke_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'outputs/pilot-training').mkdir(parents=True)
   with patch.object(m,'ROOT',root),patch.object(m,'live_workers',return_value=[]),patch('sys.argv',['recovery','--run','smoke-pyrosdis-yolo11n-cpu-20261020','--execute']):
    with self.assertRaisesRegex(AssertionError,'never starts'):m.main()
   self.assertFalse((root/'outputs/pilot-training/smoke-pyrosdis-yolo11n-cpu-20261020').exists())
 def test_snapshot_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);run=root/'outputs/pilot-training'/next(iter(m.RUNS));run.mkdir(parents=True);data=root/'datasets/litter-v3-land';data.mkdir(parents=True)
   (run/'quality-config.json').write_text(json.dumps({'run':run.name,'threads':2,'batch':1,'dataset_snapshot_lock_sha256':'old'}));(run/'progress.json').write_text('{}');(data/'snapshot-lock.json').write_text('{}')
   with patch.object(m,'ROOT',root),patch.object(m,'live_workers',return_value=[]),patch('sys.argv',['recovery','--run',run.name,'--execute']):
    with self.assertRaises(AssertionError):m.main()
 def test_stopper_patience_not_reset(self):
  t=SimpleNamespace(start_epoch=12,stopper=SimpleNamespace(patience=6));history=[{'epoch':i,'metrics':{'metrics/mAP50-95(B)':.3 if i==7 else .1}} for i in range(1,13)]
  m.restore_stopper(t,history);self.assertEqual(t.stopper.best_epoch,7);self.assertEqual(t.stopper.best_fitness,.3);self.assertTrue(t.stopper.possible_stop)
if __name__=='__main__':unittest.main()
