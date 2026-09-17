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

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 100 * 1024 * 1024


class Dashboard:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.jobs = root / 'outputs' / 'web'
        self.lock = threading.Lock()
        self.processes = {}
        self.check_process = None
        self.check_log = self.jobs / "system-check.log"

    def close(self):
        for process in [*self.processes.values(), *([self.check_process] if self.check_process else [])]:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def directory(self, job_id: str) -> Path:
        if job_id == 'cli':
            return self.root / 'outputs'
        if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('Некорректный идентификатор анализа')
        return self.jobs / job_id

    def history(self) -> list[dict]:
        rows = []
        for path in sorted(self.jobs.glob('*/job.json'), reverse=True):
            row = json.loads(path.read_text(encoding='utf-8'))
            if row['status'] == 'running':
                process = self.processes.get(row['id'])
                if process is None:
                    row.update(status='error', error='Сервер перезапущен. Запустите анализ повторно.')
                elif process.poll() is not None:
                    row['status'] = 'done' if process.returncode == 0 else 'error'
                    if process.returncode:
                        log = path.parent / 'analysis.log'
                        row['error'] = log.read_text(encoding='utf-8', errors='replace')[-3000:]
                if row['status'] != 'running':
                    path.write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
            rows.append(row)
        cli = self.root / 'outputs' / 'results.json'
        if cli.exists():
            rows.append({'id': 'cli', 'name': 'Результаты из терминала', 'status': 'done',
                         'created': datetime.fromtimestamp(cli.stat().st_mtime, timezone.utc).isoformat()})
        return sorted(rows, key=lambda row: row['created'], reverse=True)

    @staticmethod
    def validate_images(files):
        from PIL import Image
        if not 1 <= len(files) <= 20:
            raise ValueError('Выберите от 1 до 20 фотографий.')
        if sum(len(data) for _, data in files) > MAX_UPLOAD:
            raise ValueError('Общий размер загрузки должен быть не больше 100 МБ.')
        for name, data in files:
            if Path(name).suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
                raise ValueError('Допустимы только JPG, JPEG и PNG.')
            try:
                with Image.open(BytesIO(data)) as image:
                    image.verify()
            except Exception as exc:
                raise ValueError(f'Не удалось прочитать изображение: {name}') from exc

    def references(self):
        base = self.root / 'data' / 'Сорняки'
        groups = {}
        for path in base.rglob('*'):
            if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png'}:
                parts = path.relative_to(base).parts
                if len(parts) >= 3:
                    key = parts[:2]
                    groups[key] = groups.get(key, 0) + 1
        return [{'species': key[0], 'stage': key[1], 'count': count}
                for key, count in sorted(groups.items())]

    def add_references(self, species, stage, files):
        labels = [species.strip(), stage.strip()]
        if any(not value or len(value) > 100 or value in {'.', '..'} or
               any(c in value for c in '/\\') or any(ord(c) < 32 for c in value)
               for value in labels):
            raise ValueError('Укажите вид и стадию без слешей, до 100 символов.')
        self.validate_images(files)
        with self.lock:
            if any(p.poll() is None for p in self.processes.values()):
                raise ValueError('Анализ уже выполняется. Дождитесь его завершения.')
            base = (self.root / 'data' / 'Сорняки').resolve()
            folder = base.joinpath(*labels).resolve()
            if not folder.is_relative_to(base):
                raise ValueError('Некорректный путь')
            folder.mkdir(parents=True, exist_ok=True)
            for name, data in files:
                (folder / (uuid.uuid4().hex + Path(name).suffix.lower())).write_bytes(data)
        return self.references()

    @staticmethod
    def options(fields):
        device = fields.get('device', 'auto')
        if not re.fullmatch(r'auto|cpu|cuda(?::[0-9]+)?', device):
            raise ValueError('Некорректное устройство обработки.')
        try:
            tile = int(fields.get('tile_size', '1024'))
            overlap = float(fields.get('overlap', '0.20'))
            similarity = float(fields.get('similarity_threshold', '0.55'))
            batch = int(fields.get('batch_size', '16'))
        except (TypeError, ValueError) as exc:
            raise ValueError('Проверьте числовые настройки анализа.') from exc
        if (not 128 <= tile <= 4096 or not 1 <= batch <= 128 or
                not math.isfinite(overlap) or not 0 <= overlap < 1 or
                not math.isfinite(similarity) or not -1 <= similarity <= 1):
            raise ValueError('Настройки анализа выходят за допустимые пределы.')
        return {'device': device, 'tile_size': tile, 'overlap': overlap,
                'similarity_threshold': similarity, 'batch_size': batch,
                'debug': fields.get('debug') == 'true'}

    @staticmethod
    def log_tail(path):
        if not path.exists():
            return ''
        with path.open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 24000))
            return stream.read().decode('utf-8', errors='replace')

    def check_status(self):
        process = self.check_process
        code = process.poll() if process else None
        return {'status': ('idle' if process is None else 'running' if code is None
                           else 'done' if code == 0 else 'error'),
                'log': self.log_tail(self.check_log)}

    def start_check(self):
        with self.lock:
            if self.check_process is not None and self.check_process.poll() is None:
                return self.check_status()
            self.jobs.mkdir(parents=True, exist_ok=True)
            with self.check_log.open('w') as log:
                self.check_process = subprocess.Popen(
                    [sys.executable, str(ROOT / 'scripts' / 'smoke_test.py')],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            return self.check_status()

    def archive(self, job_id, pseudo=False):
        folder = self.directory(job_id)
        if not (folder / 'results.json').exists():
            raise ValueError('Сначала дождитесь завершения анализа.')
        data = BytesIO()
        with tempfile.TemporaryDirectory() as temporary:
            source = folder
            if pseudo:
                if job_id == 'cli':
                    raise ValueError('Для экспорта YOLO запустите анализ через сайт.')
                from scripts.export_pseudo_yolo import export_dataset
                source = Path(temporary)
                try:
                    export_dataset(folder / 'results.json', folder / 'input', source)
                except ValueError as exc:
                    if str(exc).startswith('No accepted detections'):
                        raise ValueError('Нет подходящих обнаружений для разметки YOLO.') from exc
                    raise
                # A downloaded dataset must not refer to the server temporary directory.
                import yaml
                config = yaml.safe_load((source / 'dataset.yaml').read_text())
                config.pop('path', None)
                (source / 'dataset.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
            with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in source.rglob('*'):
                    relative = path.relative_to(source)
                    if path.is_file() and (pseudo or relative.parts[0] in
                            {'annotated', 'debug', 'results.json', 'results.csv', 'analysis.log'}):
                        if path.resolve().is_relative_to(source.resolve()):
                            archive.write(path, relative.as_posix())
        return data.getvalue()

    def start(self, files: list[tuple[str, bytes]], fields=None) -> str:
        options = self.options(fields or {})
        references = self.root / 'data' / 'Сорняки'
        if not any(p.suffix.lower() in {'.jpg', '.jpeg', '.png'} and len(p.relative_to(references).parts) >= 3
                   for p in references.rglob('*') if p.is_file()):
            raise ValueError('Добавьте эталоны на вкладке «Подготовка», затем повторите запуск.')
        self.validate_images(files)
        with self.lock:
            if any(p.poll() is None for p in self.processes.values()):
                raise ValueError('Анализ уже выполняется. Дождитесь его завершения.')
            job_id = uuid.uuid4().hex
            folder = self.directory(job_id)
            (folder / 'input').mkdir(parents=True)
            for index, (name, data) in enumerate(files):
                clean = Path(name.replace('\\', '/')).name
                (folder / 'input' / f'{index+1:02d}_{clean}').write_bytes(data)
            row = {'id': job_id, 'name': f'Анализ · {len(files)} фото', 'status': 'running',
                   'created': datetime.now(timezone.utc).isoformat(), 'options': options}
            with (folder / 'analysis.log').open('w') as log:
                process = subprocess.Popen([sys.executable, str(self.root/'run.py'),
                    '--references', str(references), '--input', str(folder/'input'), '--output', str(folder),
                    '--device', options['device'], '--tile-size', str(options['tile_size']),
                    '--overlap', str(options['overlap']), '--similarity-threshold', str(options['similarity_threshold']),
                    '--batch-size', str(options['batch_size']), *(['--debug'] if options['debug'] else [])],
                    cwd=self.root, stdout=log, stderr=subprocess.STDOUT)
            self.processes[job_id] = process
            (folder/'job.json').write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
            return job_id


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
                        filename = 'results.csv' if action == 'csv' else 'results.json'
                        mime = 'text/csv; charset=utf-8' if action == 'csv' else 'application/json; charset=utf-8'
                        self.send(200, (folder/filename).read_bytes(), mime, filename if action != 'results' else '')
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
            if path not in {'/api/analyze', '/api/references', '/api/check', '/api/training'}:
                self.json(404, {'error': 'Не найдено'})
                return
            # Only the local dashboard can submit work; reject cross-origin forms.
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{self.headers.get("Host")}':
                self.json(403, {'error': 'Запрос с другого сайта запрещён'})
                return
            try:
                if path == '/api/training':
                    from scripts.train_yolo import start_training, training_status
                    start_training()
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
                    self.json(201, app.add_references(fields.get('species', ''), fields.get('stage', ''), files))
                else:
                    self.json(202, {'id': app.start(files, fields)})
            except ValueError as exc:
                self.json(400, {'error': str(exc)})
            except Exception:
                logging.exception('Cannot start analysis')
                self.json(500, {'error': 'Не удалось выполнить действие. Проверьте систему на вкладке «Подготовка».'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Olzha Agro local web dashboard')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    app = Dashboard()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(app))
    print(f'Olzha Agro: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()


if __name__ == '__main__':
    main()
