"""Persistent optional human decisions layered over immutable model results."""
import json
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
                prediction = {k:d.get(k) for k in [
                    'species','stage','kind','species_prediction','category_prediction',
                    'prediction_status','uncertainty_reasons']}
                d['prediction'] = prediction
                original_kind = d.get('kind') or ('unknown' if d.get('species') == 'unknown' else 'weed')
                d['review'] = decision['decision']
                d['kind'] = decision['decision']
                d['reviewed_at'] = decision['at']
                d['manual_correction'] = decision['decision'] != original_kind
                d['review_status'] = 'corrected' if d['manual_correction'] else 'confirmed'
                # Category review does not certify a species. If a known weed/crop is
                # changed to the opposite category or to not-a-plant, keep the raw
                # prediction in d['prediction'] but stop presenting that species as final.
                if (original_kind in {'weed', 'crop'} and
                        decision['decision'] in {'weed', 'crop', 'not_plant'} and
                        decision['decision'] != original_kind):
                    d.update(species='unknown',stage='unknown',weed_class=None,lifecycle=None)
                if decision['decision'] == 'not_plant':
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
