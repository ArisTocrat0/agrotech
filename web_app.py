"""Local dashboard. Run: python web_app.py."""
import argparse
import json
import logging
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

    def close(self):
        for process in self.processes.values():
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

    def start(self, files: list[tuple[str, bytes]]) -> str:
        from PIL import Image
        from io import BytesIO
        references = self.root / 'data' / 'Сорняки'
        if not any(p.suffix.lower() in {'.jpg', '.jpeg', '.png'} and len(p.relative_to(references).parts) >= 3
                   for p in references.rglob('*') if p.is_file()):
            raise ValueError('Добавьте эталоны в data/Сорняки/Вид/Стадия, затем повторите запуск.')
        if not 1 <= len(files) <= 20:
            raise ValueError('Выберите от 1 до 20 фотографий.')
        for name, data in files:
            if Path(name).suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
                raise ValueError('Допустимы только JPG, JPEG и PNG.')
            try:
                with Image.open(BytesIO(data)) as image:
                    image.verify()
            except Exception as exc:
                raise ValueError(f'Не удалось прочитать изображение: {name}') from exc
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
                   'created': datetime.now(timezone.utc).isoformat()}
            with (folder / 'analysis.log').open('w') as log:
                process = subprocess.Popen([sys.executable, str(self.root/'run.py'),
                    '--references', str(references), '--input', str(folder/'input'), '--output', str(folder)],
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
                if path == '/api/jobs':
                    with app.lock:
                        self.json(200, app.history())
                    return
                if path.startswith('/api/jobs/'):
                    parts = path.split('/')
                    folder = app.directory(parts[3])
                    action = parts[4] if len(parts) > 4 else ''
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
                          '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if path in assets:
                    name, mime = assets[path]
                    self.send(200, (ROOT/'web'/name).read_bytes(), mime)
                else:
                    self.json(404, {'error': 'Не найдено'})
            except (OSError, ValueError, IndexError, KeyError) as exc:
                self.json(404, {'error': str(exc)})

        def do_POST(self):
            if urlparse(self.path).path != '/api/analyze':
                self.json(404, {'error': 'Не найдено'})
                return
            # Only the local dashboard can submit work; reject cross-origin forms.
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{self.headers.get("Host")}':
                self.json(403, {'error': 'Запрос с другого сайта запрещён'})
                return
            try:
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
                self.json(202, {'id': app.start(files)})
            except ValueError as exc:
                self.json(400, {'error': str(exc)})
            except Exception:
                logging.exception('Cannot start analysis')
                self.json(500, {'error': 'Не удалось запустить анализ. Подробности в терминале сервера.'})
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
