"""Offline contract/fixture tests. These do NOT measure real detection accuracy."""
import io
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.environment import assistant, media, model, pipeline
from src.web.http import make_handler
from src.web.service import Dashboard


def png():
    buffer = io.BytesIO()
    Image.new('RGB', (64, 48), 'black').save(buffer, format='PNG')
    return buffer.getvalue()


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = Dashboard(self.root)
        self.weights = self.root / 'test-only-not-real.pt'
        self.weights.write_bytes(b'fixture - not a trained model')
        self.env = {'AGRO_ENV_MODEL': str(self.weights), 'AGRO_ENV_CLASS_MAP': '{"fire":"fire","smoke":"smoke","trash":"trash"}'}

    def tearDown(self):
        self.temporary.cleanup()

    def test_no_model_is_explicit_and_keeps_no_upload(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.app.environment.status()['status'], 'model_not_configured')
            with self.assertRaises(model.ModelNotConfigured):
                self.app.environment.start([('a.png', png())], {})
        self.assertFalse(self.app.environment.jobs.exists())

    def test_model_configuration_rejects_remote_missing_and_bad_map(self):
        for changes in [{'AGRO_ENV_MODEL': 'https://example.invalid/model.pt'}, {'AGRO_ENV_MODEL': '/absent.pt'},
                        {'AGRO_ENV_CLASS_MAP': '{}'}, {'AGRO_ENV_CLASS_MAP': '[]'},
                        {'AGRO_ENV_CLASS_MAP': '{"person":"person"}'}, {'AGRO_ENV_CLASS_MAP': 'oops'}]:
            self.assertEqual(model.status(self.env | changes)['status'], 'configuration_error')
        self.assertEqual(model.status(self.env)['status'], 'configured')

    def test_adapter_rejects_incompatible_taxonomy_and_task(self):
        for names, task in [({0: 'person'}, 'detect'), ({0: 'trash', 1: 'fire', 2: 'smoke'}, 'classify')]:
            fake = types.ModuleType('ultralytics')
            fake.YOLO = Mock(return_value=Mock(names=names, task=task))
            with patch.dict(sys.modules, {'ultralytics': fake}), self.assertRaises(ValueError):
                model.LocalYoloDetector(environ=self.env)
            fake.YOLO.assert_called_once_with(str(self.weights), task='detect')

    def test_adapter_explicit_local_path_no_download_fallback(self):
        fake = types.ModuleType('ultralytics')
        predictor = Mock(names={0: 'fire', 1: 'smoke', 2: 'trash'}, task='detect')
        predictor.predict.return_value = [types.SimpleNamespace(boxes=None, orig_shape=(4, 4))]
        fake.YOLO = Mock(return_value=predictor)
        with patch.dict(sys.modules, {'ultralytics': fake}):
            detector = model.LocalYoloDetector(environ=self.env)
            self.assertEqual(detector.detect(Image.new('RGB', (4, 4))), [])
        self.assertEqual(predictor.predict.call_args.kwargs['device'], 'cpu')
        self.assertEqual(len(detector.metadata['weights_sha256']), 64)

    def test_adapter_rejects_malformed_results_and_class_ids(self):
        fake = types.ModuleType('ultralytics')
        predictor = Mock(names={0: 'fire', 1: 'smoke', 2: 'trash'}, task='detect')
        fake.YOLO = Mock(return_value=predictor)
        image = Image.new('RGB', (4, 4))
        with patch.dict(sys.modules, {'ultralytics': fake}):
            detector = model.LocalYoloDetector(environ=self.env)
            for outputs in [[], [None, None], [types.SimpleNamespace(orig_shape=(5, 4), boxes=None)]]:
                predictor.predict.return_value = outputs
                with self.assertRaises(ValueError):
                    detector.detect(image)
            for value in [.8, float('nan'), float('inf'), -1, 3, True]:
                box = Mock()
                box.cls.item.return_value = value
                predictor.predict.return_value = [types.SimpleNamespace(orig_shape=(4, 4), boxes=[box], names=predictor.names)]
                with self.assertRaises(ValueError):
                    detector.detect(image)

    def test_geodata_no_defaults_and_valid_zero(self):
        rows = [{'source_name': 'a.png', 'kind': 'image'}]
        self.assertEqual(media.validate_geodata({}, rows), {})
        points = media.validate_geodata({'a.png': {'latitude': 0, 'longitude': 0, 'source': 'operator_capture_position'}}, rows)
        self.assertEqual(points['a.png']['latitude'], 0)
        self.assertEqual(points['a.png']['precision'], 'capture_position_not_object')

    def test_geodata_invalid_and_nonfinite_are_rejected(self):
        rows = [{'source_name': 'a.png', 'kind': 'image'}]
        for value in [float('nan'), float('inf'), 91, True, None]:
            with self.assertRaises(ValueError):
                media.validate_geodata({'a.png': {'latitude': value, 'longitude': 1, 'source': 'operator_capture_position'}}, rows)
        with self.assertRaises(ValueError):
            media.validate_geodata({'unknown.png': {}}, rows)

    def test_photo_bounds_and_actual_type(self):
        self.assertEqual(media.load_photo(io.BytesIO(png())).size, (64, 48))
        with self.assertRaises(ValueError):
            media.load_photo(io.BytesIO(b'not image'))
        gif = io.BytesIO()
        Image.new('RGB', (4, 4)).save(gif, format='GIF')
        with self.assertRaises(ValueError):
            media.load_photo(io.BytesIO(gif.getvalue()))
        with self.assertRaises(ValueError):
            media.dimensions(8001, 1)
        with self.assertRaises(ValueError):
            media.dimensions(6000, 6000)

    def test_animated_png_is_not_accepted_as_photo(self):
        buffer = io.BytesIO()
        Image.new('RGB', (4, 4), 'black').save(buffer, format='PNG', save_all=True,
                                             append_images=[Image.new('RGB', (4, 4), 'white')], duration=100)
        with self.assertRaisesRegex(ValueError, 'анимированный'):
            media.load_photo(io.BytesIO(buffer.getvalue()))

    def test_exif_capture_gps_and_orientation(self):
        photo = Image.new('RGB', (64, 48))
        exif = Image.Exif()
        exif[274] = 6
        exif[34853] = {1: 'N', 2: (50, 30, 0), 3: 'E', 4: (60, 15, 0)}
        buffer = io.BytesIO()
        photo.save(buffer, format='JPEG', exif=exif)
        result = media.exif_capture_location(buffer.getvalue())
        self.assertEqual(result['latitude'], 50.5)
        self.assertEqual(result['longitude'], 60.25)
        self.assertEqual(result['source'], 'embedded_gps_capture_position')
        self.assertEqual(media.load_photo(io.BytesIO(buffer.getvalue())).size, (48, 64))
        self.assertIsNone(media.exif_capture_location(png()))

    def manifest(self):
        folder = self.root / ('a' * 32)
        (folder / 'input').mkdir(parents=True)
        (folder / 'input/00.png').write_bytes(png())
        return folder, {'id': 'a' * 32, 'media': [{'index': 0, 'source_name': 'fixture.png', 'stored_name': '00.png', 'kind': 'image'}],
                        'options': {'confidence': .35}, 'geodata': {}}

    def test_fixture_detection_retains_evidence_and_null_geometry(self):
        folder, manifest = self.manifest()
        detector = Mock(metadata={'backend': 'TEST FIXTURE ONLY'})
        detector.detect.return_value = [{'class_name': 'fire', 'confidence': .8, 'bbox': [1, 2, 20, 30]},
                                       {'class_name': 'trash', 'confidence': .1, 'bbox': [2, 2, 10, 10]}]
        result = pipeline.analyze(folder, manifest, detector)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['events']), 1)
        self.assertIsNone(result['events'][0]['location'])
        self.assertEqual(result['events'][0]['review_status'], 'unreviewed')
        self.assertTrue((folder / 'evidence/00_00000000.jpg').exists())
        self.assertTrue((folder / 'evidence/00_00000000_annotated.jpg').exists())
        self.assertIsNone(json.loads((folder / 'events.geojson').read_text())['features'][0]['geometry'])

    def test_no_detections_retains_photo_and_warning(self):
        folder, manifest = self.manifest()
        detector = Mock(metadata={'backend': 'TEST FIXTURE ONLY'})
        detector.detect.return_value = []
        result = pipeline.analyze(folder, manifest, detector)
        self.assertEqual(result['events'], [])
        self.assertIn('не доказывает безопасность', result['warnings'][0])
        self.assertTrue((folder / 'evidence/00_00000000.jpg').exists())

    def test_nonfinite_model_output_and_bad_bbox_fail_closed(self):
        for row in [{'class_name': 'person', 'confidence': .5, 'bbox': [1, 1, 2, 2]},
                    {'class_name': 'fire', 'confidence': float('nan'), 'bbox': [1, 1, 2, 2]},
                    {'class_name': 'fire', 'confidence': .5, 'bbox': [-1, 1, 2, 2]}]:
            with self.assertRaises(ValueError):
                pipeline.validated_detection(row, 64, 48, .35)

    def test_geojson_has_capture_provenance(self):
        event = {'id': 'x', 'class_name': 'trash', 'confidence': .6, 'source_name': 'x', 'timestamp_seconds': None,
                 'review_status': 'unreviewed', 'possible_duplicate_of': None,
                 'location': {'latitude': 50, 'longitude': 60, 'source': 'operator_capture_position', 'precision': 'capture_position_not_object'}}
        feature = pipeline.geojson([event])['features'][0]
        self.assertEqual(feature['geometry']['coordinates'], [60, 50])
        self.assertEqual(feature['properties']['geometry_role'], 'capture_position_not_object')

    def test_all_failures_never_report_success(self):
        folder, manifest = self.manifest()
        detector = Mock(metadata={'backend': 'TEST ONLY'})
        detector.detect.side_effect = RuntimeError('fixture inference failure')
        with self.assertRaisesRegex(ValueError, 'Ни одно'):
            pipeline.analyze(folder, manifest, detector)
        self.assertEqual(json.loads((folder / 'results.json').read_text())['status'], 'partial')

    def test_partial_failure_retains_success_without_hiding_error(self):
        folder, manifest = self.manifest()
        (folder / 'input/01.png').write_bytes(b'broken photo')
        manifest['media'].append({'index': 1, 'source_name': 'bad.png', 'stored_name': '01.png', 'kind': 'image'})
        detector = Mock(metadata={'backend': 'TEST ONLY'})
        detector.detect.return_value = []
        result = pipeline.analyze(folder, manifest, detector)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['media'][0]['frames_analyzed'], 1)
        self.assertEqual(result['media'][1]['frames_analyzed'], 0)

    def test_global_timeout_stops_all_remaining_photos(self):
        folder, manifest = self.manifest()
        (folder / 'input/01.png').write_bytes(png())
        manifest['media'].append({'index': 1, 'source_name': 'second.png', 'stored_name': '01.png', 'kind': 'image'})
        detector = Mock(metadata={'backend': 'TEST ONLY'})
        detector.detect.side_effect = TimeoutError('global deadline')
        with self.assertRaises(TimeoutError):
            pipeline.analyze(folder, manifest, detector)
        self.assertEqual(detector.detect.call_count, 1)
        self.assertEqual(json.loads((folder / 'results.json').read_text())['status'], 'partial')

    def test_upload_validation_and_safe_stored_names(self):
        process = Mock()
        process.poll.return_value = None
        with patch.dict(os.environ, self.env, clear=True), patch('src.web.environment.subprocess.Popen', return_value=process):
            for fields in [{'confidence': 'nan'}, {'confidence': '-1'}, {'latitude': '90.1', 'longitude': '1'}]:
                with self.assertRaises(ValueError):
                    self.app.environment.start([('a.png', png())], fields)
            with self.assertRaises(ValueError):
                self.app.environment.start([('a.png', png()), ('a.png', png())], {})
            with self.assertRaises(ValueError):
                self.app.environment.start([('a.mp4', b'video')], {})
            job_id = self.app.environment.start([('../../evil.png', png())], {})
            folder = self.app.environment.directory(job_id)
            self.assertTrue((folder / 'input/00.png').exists())
            self.assertFalse((self.root / 'evil.png').exists())
            self.assertEqual(json.loads((folder / 'manifest.json').read_text())['media'][0]['source_name'], 'evil.png')
            with self.assertRaises(ValueError):
                self.app.environment.start([('another.png', png())], {})
            process.poll.return_value = 1
            process.returncode = 1
            self.assertEqual(self.app.environment.job(job_id)['status'], 'error')

    def test_file_allowlist_blocks_input_and_traversal(self):
        for job_id, relative in [('x', 'events.geojson'), ('a' * 32, '../outside'), ('a' * 32, 'input/00.png')]:
            with self.assertRaises(ValueError):
                self.app.environment.file(job_id, relative)

    def test_assistant_off_by_default_and_rejects_uuid_identity(self):
        self.assertEqual(assistant.status({})['status'], 'not_configured')
        for env in [{'AGRO_ENV_AGROMIND_URL': 'http://example.invalid/v2', 'AGRO_ENV_AGROMIND_USER_ID': '1'},
                    {'AGRO_ENV_AGROMIND_URL': 'https://example.invalid/v2', 'AGRO_ENV_AGROMIND_USER_ID': 'uuid'},
                    {'AGRO_ENV_AGROMIND_URL': 'https://user:password@example.invalid/v2', 'AGRO_ENV_AGROMIND_USER_ID': '1'}]:
            with self.assertRaises(ValueError):
                assistant.configuration(env)

    def test_assistant_contract_and_consent_no_network(self):
        event = {'id': 'b' * 32, 'class_name': 'fire', 'confidence': .6, 'bbox': [1, 1, 2, 2],
                 'frame_index': 0, 'timestamp_seconds': None, 'review_status': 'unreviewed',
                 'possible_duplicate_of': None, 'location': None}
        payload = assistant.payload(event, 'Explain', 42)
        self.assertEqual(payload['schema_version'], 2)
        self.assertEqual(payload['user_id'], 42)
        self.assertIsNone(payload['sessionId'])
        self.assertEqual(payload['context']['location'], {'scope': 'unknown', 'point': None})
        self.assertNotIn('image', payload)
        self.assertNotIn('source_name', payload['context']['drone_observation'])
        with patch('src.environment.assistant.build_opener') as opener:
            with self.assertRaises(ValueError):
                assistant.ask(self.app.environment, {'consent': False})
            opener.assert_not_called()

    def test_assistant_recipient_change_fails_before_network(self):
        env = {'AGRO_ENV_AGROMIND_URL': 'https://new.invalid/v2', 'AGRO_ENV_AGROMIND_USER_ID': '42'}
        with patch.dict(os.environ, env, clear=True), patch('src.environment.assistant.build_opener') as opener:
            with self.assertRaisesRegex(ValueError, 'Получатель'):
                assistant.ask(self.app.environment, {'consent': True, 'expected_endpoint_host': 'old.invalid'})
            opener.assert_not_called()

    def test_assistant_request_exact_contract_without_live_call(self):
        event = {'id': 'event', 'class_name': 'trash', 'confidence': .6, 'bbox': [1, 1, 2, 2], 'frame_index': 0,
                 'timestamp_seconds': None, 'review_status': 'unreviewed', 'possible_duplicate_of': None, 'location': None}
        environment = Mock()
        environment.job.return_value = {'id': 'a' * 32, 'status': 'done', 'result': {'events': [event]}}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"response":"advisory"}'
        opener = Mock()
        opener.open.return_value = response
        env = {'AGRO_ENV_AGROMIND_URL': 'https://example.invalid/agromind-v2', 'AGRO_ENV_AGROMIND_USER_ID': '42'}
        with patch.dict(os.environ, env, clear=True), patch('src.environment.assistant.build_opener', return_value=opener):
            answer = assistant.ask(environment, {'job_id': 'a' * 32, 'event_id': 'event', 'consent': True, 'message': 'Explain', 'expected_endpoint_host': 'example.invalid'})
        self.assertEqual(answer['response'], 'advisory')
        body = json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(body['schema_version'], 2)
        self.assertEqual(body['context']['drone_observation']['class_name'], 'trash')
        environment.file.assert_not_called()


class EnvironmentalHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Dashboard(Path(self.temp.name))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_status_and_empty_histories_are_separate(self):
        with patch.dict(os.environ, {'AGRO_ENV_MODEL': '', 'AGRO_ENV_CLASS_MAP': '', 'AGRO_ENV_AGROMIND_URL': '', 'AGRO_ENV_AGROMIND_USER_ID': ''}):
            with urlopen(self.url + '/api/environment/status') as response:
                self.assertEqual(json.load(response)['status'], 'model_not_configured')
            with urlopen(self.url + '/api/environment/jobs') as response:
                self.assertEqual(json.load(response), {'jobs': []})
            with urlopen(self.url + '/api/jobs') as response:
                self.assertEqual(json.load(response), [])
            with urlopen(self.url + '/api/environment/assistant/status') as response:
                self.assertEqual(json.load(response)['status'], 'not_configured')

    def test_origin_guard_and_missing_model_post(self):
        body = b'--X\r\nContent-Disposition: form-data; name="files"; filename="x.png"\r\nContent-Type: image/png\r\n\r\n' + png() + b'\r\n--X--\r\n'
        request = Request(self.url + '/api/environment/analyze', data=body,
                          headers={'Content-Type': 'multipart/form-data; boundary=X', 'Origin': 'https://other.invalid'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)
        request.add_header('Origin', self.url)
        with patch.dict(os.environ, {'AGRO_ENV_MODEL': '', 'AGRO_ENV_CLASS_MAP': '', 'AGRO_ENV_AGROMIND_URL': '', 'AGRO_ENV_AGROMIND_USER_ID': ''}), self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)
        self.assertIn('Модель', json.load(error.exception)['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
