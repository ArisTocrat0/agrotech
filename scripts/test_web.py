"""Dashboard integration tests without downloading model weights."""
import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_app import Dashboard, make_handler
from src.exporters import image_result, save_results
from src.types import WeedDetection


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Dashboard(self.root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def get(self, path):
        return urlopen(self.url+path)

    def test_assets_and_empty_history(self):
        for path in ['/', '/app.js', '/i18n.js', '/style.css']:
            with self.get(path) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 100)
        with self.get('/api/jobs') as response:
            self.assertEqual(json.load(response), [])
        with self.assertRaises(HTTPError):
            self.get('/../../../etc/passwd')

    def test_downloads_and_image(self):
        output = self.root/'outputs'
        save_results([image_result('поле.jpg', 100, 100, [
            WeedDetection(1, 'Бодяк', 'Розетка', .8, 1, 2, 30, 40)])], output)
        (output/'annotated').mkdir()
        Image.new('RGB', (100, 100)).save(output/'annotated/поле.jpg.png')
        with self.get('/api/jobs') as response:
            self.assertEqual(json.load(response)[0]['id'], 'cli')
        with self.get('/api/jobs/cli/json') as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertEqual(json.load(response)[0]['total_weeds'], 1)
        with self.get('/api/jobs/cli/csv') as response:
            self.assertTrue(response.read().startswith(b'\xef\xbb\xbf'))
        with self.get('/api/jobs/cli/image/0') as response:
            self.assertEqual(response.headers['Content-Type'], 'image/png')
        with self.assertRaises(HTTPError):
            self.get('/api/jobs/cli/image/-1')

    def test_upload_lifecycle_and_guard(self):
        reference = self.root/'data/Сорняки/Бодяк/Розетка'
        reference.mkdir(parents=True)
        Image.new('RGB',(20,20)).save(reference/'ref.jpg')
        image = io.BytesIO()
        Image.new('RGB',(20,20)).save(image, format='PNG')
        body = b'--BOUNDARY\r\nContent-Disposition: form-data; name="files"; filename="field.png"\r\nContent-Type: image/png\r\n\r\n'+image.getvalue()+b'\r\n--BOUNDARY--\r\n'
        request = Request(self.url+'/api/analyze', data=body, headers={'Content-Type':'multipart/form-data; boundary=BOUNDARY','Origin':self.url})
        process = Mock()
        process.poll.return_value = None
        with patch('web_app.subprocess.Popen', return_value=process):
            with urlopen(request) as response:
                self.assertEqual(response.status, 202)
                job_id = json.load(response)['id']
            self.assertTrue((self.app.directory(job_id)/'input/01_field.png').exists())
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 400)
            process.poll.return_value = 0
            process.returncode = 0
            self.assertEqual(self.app.history()[0]['status'], 'done')
        request.add_header('Origin','http://other.example')
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_missing_references_and_invalid_ids(self):
        with self.assertRaisesRegex(ValueError, 'эталоны'):
            self.app.start([('photo.png', b'bad')])
        with self.assertRaises(ValueError):
            self.app.directory('../outside')


