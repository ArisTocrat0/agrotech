"""Project rule boundaries, uncertain classification and motion deadlines."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import torch

from src.domain.agronomy import plant_info, assessment, stage_window, stage_advice
from src.domain.performance import motion_budget
from src.domain.types import WeedDetection
from src.infrastructure.exporters import image_result, save_results
from src.recognition.classifier import ReferenceClassifier


def weed(species='Щирица', stage='2 листа'):
    return {'species': species, 'stage': stage, **plant_info(species)}


class AgronomyTests(unittest.TestCase):
    def test_taxonomy(self):
        expected = {'Щирица': ('A', 'annual'), 'Ширица': ('A', 'annual'), 'Марь белая': ('A', 'annual'),
                    'Бодяк полевой': ('A', 'perennial'), 'Осот': ('A', 'perennial'),
                    'Вьюнок полевой': ('A', 'perennial'), 'Выюнок': ('A', 'perennial'),
                    'Овсюг': ('B', 'annual'), 'Куриное просо': ('B', 'annual'),
                    'Пырей ползучий': ('B', 'perennial')}
        for species, pair in expected.items():
            with self.subTest(species=species):
                info = plant_info(species)
                self.assertEqual((info['weed_class'], info['lifecycle']), pair)
        for species in ['Пшеница', 'Ячмень', 'Подсолнечник']:
            self.assertEqual(plant_info(species)['kind'], 'crop')
        self.assertIsNone(plant_info('Марья')['weed_class'])
        self.assertIsNone(plant_info('Осот', 'not_plant')['weed_class'])

    def test_actions_and_priority(self):
        for count, action in [(0, 'do_not_spray'), (5, 'do_not_spray'), (6, 'standard_rate'),
                              (15, 'standard_rate'), (16, 'maximum_label_rate')]:
            result = assessment([weed()] * count, 100, 100, 1)
            self.assertEqual(result['recommendation'], action)
        mixed = assessment([weed()] * 20 + [weed('Пырей ползучий')] * 2, 100, 100, 1)
        self.assertEqual(mixed['threshold_action'], 'urgent_treatment')
        self.assertEqual(mixed['priority'], 'high')
        self.assertEqual(mixed['classes']['B']['perennial_per_m2'], 2)
        self.assertEqual(mixed['classes']['A']['annual_count'], 20)
        self.assertFalse(mixed['automatic_application_allowed'])
        self.assertIsNone(mixed['dose'])
        fractional = assessment([weed()] * 11, 200, 100, 1)
        self.assertEqual(fractional['annual_per_m2'], 5.5)
        self.assertEqual(fractional['threshold_action'], 'standard_rate')

    def test_uncertainty_and_phase_override(self):
        cases = [([weed('mystery')], 'uncertain_classification'),
                 ([{'kind': 'unknown'}], 'uncertain_classification'),
                 ([weed(stage='цветение')] * 16, 'late_stage_crop_risk'),
                 ([weed(stage='Розетка')] * 6, 'unknown_stage'),
                 ([weed('Бодяк полевой')], 'perennials_below_threshold')]
        for detections, reason in cases:
            result = assessment(detections, 100, 100, 1)
            self.assertEqual(result['recommendation'], 'agronomist_review')
            self.assertIn(reason, result['review_reasons'])
        result = assessment([weed()] * 20, 100, 100)
        self.assertIsNone(result['area_m2'])
        self.assertEqual(result['recommendation'], 'agronomist_review')
        for width, gsd in [(0, 1), (100, float('nan')), (100, 0)]:
            with self.assertRaises(ValueError):
                assessment([], width, 100, gsd)

    def test_phase_parsing(self):
        for stage, expected in [('Семядоли — 2 листа', 'early'), ('4 – 6 листьев', 'developed'),
                                ('Более 6 листьев / цветение', 'late'), ('12 листьев', 'late'),
                                ('3 листа', 'unknown'), ('Розетка', 'unknown')]:
            self.assertEqual(stage_window(stage), expected)
        self.assertEqual(stage_advice('4-6 листьев')['proposed_multiplier_range'], [1.15, 1.2])
        self.assertEqual(assessment([weed(stage='4-6 листьев')], 100, 100, 1)['recommendation'], 'do_not_spray')

    def test_exported_classes(self):
        result = image_result('test.png', 100, 100,
                              [WeedDetection(1, 'Пырей ползучий', '4-6 листьев', .9, 0, 0, 10, 10)])
        with tempfile.TemporaryDirectory() as directory:
            save_results([result], Path(directory))
            with (Path(directory)/'results.csv').open(encoding='utf-8-sig') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual((row['weed_class'], row['lifecycle'], row['priority']), ('B', 'perennial', 'high'))
            self.assertEqual(row['stage_action'], 'review_increase_15_20')

    def test_manual_weed_without_species_is_counted_but_needs_review(self):
        from src.application.review import save_decision
        result = image_result('test.png', 100, 100,
                              [WeedDetection(1, 'unknown', 'unknown', .4, 0, 0, 10, 10)])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            save_results([result], folder)
            updated = save_decision(folder, 0, 1, 'weed')[0]
            self.assertEqual(updated['total_weeds'], 1)
            self.assertEqual(updated['unknown_count'], 0)
            self.assertIsNone(updated['detections'][0]['weed_class'])
            self.assertIn('uncertain_classification', updated['agronomy']['review_reasons'])

    def test_class_ambiguity(self):
        for species in [('Щирица', 'Овсюг'), ('Щирица', 'Бодяк полевой')]:
            index = {'embeddings': torch.eye(2), 'metadata': {'records': [
                {'species': name, 'stage': '2 листа', 'kind': 'weed'} for name in species]}}
            classifier = ReferenceClassifier(index, top_k=1)
            result = classifier.classify(torch.tensor([[1., 0.], [.7, .7]]))
            self.assertEqual(result[0][0], species[0])
            self.assertEqual(result[1][0], 'unknown')
        with self.assertRaises(ValueError):
            ReferenceClassifier(index, category_margin=float('nan'))

    def test_motion_budget(self):
        result = motion_budget(.1, 20, 1, 20)
        self.assertAlmostEqual(result['processing_distance_m'], 5/9)
        self.assertAlmostEqual(result['deadline_seconds'], .16)
        self.assertTrue(result['within_budget'])
        self.assertFalse(motion_budget(.2, 20, 1, 20)['within_budget'])
        self.assertIsNone(motion_budget(.1)['within_budget'])
        with self.assertRaises(ValueError):
            motion_budget(float('nan'))

    def test_stage_ambiguity_preserves_species(self):
        index = {'embeddings': torch.eye(2), 'metadata': {'records': [
            {'species': 'Щирица', 'stage': stage, 'kind': 'weed'}
            for stage in ['2 листа', 'цветение']]}}
        classifier = ReferenceClassifier(index, top_k=1)
        result = classifier.classify(torch.tensor([[.7, .7], [1., 0.]]))
        self.assertEqual(result[0][:2], ('Щирица', 'unknown'))
        self.assertEqual(result[1][:2], ('Щирица', '2 листа'))

    def test_offline_model_load(self):
        from src.recognition.embeddings import DinoEmbeddingModel
        with patch('transformers.AutoImageProcessor.from_pretrained') as processor, \
             patch('transformers.AutoModel.from_pretrained') as model:
            DinoEmbeddingModel('local-model', device='cpu')
            processor.assert_called_once_with('local-model', local_files_only=True)
            model.assert_called_once_with('local-model', local_files_only=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
