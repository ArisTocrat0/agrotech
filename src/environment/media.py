"""Bounded photo decoding and explicit capture-position provenance."""
import math
import warnings
from io import BytesIO

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
MAX_FILES = 10
MAX_UPLOAD = 100 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_SIDE = 8000


def finite_number(value, field):
    if isinstance(value, bool):
        raise ValueError(f'{field}: требуется конечное число.')
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{field}: требуется конечное число.') from exc
    if not math.isfinite(number):
        raise ValueError(f'{field}: требуется конечное число.')
    return number


def dimensions(width, height):
    if width <= 0 or height <= 0 or max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
        raise ValueError('Фото должно быть не больше 8000 px по стороне и 25 мегапикселей.')


def location(value, expected_source='operator_capture_position'):
    if not isinstance(value, dict) or value.get('source') != expected_source:
        raise ValueError(f'Укажите источник координат: {expected_source}.')
    lat = finite_number(value.get('latitude'), 'latitude')
    lon = finite_number(value.get('longitude'), 'longitude')
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Координаты вне диапазона широты/долготы.')
    return {'latitude': lat, 'longitude': lon, 'source': expected_source,
            'precision': 'capture_position_not_object'}


def validate_geodata(geodata, media):
    if not isinstance(geodata, dict) or set(geodata) - {row['source_name'] for row in media}:
        raise ValueError('Геоданные должны ссылаться только на исходные имена загруженных фото.')
    return {name: location(value) for name, value in geodata.items()}


def load_photo(path):
    from PIL import Image, ImageOps
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            with Image.open(path) as image:
                if image.format not in {'JPEG', 'PNG'}:
                    raise ValueError('Допустимы только настоящие JPEG/PNG изображения.')
                dimensions(*image.size)
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Нужно отдельное фото, не анимированный PNG.')
                image.load()
                return ImageOps.exif_transpose(image).convert('RGB')
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError('Не удалось безопасно прочитать изображение.') from exc


def exif_capture_location(data):
    """Read genuine embedded GPS, never camera centre/object geometry inference."""
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as image:
            gps = image.getexif().get_ifd(34853)
        if not gps:
            return None

        def degrees(values, direction, positive, negative):
            if direction not in (positive, negative) or len(values) != 3:
                raise ValueError('Invalid GPS EXIF')
            d, m, s = [finite_number(value, 'GPS EXIF') for value in values]
            if d < 0 or not 0 <= m < 60 or not 0 <= s < 60:
                raise ValueError('Invalid GPS EXIF')
            return (d + m / 60 + s / 3600) * (-1 if direction == negative else 1)

        return location({'latitude': degrees(gps[2], gps[1], 'N', 'S'),
                         'longitude': degrees(gps[4], gps[3], 'E', 'W'),
                         'source': 'embedded_gps_capture_position'}, 'embedded_gps_capture_position')
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError):
        return None
