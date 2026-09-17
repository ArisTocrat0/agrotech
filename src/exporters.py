import csv
import json
from collections import Counter
from pathlib import Path
from .types import WeedDetection


def image_result(name: str, width: int, height: int, detections: list[WeedDetection]) -> dict:
    known = [d for d in detections if d.species != "unknown"]
    return {"image": name, "width": width, "height": height,
            "total_weeds": len(known), "total_candidates": len(detections),
            "unknown_count": len(detections)-len(known),
            "counts_by_species": dict(Counter(d.species for d in known)),
            "counts_by_species_and_stage": dict(Counter(f"{d.species}__{d.stage}" for d in known)),
            "detections": [{"id": d.id, "species": d.species, "stage": d.stage,
                            "similarity_score": d.similarity_score,
                            "bbox": {k: getattr(d, k) for k in ("x1", "y1", "x2", "y2")}} for d in detections]}


def save_results(results: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output/"results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    with (output/"results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "detection_id", "species", "stage", "similarity_score", "x1", "y1", "x2", "y2"])
        writer.writeheader()
        for result in results:
            for d in result["detections"]:
                writer.writerow({"image": result["image"], "detection_id": d["id"], "species": d["species"],
                                 "stage": d["stage"], "similarity_score": d["similarity_score"], **d["bbox"]})


def normalize_bbox(box: dict, width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (box[k] for k in ("x1", "y1", "x2", "y2"))
    if not (width > 0 and height > 0 and 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("Invalid bounding box or image dimensions")
    return ((x1+x2)/(2*width), (y1+y2)/(2*height), (x2-x1)/width, (y2-y1)/height)
