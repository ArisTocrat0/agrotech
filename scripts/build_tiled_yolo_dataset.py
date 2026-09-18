import argparse
from pathlib import Path

import yaml
from PIL import Image


def axis_positions(length: int, tile: int, stride: int):
    if length <= tile:
        return [0]

    values = list(range(0, length - tile + 1, stride))
    last = length - tile

    if values[-1] != last:
        values.append(last)

    return values


def read_labels(path: Path, width: int, height: int):
    boxes = []

    if not path.exists():
        return boxes

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        class_id = int(parts[0])
        cx, cy, bw, bh = map(float, parts[1:5])

        x1 = (cx - bw / 2) * width
        y1 = (cy - bh / 2) * height
        x2 = (cx + bw / 2) * width
        y2 = (cy + bh / 2) * height

        boxes.append((class_id, x1, y1, x2, y2))

    return boxes


def tile_split(
    source: Path,
    output: Path,
    split: str,
    tile_size: int,
    overlap: float,
    min_visible: float,
    empty_every: int,
):
    image_dir = source / "images" / split
    label_dir = source / "labels" / split

    out_images = output / "images" / split
    out_labels = output / "labels" / split

    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    stride = max(1, int(tile_size * (1.0 - overlap)))

    tile_count = 0
    object_count = 0
    empty_saved = 0
    empty_seen = 0

    image_paths = sorted(
        p for p in image_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    for image_path in image_paths:
        with Image.open(image_path) as im:
            image = im.convert("RGB")

        width, height = image.size

        boxes = read_labels(
            label_dir / f"{image_path.stem}.txt",
            width,
            height,
        )

        xs = axis_positions(width, tile_size, stride)
        ys = axis_positions(height, tile_size, stride)

        for y in ys:
            for x in xs:
                tile_labels = []

                tile_x2 = x + tile_size
                tile_y2 = y + tile_size

                for class_id, bx1, by1, bx2, by2 in boxes:
                    ix1 = max(bx1, x)
                    iy1 = max(by1, y)
                    ix2 = min(bx2, tile_x2)
                    iy2 = min(by2, tile_y2)

                    if ix2 <= ix1 or iy2 <= iy1:
                        continue

                    original_area = max(1.0, (bx2 - bx1) * (by2 - by1))
                    visible_area = (ix2 - ix1) * (iy2 - iy1)
                    visible_fraction = visible_area / original_area

                    if visible_fraction < min_visible:
                        continue

                    local_x1 = ix1 - x
                    local_y1 = iy1 - y
                    local_x2 = ix2 - x
                    local_y2 = iy2 - y

                    if local_x2 - local_x1 < 2 or local_y2 - local_y1 < 2:
                        continue

                    cx = ((local_x1 + local_x2) / 2) / tile_size
                    cy = ((local_y1 + local_y2) / 2) / tile_size
                    bw = (local_x2 - local_x1) / tile_size
                    bh = (local_y2 - local_y1) / tile_size

                    tile_labels.append(
                        f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"
                    )

                keep = bool(tile_labels)

                if not keep and empty_every > 0:
                    empty_seen += 1
                    if empty_seen % empty_every == 0:
                        keep = True
                        empty_saved += 1

                if not keep:
                    continue

                name = f"{image_path.stem}_x{x:04d}_y{y:04d}"

                crop = image.crop(
                    (
                        x,
                        y,
                        min(x + tile_size, width),
                        min(y + tile_size, height),
                    )
                )

                # На случай изображения меньше tile_size.
                if crop.size != (tile_size, tile_size):
                    canvas = Image.new(
                        "RGB",
                        (tile_size, tile_size),
                        (0, 0, 0),
                    )
                    canvas.paste(crop, (0, 0))
                    crop = canvas

                crop.save(out_images / f"{name}.jpg", quality=95)

                (out_labels / f"{name}.txt").write_text(
                    "\n".join(tile_labels) + ("\n" if tile_labels else ""),
                    encoding="utf-8",
                )

                tile_count += 1
                object_count += len(tile_labels)

    return tile_count, object_count, empty_saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="yolo_dataset")
    parser.add_argument("--output", default="yolo_tiled_dataset")
    parser.add_argument("--tile-size", type=int, default=1024)
    parser.add_argument("--overlap", type=float, default=0.20)
    parser.add_argument("--min-visible", type=float, default=0.35)
    parser.add_argument(
        "--empty-every",
        type=int,
        default=5,
        help="Сохранять примерно каждый N-й пустой tile; 0 = не сохранять",
    )
    args = parser.parse_args()

    source = Path(args.input).resolve()
    output = Path(args.output).resolve()

    if not source.exists():
        raise SystemExit(f"Не найден dataset: {source}")

    if output.exists() and any(output.iterdir()):
        raise SystemExit(
            f"{output} уже не пустой. Удалите его или выберите другой --output."
        )

    output.mkdir(parents=True, exist_ok=True)

    source_yaml = yaml.safe_load(
        (source / "dataset.yaml").read_text(encoding="utf-8")
    )

    stats = {}

    for split in ("train", "val", "test"):
        result = tile_split(
            source,
            output,
            split,
            args.tile_size,
            args.overlap,
            args.min_visible,
            args.empty_every,
        )
        stats[split] = result

    config = {
        "path": str(output),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": source_yaml["names"],
    }

    (output / "dataset.yaml").write_text(
        yaml.safe_dump(
            config,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    print("\nГотово.")
    for split, (tiles, objects, empty) in stats.items():
        print(
            f"{split:5s}: tiles={tiles}, "
            f"objects={objects}, empty_tiles={empty}"
        )

    print(f"\nDataset: {output}")
    print(f"Config:  {output / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
