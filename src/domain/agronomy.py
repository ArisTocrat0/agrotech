"""Plant taxonomy and explainable screening rules from the supplied mentor sheet.

These are configurable project heuristics, not herbicide prescriptions.
"""
import math
from collections import Counter

CROPS = {'пшеница', 'ячмень', 'подсолнечник'}
TAXONOMY = {
    'щирица': ('A', 'annual'), 'марь': ('A', 'annual'),
    'бодяк': ('A', 'perennial'), 'осот': ('A', 'perennial'), 'вьюнок': ('A', 'perennial'),
    'овсюг': ('B', 'annual'), 'куриное просо': ('B', 'annual'), 'пырей': ('B', 'perennial'),
}


def plant_info(species, kind=None):
    name = species.casefold()
    if kind == 'crop' or any(name.startswith(crop) for crop in CROPS):
        return {'kind':'crop', 'weed_class':None, 'lifecycle':None}
    if name == 'unknown' or kind == 'unknown':
        return {'kind':'unknown', 'weed_class':None, 'lifecycle':None}
    for key, (group, lifecycle) in TAXONOMY.items():
        if name.startswith(key):
            return {'kind':kind or 'weed', 'weed_class':group, 'lifecycle':lifecycle}
    return {'kind':kind or 'weed', 'weed_class':None, 'lifecycle':None}


def stage_window(stage):
    name = stage.casefold().replace('–', '-').replace('—', '-')
    if 'цветен' in name or 'более 6' in name:
        return 'late'
    if '4-6' in name or '4–6' in name:
        return 'developed'
    if 'семядол' in name or '2 лист' in name:
        return 'early'
    return 'unknown'


def assessment(detections, width, height, gsd_cm=None):
    if gsd_cm is not None and (not math.isfinite(gsd_cm) or gsd_cm <= 0):
        raise ValueError('GSD must be a positive finite number')
    area = width * height * (gsd_cm / 100) ** 2 if gsd_cm else None
    weeds = [d for d in detections if d.get('kind') == 'weed']
    life = Counter(d.get('lifecycle') for d in weeds)
    annual = life['annual'] / area if area else None
    perennial = life['perennial'] / area if area else None
    level = 'scale_required'
    if area:
        level = 'critical' if perennial >= 2 else 'high' if annual > 15 else 'medium' if annual > 5 else 'low'
    return {'area_m2':area, 'gsd_cm':gsd_cm, 'annual_per_m2':annual,
            'perennial_per_m2':perennial, 'level':level,
            'unclassified_weeds':life[None],
            'stage_windows':dict(Counter(stage_window(d.get('stage','')) for d in weeds)),
            'reviewed':sum(bool(d.get('review')) for d in detections),
            'rule_source':'mentor_sheet_project_heuristic', 'requires_agronomist':True,
            'dose':None}
