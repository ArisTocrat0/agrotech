import argparse
import json
import math
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.image_utils import load_image_rgb
from src.exporters import normalize_bbox


def export_dataset(results_path: Path, images: Path, output: Path, min_similarity: float = 0.7) -> int:
    if not math.isfinite(min_similarity) or not -1 <= min_similarity <= 1:
        raise ValueError("Invalid similarity threshold")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if isinstance(results, dict):
        results = [results]
    prepared = []
    classes = set()
    for result in results:
        source = (images/result["image"]).resolve() if images.is_dir() else images.resolve()
        if images.is_dir() and not source.is_relative_to(images.resolve()):
            raise ValueError("Image path escapes source directory")
        if images.is_file() and (len(results) != 1 or Path(result["image"]).name != images.name):
            raise ValueError("Single source image does not match results")
        image = load_image_rgb(source)
        if image.size != (result["width"], result["height"]):
            raise ValueError(f"EXIF-oriented dimensions do not match: {source}")
        labels = []
        for d in result["detections"]:
            if "unknown" in (d["species"], d["stage"]) or not math.isfinite(d["similarity_score"]) or d["similarity_score"] < min_similarity:
                continue
            key = f'{d["species"]}__{d["stage"]}'
            box = normalize_bbox(d["bbox"], image.width, image.height)
            classes.add(key)
            labels.append((key, box))
        # Omit images without accepted labels: they are not verified negative examples.
        if labels:
            prepared.append((source, labels))
    if not prepared:
        raise ValueError("No accepted detections; pseudo dataset was not created")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty to prevent stale labels/classes")
    names = sorted(classes)
    (output/"images").mkdir(parents=True, exist_ok=True)
    (output/"labels").mkdir(parents=True, exist_ok=True)
    for i, (source, labels) in enumerate(prepared):
        # Physically apply EXIF orientation so YOLO coordinates match the image pixels.
        load_image_rgb(source).save(output/"images"/f"{i:06d}.png")
        rows = [str(names.index(key))+" "+" ".join(f"{v:.8f}" for v in box) for key, box in labels]
        (output/"labels"/f"{i:06d}.txt").write_text("\n".join(rows)+"\n", encoding="utf-8")
    manifest = {f"{i:06d}.png": str(source) for i, (source, _) in enumerate(prepared)}
    (output/"source_images.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # Valid Ultralytics schema; shared paths are an export placeholder, not an evaluation split.
    (output/"dataset.yaml").write_text(yaml.safe_dump({"path": str(output.resolve()), "train": "images", "val": "images", "names": dict(enumerate(names))}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return len(prepared)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export pseudo labels for manual review")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("pseudo_dataset"))
    parser.add_argument("--min-similarity", type=float, default=0.70)
    args = parser.parse_args()
    export_dataset(args.results, args.images, args.output, args.min_similarity)


if __name__ == "__main__":
    main()
