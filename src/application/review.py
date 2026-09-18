"""Persistent human decisions layered over immutable model results."""
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from ..infrastructure.exporters import recount

DECISIONS = {'weed','crop','not_plant','unknown'}


def load_results(folder: Path):
    results = json.loads((folder/'results.json').read_text(encoding='utf-8'))
    path = folder/'reviews.json'
    reviews = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    geometry_path = folder/'geometry.json'
    geometry = json.loads(geometry_path.read_text(encoding='utf-8')) if geometry_path.exists() else {}
    for row in results:
        row.update(geometry.get(row['image'],{}))
        for d in row['detections']:
            decision = reviews.get(row['image'],{}).get(str(d['id']))
            if decision:
                d['prediction'] = {k:d.get(k) for k in ['species','stage','kind']}
                d['review'] = decision['decision']
                d['kind'] = decision['decision']
                d['reviewed_at'] = decision['at']
                # A changed category does not confirm the model's species/lifecycle.
                original_kind = d['prediction'].get('kind') or ('unknown' if d['species']=='unknown' else 'weed')
                if original_kind != d['kind']:
                    d.update(species='unknown',stage='unknown',weed_class=None,lifecycle=None)
        recount(row)
    return results


def save_decision(folder: Path, image_index: int, detection_id: int, decision: str):
    if decision not in DECISIONS:
        raise ValueError('Некорректное решение проверки')
    rows = json.loads((folder/'results.json').read_text(encoding='utf-8'))
    if not 0 <= image_index < len(rows):
        raise ValueError('Изображение не найдено')
    row = rows[image_index]
    if not any(d['id']==detection_id for d in row['detections']):
        raise ValueError('Объект не найден')
    path = folder/'reviews.json'
    reviews = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    reviews.setdefault(row['image'],{})[str(detection_id)] = {
        'decision':decision,'at':datetime.now(timezone.utc).isoformat()}

    # Human review is durable training signal. Promote the exact crop into the
    # persistent reference dataset only when the reviewer agrees with the model's
    # original kind and a species label exists. Kind-only corrections are stored
    # separately so they cannot poison species labels.
    detection = next(d for d in row['detections'] if d['id'] == detection_id)
    try:
        from .experience import remember_exemplar, save_unresolved_review
        from ..vision.image_utils import load_image_rgb
        root = folder.parents[2]
        source_root = (folder / 'input').resolve()
        source = (source_root / row['image']).resolve()
        if source.is_relative_to(source_root) and source.is_file():
            image = load_image_rgb(source)
            box = detection['bbox']
            crop = image.crop((box['x1'], box['y1'], box['x2'], box['y2']))
            predicted_kind = detection.get('kind')
            predicted_species = detection.get('species')
            if (decision in {'weed', 'crop'} and
                    decision == predicted_kind and
                    predicted_species and predicted_species != 'unknown'):
                remember_exemplar(
                    root, crop, decision, predicted_species,
                    detection.get('similarity_score'), source='human'
                )
            elif decision in {'weed', 'crop'}:
                save_unresolved_review(root, crop, decision)
    except (OSError, ValueError, KeyError):
        # A review must remain saveable even if the source image is unavailable.
        pass

    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(reviews,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    return load_results(folder)


def save_geometry(folder, image_index, gsd_cm=None):
    import math
    from ..config import load_config
    from ..vision.image_utils import load_image_rgb
    from ..vision.vegetation import VegetationDetector
    from ..vision.rows import estimate_rows
    rows = json.loads((folder/'results.json').read_text(encoding='utf-8'))
    if not 0 <= image_index < len(rows):
        raise ValueError('Изображение не найдено')
    if gsd_cm is not None and (not math.isfinite(gsd_cm) or not 0 < gsd_cm <= 100):
        raise ValueError('Некорректный масштаб')
    row = rows[image_index]
    base = (folder/'input').resolve()
    source = (base/row['image']).resolve()
    if not source.is_relative_to(base) or not source.is_file():
        raise ValueError('Исходный снимок недоступен. Запустите анализ через сайт.')
    path = folder/'geometry.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data[row['image']] = {'gsd_cm':gsd_cm,'rows':estimate_rows(load_image_rgb(source),VegetationDetector(load_config()['vegetation']))}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    return load_results(folder)
