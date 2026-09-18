"""Supervised linear head; validation selects regularization, test is untouched.

These metrics concern reference-photo classification, never field detection.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

VERSION = 2
CROPS = ('Пшеница', 'Ячмень', 'Подсолнечник')


def split_records(records):
    groups = defaultdict(list)
    seen = {}
    for i, row in enumerate(records):
        key = (row['species'], row.get('kind', 'weed'))
        digest = row['sha256']
        if digest in seen:
            if seen[digest] != key:
                raise ValueError('Одинаковое фото имеет разные классы в датасете.')
            continue
        seen[digest] = key
        groups[key].append(i)
    train, val, test = [], [], []
    excluded = []
    for key, ids in sorted(groups.items()):
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
    # Acceptance threshold is chosen on validation only. It is not a probability.
    scores = x[val] @ head
    top = scores.topk(2, dim=1)
    margins = top.values[:, 0] - top.values[:, 1]
    correct = top.indices[:, 0] == labels[val]
    threshold = None
    for candidate in sorted(set(margins.tolist())):
        accepted = margins >= candidate
        if int(accepted.sum()) >= 10 and float(correct[accepted].float().mean()) >= .9:
            threshold = candidate
            break
    scores = x[test] @ head
    top = scores.topk(2, dim=1)
    accepted = ((top.values[:, 0] - top.values[:, 1]) >= threshold
                if threshold is not None else torch.zeros(len(test), dtype=torch.bool))
    report = measure(top.indices[:, 0], labels[test], [c[0] for c in classes])
    report.update(scope='reference_photo_species_classification', field_accuracy=None,
                  target=.9, target_met=report['balanced_accuracy'] >= .9,
                  accepted_count=int(accepted.sum()), coverage=float(accepted.float().mean()),
                  accepted_accuracy=float((top.indices[:, 0][accepted] == labels[test][accepted]).float().mean()) if accepted.any() else None,
                  train_count=len(train), validation=validation, excluded_species=excluded,
                  crop_species=[c[0] for c in classes if c[1] == 'crop'],
                  split='sha256_deduplicated_images_not_fields', alpha=alpha,
                  limitation='Проверка вида на эталонных фото. Точность обнаружения на полях не измерена.')
    state = {'fingerprint': fingerprint, 'head': head, 'classes': classes, 'threshold': threshold, 'report': report}
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp')
    torch.save(state, temp); temp.replace(output)
    return LearnedClassifier(state)


class LearnedClassifier:
    def __init__(self, state):
        self.state = state
        self.report = state['report']
        self.species_kinds = dict(state['classes'])

    def classify(self, embeddings):
        import torch
        if not len(embeddings):
            return []
        x = embeddings.detach().cpu().float()
        scores = torch.cat((x, torch.ones((len(x), 1))), dim=1) @ self.state['head']
        top = scores.topk(2, dim=1)
        result = []
        for values, ids in zip(top.values.tolist(), top.indices.tolist()):
            margin = values[0] - values[1]
            species = (self.state['classes'][ids[0]][0]
                       if self.state['threshold'] is not None and margin >= self.state['threshold'] else 'unknown')
            # Growth stage has no trained target; do not invent one.
            result.append((species, 'unknown', margin))
        return result
