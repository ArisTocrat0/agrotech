import csv
import json
from collections import Counter
from pathlib import Path
from ..domain.types import WeedDetection


def image_result(name: str, width: int, height: int, detections: list[WeedDetection]) -> dict:
    from ..domain.agronomy import plant_info, assessment
    rows = []
    for d in detections:
        rows.append({"id":d.id, "species":d.species, "stage":d.stage,
                     "similarity_score":d.similarity_score, **plant_info(d.species, d.kind or None),
                     "bbox":{k:getattr(d,k) for k in ("x1","y1","x2","y2")}})
    result = {"image":name,"width":width,"height":height,"detections":rows}
    recount(result)
    return result


def recount(result):
    from ..domain.agronomy import plant_info, assessment, stage_advice
    rows = result['detections']
    for row in rows:
        row.update(plant_info(row['species'], row.get('kind')))
        row['priority'] = 'high' if row['lifecycle'] == 'perennial' else 'normal'
        row['stage_advice'] = stage_advice(row.get('stage', '')) if row['kind'] == 'weed' else None
    weeds = [d for d in rows if d['kind']=='weed']
    result.update(total_weeds=len(weeds), total_candidates=len(rows),
                  crop_count=sum(d['kind']=='crop' for d in rows),
                  unknown_count=sum(d['kind']=='unknown' for d in rows),
                  rejected_count=sum(d['kind']=='not_plant' for d in rows),
                  counts_by_species=dict(Counter(d['species'] for d in weeds)),
                  counts_by_species_and_stage=dict(Counter(f"{d['species']}__{d['stage']}" for d in weeds)))
    result['agronomy'] = assessment(rows,result['width'],result['height'],result.get('gsd_cm'))
    return result


def save_results(results: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output/"results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    with (output/"results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "detection_id", "species", "stage", "similarity_score", "kind", "weed_class", "lifecycle", "priority", "stage_action", "review", "x1", "y1", "x2", "y2"])
        writer.writeheader()
        for result in results:
            for d in result["detections"]:
                writer.writerow({"image": result["image"], "detection_id": d["id"], "species": d["species"],
                                 "stage": d["stage"], "similarity_score": d["similarity_score"], "kind":d.get("kind","weed"),
                                 **{key:d.get(key) for key in ('weed_class','lifecycle','priority')},
                                 "stage_action":(d.get('stage_advice') or {}).get('action'),
                                 "review":d.get("review",""), **d["bbox"]})


def normalize_bbox(box: dict, width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (box[k] for k in ("x1", "y1", "x2", "y2"))
    if not (width > 0 and height > 0 and 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("Invalid bounding box or image dimensions")
    return ((x1+x2)/(2*width), (y1+y2)/(2*height), (x2-x1)/width, (y2-y1)/height)
