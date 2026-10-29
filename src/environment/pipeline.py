"""Evidence-preserving photo analysis, separate from weed inference."""
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .media import exif_capture_location, load_photo
from .model import CLASSES

DISCLAIMER = ('Предварительные визуальные гипотезы требуют проверки человеком. Отсутствие обнаружений не доказывает безопасность. '
              'Обычная камера может пропустить дым, огонь, ночные и скрытые очаги; химическое загрязнение не определяется. '
              'GPS относится к позиции съёмки, не к точному положению объекта. Полёт и вызов служб не выполняются.')


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def validated_detection(row, width, height, threshold, allowed_classes=CLASSES):
    if not isinstance(row, dict) or row.get('class_name') not in allowed_classes:
        raise ValueError('Неизвестный класс результата модели.')
    confidence, bbox = row.get('confidence'), row.get('bbox')
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or
            not math.isfinite(confidence) or not 0 <= confidence <= 1 or
            not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bbox)):
        raise ValueError('Некорректные confidence/bbox от модели.')
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError('Рамка модели выходит за границы фото.')
    if confidence < threshold:
        return None
    return {'class_name': row['class_name'], 'confidence': round(confidence, 6),
            'bbox': [round(v, 3) for v in bbox]}


def geojson(events):
    features = []
    for event in events:
        point = event['location']
        geometry = None if point is None else {'type': 'Point', 'coordinates': [point['longitude'], point['latitude']]}
        properties = {key: event[key] for key in ['id', 'class_name', 'confidence', 'source_name', 'timestamp_seconds',
                                                  'review_status', 'possible_duplicate_of']}
        properties.update(location_provenance=point, geometry_role='capture_position_not_object' if point else 'unknown')
        features.append({'type': 'Feature', 'id': event['id'], 'geometry': geometry, 'properties': properties})
    return {'type': 'FeatureCollection', 'features': features}


def analyze(folder, manifest, detector):
    from PIL import ImageDraw
    folder = Path(folder)
    evidence = folder / 'evidence'
    evidence.mkdir(exist_ok=True)
    result = {'schema_version': 1, 'mode': 'environment', 'status': 'complete',
              'created': datetime.now(timezone.utc).isoformat(), 'model': detector.metadata,
              'media': [], 'events': [], 'warnings': [DISCLAIMER],
              'geojson_url': f"/api/environment/files/{manifest['id']}/events.geojson"}
    total_photos = 0
    for item in manifest['media']:
        report = {'source_name': item['source_name'], 'kind': 'image', 'frames_analyzed': 0,
                  'coverage': {'sampling': 'single_image'}, 'warnings': [], 'acquisition': 'photo_upload'}
        result['media'].append(report)
        try:
            path = folder / 'input' / item['stored_name']
            data = path.read_bytes()
            report['source_sha256'] = hashlib.sha256(data).hexdigest()
            image = load_photo(path)
            capture = manifest['geodata'].get(item['source_name']) or exif_capture_location(data)
            report['location'] = capture
            if capture is None:
                report['warnings'].append('Достоверные координаты отсутствуют: фото не размещается на карте.')
            detections = detector.detect(image)
            if not isinstance(detections, list) or len(detections) > 100:
                raise ValueError('Модель должна вернуть не больше 100 объектов на фото.')
            validated = [validated_detection(row, *image.size, manifest['options']['confidence']) for row in detections]
            validated = [row for row in validated if row is not None]
            stem = f"{item['index']:02d}_00000000"
            image.save(evidence / (stem + '.jpg'), quality=92)
            annotated = image.copy()
            draw = ImageDraw.Draw(annotated)
            photo_events = []
            for detection in validated:
                draw.rectangle(detection['bbox'], outline={'fire': 'red', 'smoke': 'orange', 'trash': 'yellow'}[detection['class_name']], width=3)
                draw.text((detection['bbox'][0], detection['bbox'][1]),
                          f"{detection['class_name']} {detection['confidence']:.2f}", fill='white', stroke_width=1, stroke_fill='black')
                photo_events.append({'id': uuid.uuid4().hex, **detection, 'source_name': item['source_name'],
                                     'frame_index': 0, 'timestamp_seconds': None,
                                     'evidence_url': f"/api/environment/files/{manifest['id']}/evidence/{stem}_annotated.jpg",
                                     'source_evidence_url': f"/api/environment/files/{manifest['id']}/evidence/{stem}.jpg",
                                     'location': capture, 'object_location': None, 'review_status': 'unreviewed', 'possible_duplicate_of': None})
            annotated.save(evidence / (stem + '_annotated.jpg'), quality=92)
            result['events'].extend(photo_events)
            total_photos += 1
            report['frames_analyzed'] = 1
            report['evidence_url'] = f"/api/environment/files/{manifest['id']}/evidence/{stem}_annotated.jpg"
        except TimeoutError:
            report['warnings'].append('Глобальный лимит времени исчерпан; обработка остановлена.')
            result['status'] = 'partial'
            write_json(folder / 'results.json', result)
            write_json(folder / 'events.geojson', geojson(result['events']))
            raise
        except (ValueError, OSError, RuntimeError) as exc:
            report['warnings'].append(f'Обработка этого фото остановлена: {exc}')
            result['status'] = 'partial'
        write_json(folder / 'results.json', result)
        write_json(folder / 'events.geojson', geojson(result['events']))
    if total_photos == 0:
        raise ValueError('Ни одно фото не проанализировано; см. предупреждения результатов.')
    return result
