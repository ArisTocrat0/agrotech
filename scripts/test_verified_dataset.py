"""Offline verified dataset and HTTP handler tests; no GPU or socket required."""
import fcntl
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from src.application.dataset import prepare_dataset
from src.application.review import save_decision
from src.web.service import Dashboard
from src.web.http import make_handler
from scripts import train_yolo
from scripts.train_yolo_full import validate_dataset


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = 'a' * 32
        self.folder = self.root / 'outputs/web' / self.job_id
        (self.folder / 'input').mkdir(parents=True)
        self.output = self.root / 'yolo_dataset/verified'
        rows = []
        for i in range(3):
            name = f'{i}.png'
            Image.new('RGB', (30, 20), (i*50, 0, 0)).save(self.folder / 'input' / name)
            rows.append({'image':name, 'width':30, 'height':20, 'detections':[
                {'id':1, 'species':'unknown', 'stage':'unknown', 'kind':'unknown',
                 'similarity_score':0.01, 'bbox':dict(x1=1,y1=2,x2=20,y2=15)}]})
        (self.folder / 'results.json').write_text(json.dumps(rows))
        for i in range(3):
            save_decision(self.folder, i, 1, 'weed')

    def test_split_and_manual_labels_not_model_threshold(self):
        summary = prepare_dataset(self.folder, self.output, self.job_id)
        self.assertEqual((summary['train_images'], summary['val_images'], summary['objects']), (2,1,3))
        config = validate_dataset(self.output / 'dataset.yaml')
        base = Path(config['path'])
        train = {p.name for p in (base/'images/train').iterdir()}
        val = {p.name for p in (base/'images/val').iterdir()}
        self.assertFalse(train & val)
        self.assertEqual(config['names'], {0:'weed'})
        for path in (base/'labels').rglob('*.txt'):
            self.assertTrue(path.read_text().startswith('0 '))

    def test_unresolved_preserves_previous_dataset(self):
        prepare_dataset(self.folder, self.output, self.job_id)
        previous = (self.output/'dataset.yaml').read_bytes()
        save_decision(self.folder, 1, 1, 'unknown')
        with self.assertRaisesRegex(ValueError, 'Сначала проверьте'):
            prepare_dataset(self.folder, self.output, self.job_id)
        self.assertEqual((self.output/'dataset.yaml').read_bytes(), previous)

    def test_requires_two_positive_images(self):
        for i in [1,2]:
            save_decision(self.folder, i, 1, 'crop')
        with self.assertRaisesRegex(ValueError, 'минимум два'):
            prepare_dataset(self.folder, self.output, self.job_id)
        self.assertFalse((self.output/'dataset.yaml').exists())

    def test_identical_images_cannot_leak(self):
        image = (self.folder/'input/0.png').read_bytes()
        for i in [1,2]:
            (self.folder/f'input/{i}.png').write_bytes(image)
        with self.assertRaisesRegex(ValueError, 'минимум два'):
            prepare_dataset(self.folder, self.output, self.job_id)

    def test_publication_failure_preserves_snapshot(self):
        prepare_dataset(self.folder, self.output, self.job_id)
        previous = (self.output/'dataset.yaml').read_bytes()
        with patch('src.application.dataset.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                prepare_dataset(self.folder, self.output, self.job_id)
        self.assertEqual((self.output/'dataset.yaml').read_bytes(), previous)
        self.assertEqual(len(list((self.output/'versions').iterdir())),1)

    def test_existing_get_routes(self):
        handler = make_handler(Dashboard(self.root))
        for path in ['/', '/client.js', '/api/jobs', '/api/references', '/api/crop-import']:
            request = SimpleNamespace(path=path, json=Mock(), send=Mock())
            handler.do_GET(request)
            response = request.json if request.json.called else request.send
            self.assertEqual(response.call_args.args[0], 200, path)

    def test_endpoint_and_training_readiness_and_lock(self):
        training = self.root/'outputs/yolo_training'
        with patch.object(train_yolo,'ROOT',self.root), patch.object(train_yolo,'TRAINING',training), patch.object(train_yolo,'STATUS',training/'status.json'):
            self.assertFalse(train_yolo.training_status()['full_ready'])
            handler = make_handler(Dashboard(self.root))
            request = SimpleNamespace(path=f'/api/jobs/{self.job_id}/dataset', headers={}, json=Mock())
            handler.do_POST(request)
            self.assertEqual(request.json.call_args.args[0],201)
            self.assertTrue(train_yolo.training_status()['full_ready'])
            with (training/'training.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                request.json.reset_mock()
                handler.do_POST(request)
                self.assertEqual(request.json.call_args.args[0],400)
            request.headers={'Origin':'http://elsewhere','Host':'localhost'}
            request.json.reset_mock()
            handler.do_POST(request)
            self.assertEqual(request.json.call_args.args[0],403)


if __name__ == '__main__':
    unittest.main()
