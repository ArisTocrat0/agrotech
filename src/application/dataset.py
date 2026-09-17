"""Build immutable, image-separated YOLO snapshots from human weed decisions."""
import hashlib
import json
import math
import os
import shutil
import uuid
from pathlib import Path

import yaml

from .review import load_results
from ..vision.image_utils import load_image_rgb
from ..infrastructure.exporters import normalize_bbox


def prepare_dataset(folder: Path, output: Path, job_id: str) -> dict:
    rows = load_results(folder)
    if not rows or any(d.get('review') not in {'weed', 'crop', 'not_plant'}
                       for row in rows for d in row['detections']):
        raise ValueError('Сначала проверьте все объекты, включая «Не уверен».')
    source_root = (folder / 'input').resolve()
    prepared = []
    seen = {}
    # Classification review confirms weed vs crop, not species or growth stage.
    for row in rows:
        weeds = [d for d in row['detections'] if d.get('review') == 'weed']
        if not weeds:
            continue  # Detection review alone does not certify a negative image.
        source = (source_root / row['image']).resolve()
        if not source.is_relative_to(source_root) or not source.is_file():
            raise ValueError('Исходные снимки недоступны для подготовки датасета.')
        image = load_image_rgb(source)
        if image.size != (row['width'], row['height']):
            raise ValueError('Размер исходного снимка не совпадает с разметкой.')
        labels = []
        for detection in weeds:
            box = normalize_bbox(detection['bbox'], image.width, image.height)
            if not all(math.isfinite(v) for v in box) or box[2] <= 0 or box[3] <= 0:
                raise ValueError('Некорректная рамка в проверенной разметке.')
            labels.append('0 ' + ' '.join(f'{v:.8f}' for v in box))
        labels = sorted(labels)
        digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        if digest in seen:
            if seen[digest] != labels:
                raise ValueError('Одинаковые снимки имеют разную разметку.')
            continue
        seen[digest] = labels
        prepared.append((digest, source, labels, row['image']))
    if len(prepared) < 2:
        raise ValueError('Нужны минимум два разных снимка с подтверждёнными сорняками.')
    prepared.sort(key=lambda item: item[0])
    val_count = max(1, round(len(prepared) * .2))
    version = output / ('versions/' + uuid.uuid4().hex)
    version.mkdir(parents=True)
    published = False
    temporary = output / ('dataset-' + uuid.uuid4().hex + '.tmp')
    try:
        manifest = []
        for i, (digest, source, labels, original) in enumerate(prepared):
            split = 'val' if i < val_count else 'train'
            images, annotations = version / 'images' / split, version / 'labels' / split
            images.mkdir(parents=True, exist_ok=True)
            annotations.mkdir(parents=True, exist_ok=True)
            load_image_rgb(source).save(images / f'{digest}.png')
            (annotations / f'{digest}.txt').write_text('\n'.join(labels) + '\n', encoding='utf-8')
            manifest.append({'source': original, 'sha256': digest, 'split': split, 'objects': len(labels)})
        summary = {'job_id': job_id, 'train_images': len(prepared)-val_count,
                   'val_images': val_count, 'objects': sum(len(item[2]) for item in prepared),
                   'classes': ['weed'], 'images': manifest}
        (version / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        config = {'path': str(version.resolve()), 'train': 'images/train', 'val': 'images/val', 'names': {0: 'weed'}}
        snapshot = version / 'dataset.yaml'
        snapshot.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
        from scripts.train_yolo_full import validate_dataset
        validate_dataset(snapshot)
        shutil.copyfile(snapshot, temporary)
        os.replace(temporary, output / 'dataset.yaml')
        published = True
        return summary
    finally:
        temporary.unlink(missing_ok=True)
        if not published:
            shutil.rmtree(version)
