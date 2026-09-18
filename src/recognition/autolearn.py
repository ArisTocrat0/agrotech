"""Supervised linear head with separate species/category calibration.

Validation selects regularization and acceptance thresholds; test remains untouched.
These metrics concern reference-photo classification, never field detection.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

VERSION = 3
CROPS = ('Пшеница', 'Ячмень', 'Подсолнечник')
MIN_CALIBRATION_ACCEPTED = 10
TARGET_ACCEPTED_ACCURACY = .9


def _group_value(row):
    for field in ('field_id', 'series_id', 'capture_date'):
        if row.get(field):
            return field + ':' + str(row[field])
    return None


def split_records(records):
    class_groups = defaultdict(list)
    seen = {}
    unique = []
    for i, row in enumerate(records):
        key = (row['species'], row.get('kind', 'weed'))
        digest = row['sha256']
        if digest in seen:
            if seen[digest] != key:
                raise ValueError('Одинаковое фото имеет разные классы в датасете.')
            continue
        seen[digest] = key
        unique.append(i)
        class_groups[key].append(i)

    # If field/series/date metadata exists, keep each group wholly in one split.
    # Refuse an unusable grouped split instead of silently leaking adjacent frames.
    if any(_group_value(records[i]) for i in unique):
        grouped = defaultdict(list)
        for i in unique:
            grouped[_group_value(records[i]) or ('image:' + records[i]['sha256'])].append(i)
        tokens = sorted(grouped, key=lambda value: hashlib.sha256(
            ('split42-group:' + value).encode()).hexdigest())
        if len(tokens) < 3:
            raise ValueError('Для train/validation/test нужны минимум три независимые группы полей/серий/дат.')
        count = max(1, int(len(tokens) * .2))
        test_groups = set(tokens[:count])
        val_groups = set(tokens[count:2*count])
        train_groups = set(tokens[2*count:])
        train = [i for token in train_groups for i in grouped[token]]
        val = [i for token in val_groups for i in grouped[token]]
        test = [i for token in test_groups for i in grouped[token]]
        for key in class_groups:
            for name, split in [('train', train), ('validation', val), ('test', test)]:
                if not any((records[i]['species'], records[i].get('kind', 'weed')) == key
                           for i in split):
                    raise ValueError(
                        f'Недостаточно независимых групп для класса {key[0]} в {name}; '
                        'добавьте данные вместо разбиения соседних кадров.')
        return train, val, test, []

    train, val, test = [], [], []
    excluded = []
    for key, ids in sorted(class_groups.items()):
        ids.sort(key=lambda i: hashlib.sha256(('split42' + records[i]['sha256']).encode()).hexdigest())
        if len(ids) < 3:
            excluded.append(key[0])
            continue
        count = max(1, int(len(ids) * .2))
        test.extend(ids[:count]); val.extend(ids[count:2*count]); train.extend(ids[2*count:])
    return train, val, test, excluded


def measure(predictions, labels, names):
    per_class = {}
    for i, name in enumerate(names):
        mask = labels == i
        per_class[name] = {'count': int(mask.sum()),
                           'accuracy': float((predictions[mask] == i).float().mean())}
    return {'accuracy': float((predictions == labels).float().mean()),
            'balanced_accuracy': sum(v['accuracy'] for v in per_class.values()) / len(names),
            'count': len(labels), 'per_class': per_class}


def _calibrate_threshold(margins, correct, min_accepted=MIN_CALIBRATION_ACCEPTED,
                         target=TARGET_ACCEPTED_ACCURACY):
    """Return a validation-only threshold and why it is or is not available."""
    count = len(margins)
    base = {'validation_count': count, 'min_accepted': min_accepted,
            'target_accepted_accuracy': target, 'threshold': None}
    if count < min_accepted:
        return None, {**base, 'status': 'insufficient_validation_data'}
    for candidate in sorted(set(margins.tolist())):
        accepted = margins >= candidate
        accepted_count = int(accepted.sum())
        if accepted_count < min_accepted:
            continue
        accuracy = float(correct[accepted].float().mean())
        if accuracy >= target:
            return float(candidate), {**base, 'status': 'calibrated',
                                      'threshold': float(candidate),
                                      'accepted_count': accepted_count,
                                      'accepted_accuracy': accuracy}
    return None, {**base, 'status': 'target_not_met'}


def _category_view(scores, labels, classes):
    """Collapse species scores/labels into crop-vs-weed scores when both exist."""
    import torch
    kinds = sorted({kind for _, kind in classes})
    if kinds != ['crop', 'weed']:
        return None
    columns = [[i for i, (_, kind) in enumerate(classes) if kind == target] for target in kinds]
    category_scores = torch.stack([scores[:, ids].max(dim=1).values for ids in columns], dim=1)
    category_labels = torch.tensor([kinds.index(classes[int(label)][1]) for label in labels],
                                   device=labels.device)
    top = category_scores.topk(2, dim=1)
    margins = top.values[:, 0] - top.values[:, 1]
    correct = top.indices[:, 0] == category_labels
    return kinds, category_labels, top, margins, correct


def _accepted_metrics(predictions, labels, accepted):
    if not len(accepted):
        return {'accepted_count': 0, 'coverage': 0., 'accepted_accuracy': None}
    count = int(accepted.sum())
    return {'accepted_count': count,
            'coverage': float(accepted.float().mean()),
            'accepted_accuracy': (float((predictions[accepted] == labels[accepted]).float().mean())
                                  if count else None)}


def train_head(index, output: Path):
    import torch
    records = index['metadata']['records']
    fingerprint = hashlib.sha256(json.dumps({'version': VERSION, 'metadata': index['metadata']},
                                           sort_keys=True).encode()).hexdigest()
    if output.exists():
        state = torch.load(output, map_location='cpu', weights_only=True)
        if state.get('fingerprint') == fingerprint:
            return LearnedClassifier(state)
    species_kinds = {}
    for row in records:
        kind = row.get('kind', 'weed')
        if row['species'] in species_kinds and species_kinds[row['species']] != kind:
            raise ValueError('Один вид не может иметь разные категории в датасете.')
        species_kinds[row['species']] = kind
    train, val, test, excluded = split_records(records)
    if not train:
        raise ValueError('Для автообучения нужны минимум три разных размеченных фото каждого вида.')
    classes = sorted({(records[i]['species'], records[i].get('kind', 'weed')) for i in train})
    if len(classes) < 2:
        raise ValueError('Для автообучения нужны минимум два класса растений.')
    labels = torch.tensor([classes.index((r['species'], r.get('kind', 'weed')))
                           if (r['species'], r.get('kind', 'weed')) in classes else -1 for r in records])
    x = index['embeddings'].detach().cpu().float()
    x = torch.cat((x, torch.ones((len(x), 1))), dim=1)
    y = torch.nn.functional.one_hot(labels[train], len(classes)).float()
    counts = torch.bincount(labels[train], minlength=len(classes)).float()
    weights = (len(train) / (len(classes) * counts[labels[train]])).sqrt().unsqueeze(1)
    a, b = x[train] * weights, y * weights
    best = None
    for alpha in (.01, .1, 1., 10.):
        head = torch.linalg.solve(a.T @ a + alpha * torch.eye(a.shape[1]), a.T @ b)
        scores = x[val] @ head
        metrics = measure(scores.argmax(1), labels[val], [c[0] for c in classes])
        if best is None or metrics['balanced_accuracy'] > best[0]:
            best = (metrics['balanced_accuracy'], head, alpha, metrics)
    _, head, alpha, validation = best

    validation_scores = x[val] @ head
    species_top = validation_scores.topk(2, dim=1)
    species_margins = species_top.values[:, 0] - species_top.values[:, 1]
    species_correct = species_top.indices[:, 0] == labels[val]
    species_threshold, species_calibration = _calibrate_threshold(species_margins, species_correct)

    category_validation = _category_view(validation_scores, labels[val], classes)
    category_threshold = None
    if category_validation is None:
        category_calibration = {
            'status': 'unsupported_missing_category_class', 'threshold': None,
            'validation_count': len(val), 'min_accepted': MIN_CALIBRATION_ACCEPTED,
            'target_accepted_accuracy': TARGET_ACCEPTED_ACCURACY,
        }
    else:
        _, _, _, category_margins, category_correct = category_validation
        category_threshold, category_calibration = _calibrate_threshold(
            category_margins, category_correct)

    test_scores = x[test] @ head
    species_test_top = test_scores.topk(2, dim=1)
    species_test_margins = species_test_top.values[:, 0] - species_test_top.values[:, 1]
    species_accepted = (species_test_margins >= species_threshold if species_threshold is not None
                        else torch.zeros(len(test), dtype=torch.bool))
    report = measure(species_test_top.indices[:, 0], labels[test], [c[0] for c in classes])
    report.update(_accepted_metrics(species_test_top.indices[:, 0], labels[test], species_accepted))
    report['unknown_rate'] = 1. - report['coverage']

    category_test = _category_view(test_scores, labels[test], classes)
    if category_test is None:
        category_report = {
            'accuracy': None, 'crop_weed_error_rate': None, 'accepted_count': 0,
            'coverage': None, 'accepted_accuracy': None,
            'reason': 'crop_and_weed_examples_required',
        }
    else:
        kinds, category_labels, category_top, category_margins, _ = category_test
        category_accepted = (category_margins >= category_threshold if category_threshold is not None
                             else torch.zeros(len(test), dtype=torch.bool))
        category_accuracy = float((category_top.indices[:, 0] == category_labels).float().mean())
        category_report = {
            'labels': kinds, 'accuracy': category_accuracy,
            'crop_weed_error_rate': 1. - category_accuracy,
            **_accepted_metrics(category_top.indices[:, 0], category_labels, category_accepted),
        }

    grouping_fields = sorted({field for field in ('field_id', 'series_id', 'capture_date')
                              if any(row.get(field) for row in records)})
    report.update(scope='reference_photo_species_classification', field_accuracy=None,
                  target=TARGET_ACCEPTED_ACCURACY,
                  target_met=report['balanced_accuracy'] >= TARGET_ACCEPTED_ACCURACY,
                  train_count=len(train), validation=validation, excluded_species=excluded,
                  crop_species=[c[0] for c in classes if c[1] == 'crop'],
                  split=('grouped_by_field_series_or_date' if grouping_fields else
                         'sha256_deduplicated_images_not_fields'),
                  split_group_metadata=grouping_fields,
                  leakage_limitation=(None if grouping_fields else
                                      'Нет field_id/series_id/date: соседние кадры нельзя гарантированно развести по группам.'),
                  alpha=alpha, species_calibration=species_calibration,
                  category_calibration=category_calibration, category=category_report,
                  limitation='Проверка вида на эталонных фото. Точность обнаружения на полях не измерена.')
    state = {'fingerprint': fingerprint, 'head': head, 'classes': classes,
             'threshold': species_threshold, 'category_threshold': category_threshold,
             'calibration': {'species': species_calibration, 'category': category_calibration},
             'report': report}
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp')
    torch.save(state, temp); temp.replace(output)
    return LearnedClassifier(state)


class LearnedClassifier:
    def __init__(self, state):
        self.state = state
        self.report = state['report']
        self.species_kinds = dict(state['classes'])
        self._head_cache = {}

    def _head_for(self, embeddings):
        key = (str(embeddings.device), str(embeddings.dtype))
        head = self._head_cache.get(key)
        if head is None:
            head = self.state['head'].to(device=embeddings.device, dtype=embeddings.dtype,
                                         non_blocking=True)
            self._head_cache[key] = head
        return head

    def classify_detailed(self, embeddings):
        import torch
        if not len(embeddings):
            return []
        # Keep the linear head on the embeddings device. Only tiny final diagnostics
        # cross to CPU; this avoids a full embeddings transfer on accelerator runs.
        x = embeddings.detach().float()
        head = self._head_for(x)
        scores = x @ head[:-1] + head[-1]
        top = scores.topk(2, dim=1)
        species_margins = top.values[:, 0] - top.values[:, 1]
        species_threshold = self.state.get('threshold')
        species_calibration = (self.state.get('calibration') or {}).get('species') or {
            'status': 'legacy_calibrated' if species_threshold is not None else 'insufficient_calibration_data'}
        species_status = species_calibration.get('status', 'unknown')

        classes = self.state['classes']
        kinds = sorted({kind for _, kind in classes})
        category_top = category_margins = None
        if kinds == ['crop', 'weed']:
            columns = [[i for i, (_, kind) in enumerate(classes) if kind == target] for target in kinds]
            category_scores = torch.stack([scores[:, ids].max(dim=1).values for ids in columns], dim=1)
            category_top = category_scores.topk(2, dim=1)
            category_margins = category_top.values[:, 0] - category_top.values[:, 1]
        category_threshold = self.state.get('category_threshold')
        category_calibration = (self.state.get('calibration') or {}).get('category') or {
            'status': ('legacy_uncalibrated' if category_top is not None
                       else 'unsupported_missing_category_class')}
        category_status = category_calibration.get('status', 'unknown')

        top_values = top.values.detach().cpu().tolist()
        top_ids = top.indices.detach().cpu().tolist()
        species_margin_values = species_margins.detach().cpu().tolist()
        category_values = (category_top.indices.detach().cpu().tolist()
                           if category_top is not None else [None] * len(x))
        category_margin_values = (category_margins.detach().cpu().tolist()
                                  if category_margins is not None else [None] * len(x))
        result = []
        for values, ids, margin, category_ids, category_margin in zip(
                top_values, top_ids, species_margin_values, category_values, category_margin_values):
            predicted_species, predicted_kind = classes[ids[0]]
            species_accepted = species_threshold is not None and margin >= species_threshold
            reasons = []
            if species_threshold is None:
                reasons.append('insufficient_calibration_data'
                               if species_status == 'insufficient_validation_data'
                               else 'species_calibration_unavailable')
            elif not species_accepted:
                reasons.append('low_species_margin')

            category_prediction = predicted_kind
            category_accepted = False
            if category_ids is None:
                category_prediction = None
            else:
                category_prediction = kinds[category_ids[0]]
                category_accepted = (category_threshold is not None
                                     and category_margin >= category_threshold)
                if category_threshold is None:
                    reasons.append('insufficient_category_calibration'
                                   if category_status == 'insufficient_validation_data'
                                   else 'category_calibration_unavailable')
                elif not category_accepted:
                    reasons.append('low_category_margin')
            result.append({
                'species': predicted_species if species_accepted else 'unknown',
                'species_prediction': predicted_species,
                'stage': 'unknown',
                'model_score': float(margin),
                'score_type': 'linear_margin_not_probability',
                'species_accepted': bool(species_accepted),
                'category': category_prediction if category_accepted else 'unknown',
                'category_prediction': category_prediction,
                'category_score': (float(category_margin) if category_margin is not None else None),
                'category_score_type': ('linear_margin_not_probability'
                                        if category_margin is not None else None),
                'category_accepted': bool(category_accepted),
                'uncertainty_reasons': reasons,
            })
        return result

    def classify(self, embeddings):
        """Compatibility triple: accepted species, unknown stage, linear margin."""
        return [(row['species'], row['stage'], row['model_score'])
                for row in self.classify_detailed(embeddings)]
