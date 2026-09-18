"""Deterministic project rules, separate from recognition and product application."""
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
RULE_VERSION = 'user_thresholds_v3'


def plant_info(species, kind=None):
    name = ' '.join((species or 'unknown').casefold().replace('ё', 'е').split())
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
    name = ' '.join((stage or '').casefold().replace('–', '-').replace('—', '-').split())
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
                   'late': 'warn_ineffective_crop_risk',
                   'unknown': 'stage_data_required'}[window],
        'proposed_multiplier_range': [1.15, 1.20] if window == 'developed' else None,
        'requires_product_label': True,
        'data_available': window != 'unknown',
        'missing_data': ['growth_stage'] if window == 'unknown' else [],
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
    blockers, limitations, missing_data = [], [], []

    if area is None:
        blockers.append('scale_required')
        missing_data.append('scale')
    if unclassified or unknown:
        blockers.append('uncertain_classification')
        missing_data.append('classification')
    if phases['late']:
        blockers.append('late_stage_crop_risk')
    if phases['unknown']:
        # Unknown stage limits stage-specific advice, but it does not invalidate a
        # recognized species/category or make the whole image analysis unfinished.
        limitations.append('unknown_stage')
        missing_data.append('growth_stage')
    if life['perennial'] and level == 'low':
        blockers.append('perennials_below_threshold')

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

    if blockers:
        recommendation_status = 'needs_data' if any(
            key in missing_data for key in ('scale', 'classification')) else 'needs_review'
        recommendation = 'agronomist_review'
    elif limitations:
        recommendation_status = 'partial'
        recommendation = action
    else:
        recommendation_status = 'ready'
        recommendation = action

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
        'recommendation': recommendation,
        'recommendation_status': recommendation_status,
        'recommendation_missing_data': list(dict.fromkeys(missing_data)),
        'review_reasons': blockers,
        'limitations': limitations,
        'analysis_complete': True,
        'reviewed': sum(bool(d.get('review')) for d in detections),
        'rule_source': 'user_supplied_project_heuristic', 'rule_version': RULE_VERSION,
        'density_scope': 'whole_image', 'requires_agronomist': True,
        'automatic_application_allowed': False, 'dose': None,
    }
