"""Stable class-aware suppression, using the optional C++ kernel when built."""
from pathlib import Path
import ctypes
from functools import lru_cache
from ..domain.types import WeedDetection


def iou(a, b):
    area = max(0, min(a.x2,b.x2)-max(a.x1,b.x1))*max(0,min(a.y2,b.y2)-max(a.y1,b.y1))
    union = (a.x2-a.x1)*(a.y2-a.y1)+(b.x2-b.x1)*(b.y2-b.y1)-area
    return area/union if union > 0 else 0.0


@lru_cache(maxsize=1)
def kernel():
    try:
        lib = ctypes.CDLL(str(Path(__file__).resolve().parents[2]/'artifacts/native/libagro_nms.so'))
        fn = lib.agro_nms
        fn.argtypes = [ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_int),ctypes.c_int,
                       ctypes.c_double,ctypes.POINTER(ctypes.c_int)]
        fn.restype = ctypes.c_int
        return fn
    except (OSError, AttributeError):
        return None


def nms(detections: list[WeedDetection], iou_threshold=0.4, backend='auto'):
    if not 0 <= iou_threshold <= 1:
        raise ValueError('Invalid NMS threshold')
    ordered = sorted(detections, key=lambda d:d.similarity_score, reverse=True)
    fn = kernel() if backend != 'python' else None
    if fn and ordered:
        size = len(ordered)
        boxes = (ctypes.c_double*(size*4))(*(v for d in ordered for v in (d.x1,d.y1,d.x2,d.y2)))
        labels = {}
        groups = (ctypes.c_int*size)(*(labels.setdefault((d.species,d.stage),len(labels)) for d in ordered))
        output = (ctypes.c_int*size)()
        count = fn(boxes,groups,size,iou_threshold,output)
        kept = [ordered[output[i]] for i in range(count)]
    else:
        kept = []
        for d in ordered:
            if not any((d.species,d.stage)==(k.species,k.stage) and iou(d,k)>iou_threshold for k in kept):
                kept.append(d)
    for i, d in enumerate(kept,1):
        d.id = i
    return kept