class JobTests(unittest.TestCase):
    @staticmethod
    def photo():
        raw = io.BytesIO()
        Image.new('RGB', (30, 30)).save(raw, format='PNG')
        return raw.getvalue()

    def test_reference_upload_validation_and_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Dashboard(Path(folder))
            image = self.photo()
            rows = app.add_references('Бодяк', 'Розетка', [('same.png', image)])
            self.assertEqual(rows, [{'species':'Бодяк', 'stage':'Розетка', 'count':1}])
            app.add_references('Бодяк', 'Розетка', [('same.png', image)])
            self.assertEqual(app.references()[0]['count'], 2)
            for species in ['../escape', '..', 'bad/name', 'bad\\name', '']:
                with self.assertRaises(ValueError):
                    app.add_references(species, 'stage', [('ref.png', image)])
            with self.assertRaises(ValueError):
                app.add_references('Вид', 'Стадия', [('valid.png', image), ('bad.png', b'bad')])
            self.assertEqual(len(app.references()), 1)
            process = Mock()
            process.poll.return_value = None
            app.processes['active'] = process
            with self.assertRaisesRegex(ValueError, 'уже выполняется'):
                app.add_references('Вид', 'Стадия', [('ref.png', image)])

    def test_analysis_options_are_validated_and_passed_to_process(self):
        for fields in [{'overlap':'nan'}, {'overlap':'1'}, {'tile_size':'0'},
                       {'batch_size':'129'}, {'similarity_threshold':'inf'}, {'device':'cpu; ls'}]:
            with self.assertRaises(ValueError):
                Dashboard.options(fields)
        with tempfile.TemporaryDirectory() as folder:
            app = Dashboard(Path(folder))
            app.add_references('Бодяк', 'Розетка', [('ref.png', self.photo())])
            process = Mock()
            process.poll.return_value = None
            fields = {'device':'cpu', 'tile_size':'512', 'overlap':'0.3',
                      'similarity_threshold':'0.7', 'batch_size':'4', 'debug':'true'}
            with patch('web_app.subprocess.Popen', return_value=process) as spawn:
                job = app.start([('field.png', self.photo())], fields)
            command = spawn.call_args.args[0]
            for flag, value in [('--device','cpu'), ('--tile-size','512'), ('--batch-size','4')]:
                self.assertEqual(command[command.index(flag)+1], value)
            self.assertIn('--debug', command)
            metadata = json.loads((app.directory(job)/'job.json').read_text())
            self.assertEqual(metadata['options']['similarity_threshold'], .7)

    def test_system_check_status_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Dashboard(Path(folder))
            self.assertEqual(app.check_status()['status'], 'idle')
            process = Mock()
            process.poll.return_value = None
            with patch('web_app.subprocess.Popen', return_value=process) as spawn:
                self.assertEqual(app.start_check()['status'], 'running')
                app.start_check()
                self.assertEqual(spawn.call_count, 1)
            app.check_log.write_text('OK')
            process.poll.return_value = 0
            self.assertEqual(app.check_status(), {'status':'done', 'log':'OK'})
            process.poll.return_value = 1
            self.assertEqual(app.check_status()['status'], 'error')

    def test_archives_include_results_and_portable_pseudo_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Dashboard(Path(temporary))
            folder = app.directory('a'*32)
            (folder/'input').mkdir(parents=True)
            (folder/'input/field.png').write_bytes(self.photo())
            save_results([image_result('field.png', 30, 30, [
                WeedDetection(1, 'Бодяк', 'Розетка', .8, 1, 2, 20, 25)])], folder)
            (folder/'annotated').mkdir()
            (folder/'annotated/field.png.png').write_bytes(self.photo())
            (folder/'analysis.log').write_text('completed')
            with zipfile.ZipFile(io.BytesIO(app.archive('a'*32))) as archive:
                self.assertIn('annotated/field.png.png', archive.namelist())
                self.assertIn('results.csv', archive.namelist())
                self.assertNotIn('input/field.png', archive.namelist())
            with zipfile.ZipFile(io.BytesIO(app.archive('a'*32, pseudo=True))) as archive:
                self.assertIn('labels/000000.txt', archive.namelist())
                self.assertNotIn('path:', archive.read('dataset.yaml').decode())
            save_results([image_result('field.png', 30, 30, [])], folder)
            with self.assertRaisesRegex(ValueError, 'Нет подходящих'):
                app.archive('a'*32, pseudo=True)

    def test_validation_lifecycle_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = Dashboard(root)
            self.assertEqual(app.history(), [])
            with self.assertRaisesRegex(ValueError, 'эталоны'):
                app.start([])
            reference = root/'data/Сорняки/Бодяк/Розетка'
            reference.mkdir(parents=True)
            Image.new('RGB', (20,20)).save(reference/'ref.png')
            with self.assertRaisesRegex(ValueError, 'от 1 до 20'):
                app.start([])
            with self.assertRaisesRegex(ValueError, 'прочитать'):
                app.start([('bad.jpg', b'bad')])
            with self.assertRaises(ValueError):
                app.directory('../escape')
            raw = io.BytesIO()
            Image.new('RGB', (20,20)).save(raw, format='PNG')
            process = Mock()
            process.poll.return_value = None
            with patch('web_app.subprocess.Popen', return_value=process) as spawn:
                job_id = app.start([('../../field.png', raw.getvalue())])
                self.assertTrue((app.directory(job_id)/'input/01_field.png').exists())
                self.assertEqual(app.history()[0]['status'], 'running')
                self.assertIn('--references', spawn.call_args.args[0])
                with self.assertRaisesRegex(ValueError, 'уже выполняется'):
                    app.start([('field.png', raw.getvalue())])
                process.poll.return_value = 1
                process.returncode = 1
                (app.directory(job_id)/'analysis.log').write_text('Model unavailable')
                self.assertEqual(app.history()[0]['error'], 'Model unavailable')
                next_process = Mock()
                next_process.poll.return_value = None
                spawn.return_value = next_process
                next_job = app.start([('field.png', raw.getvalue())])
                restarted = Dashboard(root)
                rows = {row['id']: row for row in restarted.history()}
                self.assertEqual(rows[next_job]['status'], 'error')
                self.assertIn('перезапущен', rows[next_job]['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
