import copy
import tempfile
import unittest
from pathlib import Path
import torch
from src.recognition.autolearn import split_records, train_head
from src.web.service import Dashboard


class AutomaticLearningTests(unittest.TestCase):
    def index(self):
        records, vectors = [], []
        for label, species in enumerate(('Пшеница', 'Бодяк полевой', 'Ячмень')):
            for i in range(30):
                records.append({'species': species, 'kind': 'weed' if label == 1 else 'crop',
                                'stage': 'unknown', 'sha256': f'{label}-{i}'})
                vectors.append(torch.eye(3)[label])
        return {'metadata': {'records': records}, 'embeddings': torch.stack(vectors)}

    def test_no_duplicate_leakage_and_conflicting_labels_rejected(self):
        records = self.index()['metadata']['records']
        records.append(copy.deepcopy(records[0]))
        train, val, test, excluded = split_records(records)
        self.assertFalse(set(train) & set(val) or set(test) & set(train) or set(test) & set(val))
        self.assertEqual(len(train + val + test), 90)
        self.assertFalse(excluded)
        records[-1]['species'] = 'Пырей'
        with self.assertRaises(ValueError):
            split_records(records)

    def test_training_cache_and_heldout_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'head.pt'
            index = self.index()
            classifier = train_head(index, path)
            self.assertEqual(classifier.report['accuracy'], 1.)
            self.assertIsNone(classifier.report['field_accuracy'])
            self.assertEqual(classifier.report['count'], 18)
            self.assertEqual(classifier.report['crop_species'], ['Пшеница', 'Ячмень'])
            prediction = classifier.classify(torch.eye(3))
            self.assertEqual([x[0] for x in prediction], ['Пшеница', 'Бодяк полевой', 'Ячмень'])
            self.assertTrue(all(x[1] == 'unknown' for x in prediction))
            modified = path.stat().st_mtime_ns
            train_head(index, path)
            self.assertEqual(path.stat().st_mtime_ns, modified)
            index['metadata']['records'][0]['sha256'] = 'changed'
            train_head(index, path)
            self.assertNotEqual(path.stat().st_mtime_ns, modified)

    def test_field_without_crop_data_stays_unknown(self):
        from unittest.mock import Mock, patch
        from PIL import Image
        from src.application.inference import run_inference
        from src.config import load_config
        from src.domain.types import DetectionCandidate
        from src.application.review import load_results
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (128, 128), (20, 150, 20)).save(root / 'field.png')
            config = load_config()
            config.update(crop='Пшеница', learning_report={'crop_species': []})
            detector = Mock()
            detector.candidates.return_value = [DetectionCandidate(10, 10, 30, 30)]
            model = Mock()
            classifier = Mock()
            classifier.species_kinds = {'Бодяк полевой': 'weed'}
            classifier.classify.return_value = [('Бодяк полевой', 'unknown', .8)]
            with patch('src.application.inference.VegetationDetector', return_value=detector), patch('src.application.inference.estimate_rows', return_value={}):
                run_inference(root / 'field.png', root / 'result', config, model, classifier)
            row = load_results(root / 'result')[0]
            model.encode.assert_not_called()
            self.assertFalse(row['crop_supported'])
            self.assertEqual(row['total_weeds'], 0)
            self.assertEqual(row['unknown_count'], 1)
            self.assertIsNone(row['detections'][0]['similarity_score'])
            self.assertNotIn('review', row['detections'][0])
            self.assertTrue((root / 'result/annotated/field.png.png').exists())

    def test_uncalibrated_model_always_abstains(self):
        from src.recognition.autolearn import LearnedClassifier
        classifier = LearnedClassifier({'classes': [('Пшеница', 'crop'), ('Бодяк', 'weed')],
                                        'report': {}, 'threshold': None,
                                        'head': torch.tensor([[100., 0.], [0., 100.], [0., 0.]])})
        self.assertEqual(classifier.classify(torch.tensor([[1., 0.]]))[0][0], 'unknown')

    def test_too_small_dataset_and_invalid_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            index = self.index()
            index['metadata']['records'] = index['metadata']['records'][:2]
            index['embeddings'] = index['embeddings'][:2]
            with self.assertRaises(ValueError):
                train_head(index, Path(directory) / 'head.pt')
        with self.assertRaises(ValueError):
            Dashboard.options({'crop': '../test'})
        self.assertEqual(Dashboard.options({'crop': 'Пшеница'})['crop'], 'Пшеница')


if __name__ == '__main__':
    torch.set_num_threads(2)
    unittest.main()
