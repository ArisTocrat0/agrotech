from .types import WeedDetection


def iou(a: object, b: object) -> float:
    area = max(0, min(a.x2, b.x2)-max(a.x1, b.x1)) * max(0, min(a.y2, b.y2)-max(a.y1, b.y1))
    union = (a.x2-a.x1)*(a.y2-a.y1) + (b.x2-b.x1)*(b.y2-b.y1) - area
    return area / union if union > 0 else 0.0


def nms(detections: list[WeedDetection], iou_threshold: float = 0.4) -> list[WeedDetection]:
    if not 0 <= iou_threshold <= 1:
        raise ValueError("Invalid NMS threshold")
    kept = []
    for det in sorted(detections, key=lambda d: d.similarity_score, reverse=True):
        if not any((det.species, det.stage) == (k.species, k.stage)
                   and iou(det, k) > iou_threshold for k in kept):
            kept.append(det)
    for number, det in enumerate(kept, 1):
        det.id = number
    return kept
