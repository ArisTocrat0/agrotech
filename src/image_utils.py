from pathlib import Path
from PIL import Image, ImageOps

EXTENSIONS = {".jpg", ".jpeg", ".png"}


def image_paths(path: Path) -> list[Path]:
    if not path.exists():
        raise FileNotFoundError(path)
    paths = [path] if path.is_file() else path.rglob("*")
    return sorted(p for p in paths if p.is_file() and p.suffix.lower() in EXTENSIONS)


def load_image_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def candidate_crop(image: Image.Image, box: object, padding: float) -> Image.Image:
    if padding < 0:
        raise ValueError("crop_padding must be nonnegative")
    dx = round((box.x2 - box.x1) * padding)
    dy = round((box.y2 - box.y1) * padding)
    return image.crop((max(0, box.x1-dx), max(0, box.y1-dy),
                       min(image.width, box.x2+dx), min(image.height, box.y2+dy)))
