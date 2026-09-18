"""Offline tests for web training lifecycle; no model training or downloads."""
import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import train_yolo as training


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'outputs/yolo_training'
        self.folder.mkdir(parents=True)
        self.patches = [patch.object(training, 'ROOT', self.root),
                        patch.object(training, 'TRAINING', self.folder),
                        patch.object(training, 'STATUS', self.folder / 'status.json')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_idle_and_missing_dataset(self):
        self.assertEqual(training.training_status()['status'], 'idle')
        self.assertFalse(training.training_status()['full_ready'])
        with self.assertRaisesRegex(ValueError, 'датасет'):
            training.start_training()

    def test_running_lock_and_interrupted_process(self):
        training.save_status({'status':'running','run':'trial','epoch':1,'epochs':5})
        with (self.folder/'training.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(training.training_status()['status'], 'running')
            (self.root/'yolo_dataset/trial').mkdir(parents=True)
            (self.root/'yolo_dataset/trial/dataset.yaml').touch()
            (self.root/'artifacts').mkdir()
            (self.root/'artifacts/yolo11n.pt').touch()
            with patch.object(training.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'уже выполняется'):
                    training.start_training()
                spawn.assert_not_called()
        self.assertEqual(training.training_status()['status'], 'error')

    def test_finished_weights_and_log(self):
        folder = self.folder/'trial'
        (folder/'weights').mkdir(parents=True)
        (folder/'weights/best.pt').write_bytes(b'checkpoint')
        (folder/'training.log').write_text('\x1b[1mTraining\x1b[0m\rDone')
        training.save_status({'status':'done','run':'trial','epoch':5,'epochs':5})
        state = training.training_status()
        self.assertTrue(state['weights_ready'])
        self.assertEqual(state['log'], 'Training\nDone')

    def test_legacy_full_run_recovers_actual_epoch(self):
        folder = self.folder/'full_test'
        (folder/'weights').mkdir(parents=True)
        (folder/'weights/best.pt').write_bytes(b'checkpoint')
        (folder/'results.csv').write_text(' epoch, train/box_loss\n12,4.0\n42,3.2\n')
        training.save_status({'status':'done','mode':'full','run':'full_test','epoch':150,'epochs':150})
        state = training.training_status()
        self.assertEqual(state['epoch'],42)
        self.assertEqual(state['percent'],28)
        self.assertTrue(state['stopped_early'])
        self.assertTrue(state['weights_ready'])

    def test_actual_epoch_survives_missing_csv(self):
        training.save_status({'status':'done','mode':'full','run':'full_test','epoch':42,'epochs':150})
        state = training.training_status()
        self.assertEqual(state['epoch'],42)
        self.assertTrue(state['stopped_early'])

    def test_full_budget_is_not_early_stopping(self):
        training.save_status({'status':'done','mode':'full','run':'full_test','epoch':150,'epochs':150})
        self.assertFalse(training.training_status()['stopped_early'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
