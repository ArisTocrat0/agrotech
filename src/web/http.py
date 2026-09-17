"""HTTP transport; business operations are delegated to services."""
"""Local dashboard. Run: python web_app.py."""
import argparse
import json
import logging
import math
import re
import tempfile
import zipfile
from io import BytesIO
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
MAX_UPLOAD = 100 * 1024 * 1024


from .service import Dashboard

def make_handler(app: Dashboard):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body: bytes, content_type: str, download: str = ''):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def json(self, status: int, value):
            self.send(status, json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path in {'/api/training', '/api/training/weights'}:
                    from scripts.train_yolo import training_status, TRAINING
                    state = training_status()
                    if path.endswith('/weights'):
                        if not state.get('weights_ready'):
                            raise ValueError('Веса ещё не сохранены.')
                        self.send(200, (TRAINING / state['run'] / 'weights' / 'best.pt').read_bytes(),
                                  'application/octet-stream', 'yolo11n-trial-best.pt')
                    else:
                        self.json(200, state)
                    return
                if path == '/api/crop-import':
                    self.json(200,app.import_status())
                    return
                if path == '/api/references':
                    self.json(200, app.references())
                    return
                if path == '/api/check':
                    self.json(200, app.check_status())
                    return
                if path == '/api/jobs':
                    with app.lock:
                        self.json(200, app.history())
                    return
                if path.startswith('/api/jobs/'):
                    parts = path.split('/')
                    folder = app.directory(parts[3])
                    action = parts[4] if len(parts) > 4 else ''
                    if action == 'log':
                        self.json(200, {'log': app.log_tail(folder / 'analysis.log')})
                        return
                    if action in {'archive', 'pseudo'}:
                        self.send(200, app.archive(parts[3], action == 'pseudo'), 'application/zip', action + '.zip')
                        return
                    if action in {'results', 'json', 'csv'}:
                        from ..application.review import load_results
                        from ..infrastructure.exporters import save_results
                        with app.lock:
                            rows = load_results(folder)
                        if action in {'results','json'}:
                            self.send(200,json.dumps(rows,ensure_ascii=False).encode(),'application/json; charset=utf-8',
                                      'results.json' if action == 'json' else '')
                        else:
                            with tempfile.TemporaryDirectory() as temporary:
                                save_results(rows,Path(temporary))
                                self.send(200,(Path(temporary)/'results.csv').read_bytes(),'text/csv; charset=utf-8','results.csv')
                        return
                    if action == 'source' and len(parts) == 6:
                        from ..vision.image_utils import load_image_rgb
                        rows = json.loads((folder/'results.json').read_text(encoding='utf-8'))
                        index = int(parts[5])
                        if not 0 <= index < len(rows):
                            raise ValueError('Изображение не найдено')
                        base = (folder/'input').resolve()
                        image = (base/rows[index]['image']).resolve()
                        if not image.is_relative_to(base):
                            raise ValueError('Некорректный путь')
                        if image.exists():
                            data = BytesIO()
                            load_image_rgb(image).save(data,format='JPEG',quality=92)
                            self.send(200,data.getvalue(),'image/jpeg')
                        else:
                            base = (folder/'annotated').resolve()
                            image = (base/(rows[index]['image']+'.png')).resolve()
                            if not image.is_relative_to(base):
                                raise ValueError('Некорректный путь')
                            self.send(200,image.read_bytes(),'image/png')
                        return
                    if action == 'image' and len(parts) == 6:
                        rows = json.loads((folder/'results.json').read_text(encoding='utf-8'))
                        index = int(parts[5])
                        if not 0 <= index < len(rows):
                            raise ValueError('Изображение не найдено')
                        base = (folder/'annotated').resolve()
                        image = (base/(rows[index]['image']+'.png')).resolve()
                        if not image.is_relative_to(base):
                            raise ValueError('Некорректный путь')
                        self.send(200, image.read_bytes(), 'image/png')
                        return
                assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                          '/review.js': ('review.js', 'text/javascript; charset=utf-8'),
                          '/i18n.js': ('i18n.js', 'text/javascript; charset=utf-8'),
                          '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if path in assets:
                    name, mime = assets[path]
                    self.send(200, (ROOT/'web'/name).read_bytes(), mime)
                else:
                    self.json(404, {'error': 'Не найдено'})
            except (OSError, ValueError, IndexError, KeyError) as exc:
                self.json(404, {'error': str(exc)})

        def do_POST(self):
            path = urlparse(self.path).path
            is_review = bool(re.fullmatch(r'/api/jobs/(?:[a-f0-9]{32}|cli)/(?:review|geometry)',path))
            if not is_review and path not in {'/api/analyze', '/api/references', '/api/check', '/api/training', '/api/training/full', '/api/crop-import'}:
                self.json(404, {'error': 'Не найдено'})
                return
            # Only the local dashboard can submit work; reject cross-origin forms.
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{self.headers.get("Host")}':
                self.json(403, {'error': 'Запрос с другого сайта запрещён'})
                return
            try:
                if path == '/api/crop-import':
                    self.json(202,app.start_import())
                    return
                if is_review:
                    from ..application.review import save_decision, save_geometry
                    size = int(self.headers.get('Content-Length','0'))
                    if not 0 < size <= 4096:
                        raise ValueError('Некорректный размер решения')
                    data = json.loads(self.rfile.read(size))
                    with app.lock:
                        folder = app.directory(path.split('/')[3])
                        if path.endswith('/geometry'):
                            rows = save_geometry(folder,int(data['image']),float(data['gsd_cm']) if data.get('gsd_cm') else None)
                        else:
                            rows = save_decision(folder,int(data['image']),int(data['detection']),data['decision'])
                    self.json(200,rows)
                    return
                if path in {'/api/training','/api/training/full'}:
                    from scripts.train_yolo import start_training, start_full_training, training_status
                    (start_full_training if path.endswith('/full') else start_training)()
                    self.json(202, training_status())
                    return
                if path == '/api/check':
                    self.json(202, app.start_check())
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_UPLOAD:
                    raise ValueError('Общий размер загрузки должен быть не больше 100 МБ.')
                content_type = self.headers.get('Content-Type', '')
                if not content_type.startswith('multipart/form-data;'):
                    raise ValueError('Ожидаются фотографии в форме загрузки.')
                body = self.rfile.read(size)
                message = BytesParser(policy=default).parsebytes(
                    f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n'.encode()+body)
                files = [(part.get_filename(), part.get_payload(decode=True)) for part in message.iter_parts()
                         if part.get_filename() and part.get_param('name', header='content-disposition') == 'files']
                fields = {part.get_param('name', header='content-disposition'):
                          part.get_payload(decode=True).decode('utf-8') for part in message.iter_parts()
                          if not part.get_filename() and part.get_param('name', header='content-disposition')}
                if path == '/api/references':
                    self.json(201, app.add_references(fields.get('species', ''), fields.get('stage', ''), files, fields.get('kind','weed')))
                else:
                    self.json(202, {'id': app.start(files, fields)})
            except (ValueError, TypeError, KeyError) as exc:
                self.json(400, {'error': str(exc)})
            except Exception:
                logging.exception('Cannot start analysis')
                self.json(500, {'error': 'Не удалось выполнить действие. Проверьте систему на вкладке «Подготовка».'})
    return Handler

