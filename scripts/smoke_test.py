"""Offline checks: geometry, segmentation, pipeline and pseudo export."""
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import load_config
from src.types import WeedDetection
from src.nms import iou, nms
from src.tiling import iter_tiles
from src.exporters import normalize_bbox, image_result, save_results
from scripts.export_pseudo_yolo import export_dataset


class SmokeTests(unittest.TestCase):
    def test_imports(self):
        for path in (Path(__file__).resolve().parents[1]/'src').glob('*.py'):
            importlib.import_module('src.'+path.stem)

    def test_geometry(self):
        a = WeedDetection(0, 'Бодяк', 'Розетка', .9, 0, 0, 20, 20)
        b = WeedDetection(0, 'Бодяк', 'Розетка', .8, 10, 0, 30, 20)
        self.assertAlmostEqual(iou(a, b), 1/3)
        self.assertEqual(len(nms([a, b], .3)), 1)
        self.assertEqual(len(nms([a, b], .4)), 2)
        self.assertEqual(normalize_bbox(dict(x1=10, y1=20, x2=30, y2=60), 100, 100), (.2, .4, .2, .4))
        with self.assertRaises(ValueError):
            normalize_bbox(dict(x1=-1, y1=0, x2=30, y2=60), 100, 100)

    def test_tiles(self):
        image = Image.new('RGB', (233, 177))
        coverage = Image.new('1', image.size)
        draw = ImageDraw.Draw(coverage)
        for tile in iter_tiles(image, 100, .2):
            draw.rectangle((tile.offset_x, tile.offset_y, tile.offset_x+tile.width-1, tile.offset_y+tile.height-1), fill=1)
            self.assertEqual(tile.image.size, (tile.width, tile.height))
        self.assertEqual(coverage.getextrema(), (1, 1))
        self.assertEqual(len(list(iter_tiles(Image.new('RGB', (20, 30)), 100, 0))), 1)
        with self.assertRaises(ValueError):
            list(iter_tiles(image, 100, 1))

    def test_counts(self):
        result = image_result('тест.jpg', 30, 30, [WeedDetection(1, 'unknown', 'unknown', .1, 0, 0, 20, 20)])
        self.assertEqual(result['unknown_count'], 1)
        self.assertEqual(result['total_weeds'], 0)
        json.dumps(result, allow_nan=False)

    def test_export_and_exif(self):
        config = load_config()
        self.assertEqual(config['model']['name'], 'facebook/dinov2-small')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new('RGB', (200, 160), (90, 60, 40))
            exif = Image.Exif()
            exif[274] = 6
            image.save(root/'поворот.jpg', exif=exif)
            result = image_result('поворот.jpg', 160, 200, [
                WeedDetection(1, 'Бодяк', 'Розетка', .9, 10, 20, 50, 60),
                WeedDetection(2, 'unknown', 'unknown', .8, 50, 60, 70, 90)])
            save_results([result], root/'results')
            self.assertEqual(export_dataset(root/'results/results.json', root/'поворот.jpg', root/'pseudo'), 1)
            with Image.open(root/'pseudo/images/000000.png') as exported:
                self.assertEqual(exported.size, (160, 200))
            lines = (root/'pseudo/labels/000000.txt').read_text().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual([float(v) for v in lines[0].split()[1:]], [.1875, .2, .25, .2])
            self.assertTrue((root/'results/results.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
            with self.assertRaises(ValueError):
                export_dataset(root/'results/results.json', root/'поворот.jpg', root/'pseudo')

    def test_pipeline_and_export(self):
        from src.inference import run_inference
        class FakeModel:
            batch_size = 2
            def encode(self, images):
                return images
        class FakeClassifier:
            def classify(self, images):
                return [('Бодяк полевой', 'Розетка', .85) for _ in images]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = root/'ФотоПолей'
            inputs.mkdir()
            image = Image.new('RGB', (200, 160), (90, 60, 40))
            ImageDraw.Draw(image).rectangle((40, 50, 70, 90), fill=(30, 180, 30))
            image.save(inputs/'тест.png')
            config = load_config()
            config['tiling'] = {'tile_size': 128, 'overlap': .5}
            output = root/'outputs'
            results = run_inference(inputs, output, config, FakeModel(), FakeClassifier(), True)
            self.assertEqual(results[0]['total_weeds'], 1)
            self.assertEqual(Image.open(output/'annotated/тест.png.png').size, image.size)
            self.assertTrue((output/'results.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertLessEqual(len(list((output/'debug').glob('*/tile.png'))), config['debug']['max_tiles'])
            self.assertEqual(export_dataset(output/'results.json', inputs, root/'pseudo'), 1)
            label = (root/'pseudo/labels/000000.txt').read_text().split()
            self.assertEqual(label[0], '0')
            self.assertTrue(all(0 <= float(v) <= 1 for v in label[1:]))
            with self.assertRaises(ValueError):
                export_dataset(output/'results.json', inputs, root/'pseudo')
            # EXIF rotation is materialized in pseudo images.
            exif = Image.Exif()
            exif[274] = 6
            image.save(root/'rotated.jpg', exif=exif)
            result = image_result('rotated.jpg', 160, 200, [WeedDetection(1, 'Бодяк', 'Розетка', .9, 10, 20, 50, 60)])
            save_results([result], root/'rotated_results')
            export_dataset(root/'rotated_results/results.json', root/'rotated.jpg', root/'rotated_pseudo')
            self.assertEqual(Image.open(root/'rotated_pseudo/images/000000.png').size, (160, 200))


if __name__ == '__main__':
    unittest.main(verbosity=2)
