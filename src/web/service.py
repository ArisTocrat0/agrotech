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


class Dashboard:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.jobs = root / 'outputs' / 'web'
        self.lock = threading.Lock()
        self.processes = {}
        self.check_process = None
        self.import_process = None
        self.check_log = self.jobs / "system-check.log"

    def close(self):
        for process in [*self.processes.values(), *([self.import_process] if self.import_process else []), *([self.check_process] if self.check_process else [])]:
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
        groups = {}
        for directory, kind in [('Сорняки','weed'),('Культуры','crop')]:
            base = self.root / 'data' / directory
            for path in base.rglob('*'):
                if path.is_file() and path.suffix.lower() in {'.jpg','.jpeg','.png'}:
                    parts = path.relative_to(base).parts
                    if len(parts) >= 3:
                        key = (parts[0],parts[1],kind)
                        groups[key] = groups.get(key,0)+1
        return [{'species':key[0],'stage':key[1],'kind':key[2],'count':count}
                for key,count in sorted(groups.items())]

    def add_references(self, species, stage, files, kind="weed"):
        if kind not in {'weed','crop'}:
            raise ValueError('Некорректный тип растения')
        labels = [species.strip(), stage.strip()]
        if any(not value or len(value) > 100 or value in {'.', '..'} or
               any(c in value for c in '/\\') or any(ord(c) < 32 for c in value)
               for value in labels):
            raise ValueError('Укажите вид и стадию без слешей, до 100 символов.')
        self.validate_images(files)
        with self.lock:
            if self.import_process is not None and self.import_process.poll() is None:
                raise ValueError('Дождитесь загрузки эталонов культур.')
            if any(p.poll() is None for p in self.processes.values()):
                raise ValueError('Анализ уже выполняется. Дождитесь его завершения.')
            base = (self.root / 'data' / ('Культуры' if kind == 'crop' else 'Сорняки')).resolve()
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
            gsd = float(fields['gsd_cm']) if fields.get('gsd_cm') else None
        except (TypeError, ValueError) as exc:
            raise ValueError('Проверьте числовые настройки анализа.') from exc
        if (not 128 <= tile <= 4096 or not 1 <= batch <= 128 or
                not math.isfinite(overlap) or not 0 <= overlap < 1 or
                not math.isfinite(similarity) or not -1 <= similarity <= 1):
            raise ValueError('Настройки анализа выходят за допустимые пределы.')
        if gsd is not None and (not math.isfinite(gsd) or not 0 < gsd <= 100):
            raise ValueError('Масштаб должен быть от 0 до 100 см/пиксель (не включая 0).')
        return {'gsd_cm':gsd, 'online':fields.get('online') == 'true', 'device': device, 'tile_size': tile, 'overlap': overlap,
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

    def import_status(self):
        code = self.import_process.poll() if self.import_process else None
        return {'status':'idle' if self.import_process is None else 'running' if code is None else 'done' if code == 0 else 'error',
                'log':self.log_tail(self.jobs/'crop-import.log')}

    def start_import(self):
        with self.lock:
            if self.import_process is not None and self.import_process.poll() is None:
                return self.import_status()
            if any(p.poll() is None for p in self.processes.values()):
                raise ValueError('Анализ уже выполняется. Дождитесь его завершения.')
            self.jobs.mkdir(parents=True,exist_ok=True)
            with (self.jobs/'crop-import.log').open('w') as log:
                self.import_process = subprocess.Popen([sys.executable,str(ROOT/'scripts/import_crop_references.py')],
                                                       cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            return self.import_status()

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
        from ..application.review import load_results
        from ..infrastructure.exporters import save_results
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / 'snapshot'
            save_results(load_results(folder), snapshot)
            source = folder
            if pseudo:
                if job_id == 'cli':
                    raise ValueError('Для экспорта YOLO запустите анализ через сайт.')
                from scripts.export_pseudo_yolo import export_dataset
                source = Path(temporary) / 'pseudo'
                try:
                    export_dataset(snapshot / 'results.json', folder / 'input', source)
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
                if not pseudo:
                    for filename in ['results.json','results.csv']:
                        archive.write(snapshot/filename,filename)
                for path in source.rglob('*'):
                    relative = path.relative_to(source)
                    if path.is_file() and (pseudo or relative.parts[0] in
                            {'annotated', 'debug', 'reviews.json', 'analysis.log'}):
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
            if self.import_process is not None and self.import_process.poll() is None:
                raise ValueError('Дождитесь загрузки эталонов культур.')
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
                    '--batch-size', str(options['batch_size']),
                    *(['--gsd-cm', str(options['gsd_cm'])] if options['gsd_cm'] else []),
                    *(['--online'] if options['online'] else []), *(['--debug'] if options['debug'] else [])],
                    cwd=self.root, stdout=log, stderr=subprocess.STDOUT)
            self.processes[job_id] = process
            (folder/'job.json').write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
            return job_id


