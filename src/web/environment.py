"""Environmental jobs, stored separately from weed results and training datasets."""
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from ..environment import model
from ..environment.media import (
    IMAGE_EXTENSIONS,
    MAX_FILES,
    MAX_UPLOAD,
    finite_number,
    load_photo,
    validate_geodata,
)
from ..environment.pipeline import write_json

ROOT = Path(__file__).resolve().parents[2]


class EnvironmentalDashboard:
    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.jobs = dashboard.root / 'outputs' / 'environment'

    def status(self):
        return {**model.status(), 'limits': {'max_upload_bytes': MAX_UPLOAD, 'max_files': MAX_FILES,
                                           'max_photo_pixels': 25_000_000, 'max_photo_side': 8000}}

    def directory(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('Некорректный идентификатор экологического анализа.')
        return self.jobs / job_id

    def job(self, job_id):
        folder = self.directory(job_id)
        row = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        if row['status'] == 'running':
            process = self.dashboard.processes.get(job_id)
            if process is None:
                row.update(status='error', error='Сервер перезапущен; анализ прерван.')
            elif process.poll() is not None:
                row['status'] = 'done' if process.returncode == 0 and (folder / 'results.json').exists() else 'error'
                if row['status'] == 'error':
                    row['error'] = self.dashboard.log_tail(folder / 'analysis.log')[-3000:] or 'Обработка завершилась без результата.'
            if row['status'] != 'running':
                write_json(folder / 'job.json', row)
        if (folder / 'results.json').exists():
            row['result'] = json.loads((folder / 'results.json').read_text(encoding='utf-8'))
        return row

    def history(self):
        rows = [self.job(path.parent.name) for path in self.jobs.glob('*/job.json')]
        return sorted([{k: v for k, v in row.items() if k != 'result'} for row in rows], key=lambda row: row['created'], reverse=True)

    def start(self, files, fields):
        model.configuration()  # Fail closed before keeping uploads or spawning a worker.
        if not 1 <= len(files) <= MAX_FILES or sum(len(data) for _, data in files) > MAX_UPLOAD:
            raise ValueError('Допустимо 1–10 файлов общим размером до 100 МБ.')
        confidence = finite_number(fields.get('confidence', 0.35), 'confidence')
        if not 0.01 <= confidence <= 1:
            raise ValueError('Порог должен быть от 0.01 до 1.')
        media = []
        for index, (name, data) in enumerate(files):
            if not isinstance(name, str) or len(name) > 240 or any(ord(c) < 32 for c in name):
                raise ValueError('Некорректное имя файла.')
            clean = Path(name.replace('\\', '/')).name
            suffix = Path(clean).suffix.lower()
            if suffix not in IMAGE_EXTENSIONS or not data:
                raise ValueError('Допустимы только фото JPG/JPEG/PNG, без пустых файлов.')
            load_photo(BytesIO(data))
            media.append({'index': index, 'source_name': clean, 'kind': 'image',
                          'stored_name': f'{index:02d}{suffix}'})
        if len({m['source_name'] for m in media}) != len(media):
            raise ValueError('Имена загруженных файлов должны быть уникальными.')
        try:
            geodata = json.loads(fields.get('geodata') or '{}')
        except (ValueError, TypeError) as exc:
            raise ValueError('Геоданные должны быть корректным JSON.') from exc
        if fields.get('latitude') or fields.get('longitude'):
            if geodata:
                raise ValueError('Выберите один способ задания координат: поля или JSON.')
            geodata = {m['source_name']: {'latitude': fields.get('latitude'), 'longitude': fields.get('longitude'),
                                         'source': 'operator_capture_position'} for m in media}
        geodata = validate_geodata(geodata, media)
        with self.dashboard.lock:
            if any(p.poll() is None for p in self.dashboard.processes.values()):
                raise ValueError('Анализ уже выполняется. Дождитесь его завершения.')
            job_id = uuid.uuid4().hex
            folder = self.directory(job_id)
            (folder / 'input').mkdir(parents=True)
            for item, (_, data) in zip(media, files):
                (folder / 'input' / item['stored_name']).write_bytes(data)
            manifest = {'id': job_id, 'media': media, 'geodata': geodata,
                        'options': {'confidence': confidence}}
            write_json(folder / 'manifest.json', manifest)
            row = {'id': job_id, 'name': f'Экология · {len(files)} файлов', 'status': 'running',
                   'created': datetime.now(timezone.utc).isoformat()}
            write_json(folder / 'job.json', row)
            try:
                with (folder / 'analysis.log').open('w') as log:
                    self.dashboard.processes[job_id] = subprocess.Popen(
                        [sys.executable, str(ROOT / 'scripts/analyze_environment.py'), '--job', str(folder)],
                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            except OSError:
                row.update(status='error', error='Не удалось запустить обработчик.')
                write_json(folder / 'job.json', row)
                raise
            return job_id

    def file(self, job_id, relative):
        # Explicit allowlist: originals and local model paths are never public assets.
        if not re.fullmatch(r'(?:events\.geojson|results\.json|evidence/[0-9]{2}_[0-9]{8}(?:_annotated)?\.jpg)', relative):
            raise ValueError('Файл не найден.')
        folder = self.directory(job_id).resolve()
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError('Файл не найден.')
        return path.read_bytes(), 'image/jpeg' if relative.endswith('.jpg') else 'application/json; charset=utf-8'
