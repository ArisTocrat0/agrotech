"""Deterministic project rules, separate from product-specific application rates."""
import math
import re
from collections import Counter

CROPS = {'пшеница', 'ячмень', 'подсолнечник'}
TAXONOMY = {
    'щирица': ('A', 'annual'), 'марь': ('A', 'annual'),
    'бодяк': ('A', 'perennial'), 'осот': ('A', 'perennial'), 'вьюнок': ('A', 'perennial'),
    'овсюг': ('B', 'annual'), 'куриное просо': ('B', 'annual'), 'пырей': ('B', 'perennial'),
}
ALIASES = {'ширица': 'щирица', 'выюнок': 'вьюнок'}
RULE_VERSION = 'user_thresholds_v2'


def plant_info(species, kind=None):
    name = ' '.join(species.casefold().replace('ё', 'е').split())
    first, _, rest = name.partition(' ')
    name = ALIASES.get(first, first) + (' ' + rest if rest else '')
    info = {'kind': kind or 'weed', 'weed_class': None, 'lifecycle': None}
    if kind in {'crop', 'unknown', 'not_plant'}:
        return info
    if any(name == crop or name.startswith(crop + ' ') for crop in CROPS):
        return {**info, 'kind': 'crop'}
    if name == 'unknown':
        return {**info, 'kind': kind or 'unknown'}
    for key, (group, lifecycle) in TAXONOMY.items():
        if name == key or name.startswith(key + ' '):
            return {**info, 'weed_class': group, 'lifecycle': lifecycle}
    return info


def stage_window(stage):
    name = ' '.join(stage.casefold().replace('–', '-').replace('—', '-').split())
    # Recognize only explicit phases. In particular, "12 листьев" is not "2 листа".
    if 'цветен' in name or re.search(r'более\s+6\b|(?<!\d)[7-9]\s+лист|(?<!\d)\d{2,}\s+лист', name):
        return 'late'
    if re.search(r'(?<!\d)4\s*-\s*6\s+лист', name):
        return 'developed'
    if 'семядол' in name or re.search(r'(?<!\d)[12]\s+лист', name):
        return 'early'
    return 'unknown'


def stage_advice(stage):
    window = stage_window(stage)
    return {
        'window': window,
        'action': {'early': 'base_minimum', 'developed': 'review_increase_15_20',
                   'late': 'warn_ineffective_crop_risk', 'unknown': 'review_stage'}[window],
        # A proposal from the user's rule, never an actuator command or a product dose.
        'proposed_multiplier_range': [1.15, 1.20] if window == 'developed' else None,
        'requires_product_label': True,
    }


def assessment(detections, width, height, gsd_cm=None):
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError('Image dimensions must be positive finite numbers')
    if gsd_cm is not None and (not math.isfinite(gsd_cm) or gsd_cm <= 0):
        raise ValueError('GSD must be a positive finite number')
    area = width * height * (gsd_cm / 100) ** 2 if gsd_cm else None
    if area is not None and (not math.isfinite(area) or area <= 0):
        raise ValueError('Image area must be positive and finite')
    weeds = [d for d in detections if d.get('kind') == 'weed']
    life = Counter(d.get('lifecycle') for d in weeds)
    annual = life['annual'] / area if area else None
    perennial = life['perennial'] / area if area else None
    level = 'scale_required'
    if area:
        level = 'critical' if perennial >= 2 else 'high' if annual > 15 else 'medium' if annual > 5 else 'low'
    action = {'scale_required': 'measure_scale', 'low': 'do_not_spray',
              'medium': 'standard_rate', 'high': 'maximum_label_rate',
              'critical': 'urgent_treatment'}[level]
    phases = Counter(stage_window(d.get('stage', '')) for d in weeds)
    unclassified = sum(d.get('weed_class') not in {'A', 'B'} or
                       d.get('lifecycle') not in {'annual', 'perennial'} for d in weeds)
    unknown = sum(d.get('kind') == 'unknown' for d in detections)
    reasons = []
    if area is None:
        reasons.append('scale_required')
    if unclassified or unknown:
        reasons.append('uncertain_classification')
    if phases['late']:
        reasons.append('late_stage_crop_risk')
    if phases['unknown']:
        reasons.append('unknown_stage')
    # The supplied rule defines no treatment for 0 < perennial density < 2.
    if life['perennial'] and level == 'low':
        reasons.append('perennials_below_threshold')
    classes = {}
    for group in ('A', 'B'):
        members = [d for d in weeds if d.get('weed_class') == group]
        counts = Counter(d.get('lifecycle') for d in members)
        classes[group] = {
            'count': len(members),
            'annual_count': counts['annual'], 'perennial_count': counts['perennial'],
            'annual_per_m2': counts['annual'] / area if area else None,
            'perennial_per_m2': counts['perennial'] / area if area else None,
            'priority': 'high' if counts['perennial'] else 'normal',
        }
    return {
        'area_m2': area, 'gsd_cm': gsd_cm, 'annual_per_m2': annual,
        'perennial_per_m2': perennial, 'level': level,
        'classes': classes, 'priority': 'high' if life['perennial'] else 'normal',
        'unclassified_weeds': unclassified, 'unknown_candidates': unknown,
        'stage_windows': dict(phases),
        'stage_recommendations': {phase: stage_advice(stage) for phase, stage in
                                  [('early', '2 листа'), ('developed', '4-6 листьев'),
                                   ('late', 'цветение'), ('unknown', 'unknown')] if phases[phase]},
        'threshold_action': action,
        'recommendation': 'agronomist_review' if reasons else action,
        'review_reasons': reasons,
        'reviewed': sum(d.get('review') in {'weed', 'crop', 'not_plant'} for d in detections),
        'rule_source': 'user_supplied_project_heuristic', 'rule_version': RULE_VERSION,
        'density_scope': 'whole_image', 'requires_agronomist': True,
        'automatic_application_allowed': False, 'dose': None,
    }
