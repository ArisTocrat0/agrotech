import copy
import tempfile
import unittest
from pathlib import Path
import torch
from src.recognition.autolearn import split_records, train_head, LearnedClassifier
from src.web.service import Dashboard


class AutomaticLearningTests(unittest.TestCase):
    def index(self, count=30):
        records, vectors = [], []
        for label, species in enumerate(('Пшеница', 'Бодяк полевой', 'Ячмень')):
            for i in range(count):
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

    def test_training_cache_heldout_report_and_category_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'head.pt'
            index = self.index()
            classifier = train_head(index, path)
            self.assertEqual(classifier.report['accuracy'], 1.)
            self.assertIsNone(classifier.report['field_accuracy'])
            self.assertEqual(classifier.report['count'], 18)
            self.assertEqual(classifier.report['crop_species'], ['Пшеница', 'Ячмень'])
            self.assertEqual(classifier.report['category']['accuracy'], 1.)
            self.assertEqual(classifier.report['category']['crop_weed_error_rate'], 0.)
            detailed = classifier.classify_detailed(torch.eye(3))
            self.assertEqual([x['species'] for x in detailed], ['Пшеница', 'Бодяк полевой', 'Ячмень'])
            self.assertTrue(all(x['stage'] == 'unknown' for x in detailed))
            self.assertTrue(all(x['category_accepted'] for x in detailed))
            modified = path.stat().st_mtime_ns
            train_head(index, path)
            self.assertEqual(path.stat().st_mtime_ns, modified)
            index['metadata']['records'][0]['sha256'] = 'changed'
            train_head(index, path)
            self.assertNotEqual(path.stat().st_mtime_ns, modified)

    def test_field_without_crop_data_preserves_species_but_not_category(self):
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
            detector.mask.return_value = torch.zeros((128,128), dtype=torch.uint8).numpy()
            detector.candidates.return_value = [DetectionCandidate(10, 10, 30, 30)]
            model = Mock()
            model.encode.return_value = torch.tensor([[1., 0.]])
            classifier = Mock()
            classifier.species_kinds = {'Бодяк полевой': 'weed'}
            classifier.classify.return_value = [('Бодяк полевой', 'unknown', .8)]
            with patch('src.application.inference.VegetationDetector', return_value=detector), \
                 patch('src.application.inference.estimate_rows', return_value={}):
                run_inference(root / 'field.png', root / 'result', config, model, classifier)
            row = load_results(root / 'result')[0]
            model.encode.assert_called_once()
            self.assertFalse(row['crop_supported'])
            self.assertEqual(row['total_weeds'], 0)
            self.assertEqual(row['unknown_count'], 1)
            detection = row['detections'][0]
            self.assertEqual(detection['species'], 'Бодяк полевой')
            self.assertEqual(detection['species_prediction'], 'Бодяк полевой')
            self.assertEqual(detection['kind'], 'unknown')
            self.assertIn('unsupported_crop', detection['uncertainty_reasons'])
            self.assertEqual(detection['model_score'], .8)
            self.assertNotIn('review', detection)
            self.assertFalse(row['manual_review_required'])
            self.assertEqual(row['analysis_status'], 'complete')
            self.assertTrue((root / 'result/annotated/field.png.png').exists())

    def test_small_validation_is_not_object_low_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            classifier = train_head(self.index(count=9), Path(directory) / 'head.pt')
            self.assertIsNone(classifier.state['threshold'])
            self.assertEqual(classifier.report['species_calibration']['status'],
                             'insufficient_validation_data')
            prediction = classifier.classify_detailed(torch.tensor([[1., 0., 0.]]))[0]
            self.assertEqual(prediction['species'], 'unknown')
            self.assertEqual(prediction['species_prediction'], 'Пшеница')
            self.assertIn('insufficient_calibration_data', prediction['uncertainty_reasons'])
            self.assertNotIn('low_species_margin', prediction['uncertainty_reasons'])

    def test_low_margin_is_distinct_from_missing_calibration(self):
        state = {
            'classes': [('Бодяк', 'weed'), ('Пырей', 'weed'), ('Пшеница', 'crop')],
            'report': {}, 'threshold': .5, 'category_threshold': .2,
            'calibration': {'species': {'status':'calibrated'},
                            'category': {'status':'calibrated'}},
            'head': torch.tensor([[1., .9, 0.], [0., 0., 1.], [0., 0., 0.]])
        }
        classifier = LearnedClassifier(state)
        prediction = classifier.classify_detailed(torch.tensor([[1., 0.]]))[0]
        self.assertEqual(prediction['species'], 'unknown')
        self.assertEqual(prediction['species_prediction'], 'Бодяк')
        self.assertIn('low_species_margin', prediction['uncertainty_reasons'])
        # Two weed species are close, but the weed/crop category is still separable.
        self.assertEqual(prediction['category'], 'weed')
        self.assertTrue(prediction['category_accepted'])

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
