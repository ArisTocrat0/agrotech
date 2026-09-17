"""NMS ordering, class boundaries and optional native backend contracts."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.domain.types import WeedDetection
from src.vision.nms import kernel, nms


class NmsTests(unittest.TestCase):
    def test_backend_contract(self):
        with self.assertRaises(ValueError):
            nms([], backend='typo')
        for threshold in [-1, 2, float('nan')]:
            with self.assertRaises(ValueError):
                nms([], threshold)
        with patch('src.vision.nms.kernel', return_value=None):
            self.assertEqual(nms([]), [])
            with self.assertRaises(RuntimeError):
                nms([], backend='cpp')

    def test_order_classes_and_threshold_boundary(self):
        backends = ['python'] + (['cpp'] if kernel() else [])
        for backend in backends:
            with self.subTest(backend=backend):
                boxes = [WeedDetection(i, species, stage, .8, 0, 0, 10, 10)
                         for i, (species, stage) in enumerate([
                             ('wheat', 'seedling'), ('wheat', 'seedling'),
                             ('barley', 'seedling'), ('wheat', 'mature')])]
                result = nms(boxes, 0, backend)
                self.assertEqual([id(d) for d in result], [id(boxes[i]) for i in [0, 2, 3]])
                self.assertEqual([d.id for d in result], [1, 2, 3])
                self.assertEqual(len(nms(boxes, 1, backend)), 4)
                self.assertEqual(nms([], backend=backend), [])
                # IoU is exactly 0.5: suppression must use >, not >=.
                pair = [WeedDetection(0, 'wheat', 'seedling', .9, 0, 0, 10, 10),
                        WeedDetection(1, 'wheat', 'seedling', .8, 0, 0, 5, 10)]
                self.assertEqual(len(nms(pair, .5, backend)), 2)
                self.assertEqual(len(nms(pair, .49, backend)), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
