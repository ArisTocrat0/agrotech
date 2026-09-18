import csv
import json
from collections import Counter
from pathlib import Path
from ..domain.types import WeedDetection


def image_result(name: str, width: int, height: int, detections: list[WeedDetection]) -> dict:
    from ..domain.agronomy import plant_info
    rows = []
    for d in detections:
        row = {"id":d.id, "species":d.species, "stage":d.stage,
               "similarity_score":d.similarity_score, **plant_info(d.species, d.kind or None),
               "bbox":{k:getattr(d,k) for k in ("x1","y1","x2","y2")}}
        for key in (
            'species_prediction', 'species_accepted', 'model_score', 'score_type',
            'category_prediction', 'category_score', 'category_score_type',
            'category_accepted', 'prediction_status', 'stage_status',
            'uncertainty_reasons', 'uncertainty_messages',
        ):
            if hasattr(d, key):
                row[key] = getattr(d, key)
        rows.append(row)
    result = {"image":name,"width":width,"height":height,"detections":rows}
    recount(result)
    return result


def recount(result):
    from ..domain.agronomy import plant_info, assessment, stage_advice
    rows = result['detections']
    for row in rows:
        row.update(plant_info(row.get('species', 'unknown'), row.get('kind')))
        row['priority'] = 'high' if row['lifecycle'] == 'perennial' else 'normal'
        row['stage_advice'] = stage_advice(row.get('stage', '')) if row['kind'] == 'weed' else None
        row.setdefault('species_prediction',
                       row.get('species') if row.get('species') != 'unknown' else None)
        row.setdefault('species_accepted', row.get('species') != 'unknown')
        row.setdefault('category_prediction',
                       row.get('kind') if row.get('kind') in {'weed', 'crop'} else None)
        row.setdefault('category_accepted', row.get('kind') in {'weed', 'crop'})
        row.setdefault('uncertainty_reasons', [])
        row.setdefault('uncertainty_messages', [])
        row.setdefault('stage_status',
                       'known' if row.get('stage') not in {None, '', 'unknown'} else 'unknown_untrained')
        row.setdefault('prediction_status',
                       'recognized' if row.get('species') != 'unknown'
                       and row.get('kind') in {'weed', 'crop'} else 'uncertain')
        if row.get('review') and 'review_status' not in row:
            row['review_status'] = 'corrected' if row.get('manual_correction') else 'confirmed'
    weeds = [d for d in rows if d['kind']=='weed']
    reason_counts = Counter(reason for d in rows for reason in d.get('uncertainty_reasons', []))
    result.update(
        total_weeds=len(weeds), total_candidates=len(rows),
        crop_count=sum(d['kind']=='crop' for d in rows),
        unknown_count=sum(d['kind']=='unknown' for d in rows),
        rejected_count=sum(d['kind']=='not_plant' for d in rows),
        recognized_count=sum(d.get('prediction_status') == 'recognized' for d in rows),
        uncertain_count=sum(d.get('prediction_status') == 'uncertain' for d in rows),
        manual_reviewed_count=sum(bool(d.get('review')) for d in rows),
        manual_correction_count=sum(bool(d.get('manual_correction')) for d in rows),
        uncertainty_reason_counts=dict(reason_counts),
        counts_by_species=dict(Counter(d['species'] for d in weeds if d['species'] != 'unknown')),
        counts_by_species_and_stage=dict(Counter(
            f"{d['species']}__{d['stage']}" for d in weeds if d['species'] != 'unknown')),
    )
    result['agronomy'] = assessment(rows,result['width'],result['height'],result.get('gsd_cm'))
    return result


def _join(value):
    if isinstance(value, list):
        return ';'.join(str(item) for item in value)
    return value


def save_results(results: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output/"results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    fields = [
        "image", "detection_id", "species", "species_prediction", "species_accepted",
        "stage", "stage_status", "similarity_score", "model_score", "score_type",
        "kind", "category_prediction", "category_score", "category_score_type",
        "category_accepted", "prediction_status", "uncertainty_reasons",
        "uncertainty_messages", "weed_class", "lifecycle", "priority",
        "stage_action", "review", "review_status", "manual_correction",
        "x1", "y1", "x2", "y2",
    ]
    with (output/"results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for result in results:
            for d in result["detections"]:
                writer.writerow({
                    "image": result["image"], "detection_id": d["id"],
                    "species": d.get("species"), "species_prediction": d.get("species_prediction"),
                    "species_accepted": d.get("species_accepted"),
                    "stage": d.get("stage"), "stage_status": d.get("stage_status"),
                    "similarity_score": d.get("similarity_score"),
                    "model_score": d.get("model_score"),
                    "score_type": d.get("score_type", "cosine_similarity"),
                    "kind": d.get("kind","weed"),
                    "category_prediction": d.get("category_prediction"),
                    "category_score": d.get("category_score"),
                    "category_score_type": d.get("category_score_type"),
                    "category_accepted": d.get("category_accepted"),
                    "prediction_status": d.get("prediction_status"),
                    "uncertainty_reasons": _join(d.get("uncertainty_reasons", [])),
                    "uncertainty_messages": _join(d.get("uncertainty_messages", [])),
                    **{key:d.get(key) for key in ('weed_class','lifecycle','priority')},
                    "stage_action":(d.get('stage_advice') or {}).get('action'),
                    "review":d.get("review",""),
                    "review_status":d.get("review_status",""),
                    "manual_correction":d.get("manual_correction",""),
                    **d["bbox"],
                })


def normalize_bbox(box: dict, width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (box[k] for k in ("x1", "y1", "x2", "y2"))
    if not (width > 0 and height > 0 and 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("Invalid bounding box or image dimensions")
    return ((x1+x2)/(2*width), (y1+y2)/(2*height), (x2-x1)/width, (y2-y1)/height)
