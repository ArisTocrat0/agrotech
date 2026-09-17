from dataclasses import dataclass
from collections.abc import Iterator
from PIL import Image


@dataclass
class Tile:
    image: Image.Image
    offset_x: int
    offset_y: int
    width: int
    height: int
    tile_id: int


def positions(length: int, size: int, step: int) -> list[int]:
    end = max(0, length-size)
    return sorted(set([*range(0, end+1, step), end]))


def iter_tiles(image: Image.Image, tile_size: int = 1024,
               overlap: float = 0.2) -> Iterator[Tile]:
    if tile_size <= 0 or not 0 <= overlap < 1:
        raise ValueError("tile_size > 0 and 0 <= overlap < 1 required")
    step = max(1, round(tile_size*(1-overlap)))
    tile_id = 0
    for y in positions(image.height, tile_size, step):
        for x in positions(image.width, tile_size, step):
            crop = image.crop((x, y, min(x+tile_size, image.width), min(y+tile_size, image.height)))
            yield Tile(crop, x, y, crop.width, crop.height, tile_id)
            tile_id += 1
