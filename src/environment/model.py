"""Local Ultralytics detection adapter. Never downloads or substitutes weights."""
import json
import math
import os
from pathlib import Path

CLASSES = ('trash', 'fire', 'smoke')


class ModelNotConfigured(ValueError):
    pass


def configuration(environ=None):
    env = os.environ if environ is None else environ
    raw = env.get('AGRO_ENV_MODEL', '').strip()
    if not raw:
        raise ModelNotConfigured('Модель не настроена. Укажите локальный AGRO_ENV_MODEL и AGRO_ENV_CLASS_MAP.')
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.is_file() or path.suffix.lower() != '.pt':
        raise ValueError('AGRO_ENV_MODEL должен указывать абсолютный путь к доверенным локальным весам Ultralytics .pt.')
    try:
        mapping = json.loads(env.get('AGRO_ENV_CLASS_MAP', ''))
    except (TypeError, ValueError) as exc:
        raise ValueError('AGRO_ENV_CLASS_MAP должен быть JSON-объектом имён классов модели.') from exc
    if (not isinstance(mapping, dict) or not mapping or
            any(not isinstance(k, str) or not k.strip() or v not in CLASSES for k, v in mapping.items())):
        raise ValueError('Сопоставьте все имена классов модели только с trash, fire или smoke.')
    return path.resolve(), mapping


def status(environ=None):
    try:
        _, mapping = configuration(environ)
        return {'status': 'configured', 'classes': sorted(set(mapping.values())),
                'model_validation': 'pending_load',
                'message': 'Локальные веса настроены. Совместимость и классы проверяются при запуске; качество на дроне не подтверждено.'}
    except ModelNotConfigured as exc:
        return {'status': 'model_not_configured', 'classes': [], 'message': str(exc)}
    except ValueError as exc:
        return {'status': 'configuration_error', 'classes': [], 'message': str(exc)}


class LocalYoloDetector:
    def __init__(self, confidence=0.35, environ=None):
        path, self.mapping = configuration(environ)
        self.confidence = confidence
        # Only explicitly installed Ultralytics and pre-existing weights are allowed.
        # Checkpoint files execute model deserialization: only trusted operator weights.
        os.environ['YOLO_OFFLINE'] = 'true'
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ValueError('Установите зависимости проекта: пакет ultralytics отсутствует.') from exc
        self.model = YOLO(str(path), task='detect')
        names = self.model.names
        self.names = dict(names) if isinstance(names, dict) else dict(enumerate(names))
        if set(self.names) != set(range(len(self.names))):
            raise ValueError('Нужны последовательные целые ID классов модели.')
        names = list(self.names.values())
        if len(set(names)) != len(names) or set(names) != set(self.mapping):
            raise ValueError('Имена классов весов не совпадают с AGRO_ENV_CLASS_MAP. Подмена обычной COCO-модели не допускается.')
        if getattr(self.model, 'task', None) != 'detect':
            raise ValueError('Нужна модель Ultralytics object detection, не классификатор или сегментатор.')
        self.metadata = {'backend': 'ultralytics', 'classes': sorted(set(self.mapping.values()))}
        # Record checkpoint fingerprint for reproducibility, without disclosing local paths.
        import hashlib
        with path.open('rb') as stream:
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
            self.metadata['weights_sha256'] = digest.hexdigest()

    def detect(self, image):
        # Ultralytics expects BGR for numpy sources; PIL is passed directly as RGB.
        outputs = self.model.predict(source=image, conf=self.confidence, verbose=False,
                                     device='cpu', max_det=100, save=False)
        if not isinstance(outputs, list) or len(outputs) != 1:
            raise ValueError('Модель должна вернуть ровно один результат для одного фото.')
        detections = []
        for output in outputs:
            if tuple(output.orig_shape) != (image.height, image.width):
                raise ValueError('Размер исходного фото в результате модели не совпадает.')
            if output.boxes is None:
                continue
            for box in output.boxes:
                raw_index = box.cls.item()
                if (isinstance(raw_index, bool) or not isinstance(raw_index, (int, float)) or
                        not math.isfinite(raw_index) or raw_index != int(raw_index) or int(raw_index) not in self.names):
                    raise ValueError('Модель вернула некорректный ID класса.')
                index = int(raw_index)
                name = output.names[index]
                if name != self.names[index]:
                    raise ValueError('Имена классов изменились во время обработки.')
                if name not in self.mapping:
                    raise ValueError('Модель вернула неизвестный класс.')
                confidence = float(box.conf.item())
                bbox = [float(v) for v in box.xyxy[0].tolist()]
                if not math.isfinite(confidence) or not all(math.isfinite(v) for v in bbox):
                    raise ValueError('Модель вернула нечисловой результат.')
                detections.append({'class_name': self.mapping[name], 'confidence': confidence,
                                   'bbox': bbox})
        return detections
