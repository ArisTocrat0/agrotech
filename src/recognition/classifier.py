"""Reference matching guarded across crops, weed classes, life cycles and phases."""
from collections import defaultdict
import math
from ..domain.agronomy import plant_info, stage_window


def index_for_kind(index, kind: str) -> dict:
    """Return a lightweight view of an index containing only one plant kind."""
    records = index['metadata']['records']
    ids = [i for i, row in enumerate(records) if row.get('kind', 'weed') == kind]
    if not ids:
        raise ValueError(f'No {kind} references in index')
    metadata = dict(index['metadata'])
    metadata['records'] = [records[i] for i in ids]
    return {'metadata': metadata, 'embeddings': index['embeddings'][ids]}


class ReferenceClassifier:
    def __init__(self, index, top_k=5, similarity_threshold=0.55, category_margin=0.05):
        if top_k < 1 or not -1 <= similarity_threshold <= 1 or not math.isfinite(category_margin) or not 0 <= category_margin <= 2:
            raise ValueError('Invalid classification settings')
        self.embeddings = index['embeddings']
        self.top_k, self.threshold = top_k, similarity_threshold
        self.category_margin = category_margin
        self.groups = defaultdict(list)
        self.species_kinds = {}
        self.decision_groups = defaultdict(list)
        for i, row in enumerate(index['metadata']['records']):
            kind = row.get('kind', 'weed')
            if kind not in {'weed', 'crop'}:
                raise ValueError('Reference kind must be weed or crop')
            if row['species'] in self.species_kinds and self.species_kinds[row['species']] != kind:
                raise ValueError('Conflicting crop/weed references for the same species')
            self.groups[(row['species'],row['stage'])].append(i)
            self.species_kinds[row['species']] = kind
        if not self.groups:
            raise ValueError('Reference index is empty')
        for i, (species, stage) in enumerate(self.groups):
            info = plant_info(species, self.species_kinds[species])
            self.decision_groups[(info['kind'], info['weed_class'], info['lifecycle'])].append(i)
        self.stage_competitors = [
            [j for j, (other_species, other_stage) in enumerate(self.groups)
             if species == other_species and stage_window(stage) != stage_window(other_stage)]
            for species, stage in self.groups]

    def classify(self, embeddings):
        import torch
        if len(embeddings) == 0:
            return []
        similarities = embeddings @ self.embeddings.T
        keys = list(self.groups)
        # top-k over all query images at once; only the final small array crosses to Python.
        scores = torch.stack([similarities[:,ids].topk(min(self.top_k,len(ids)),dim=1).values.mean(dim=1)
                              for ids in self.groups.values()],dim=1)
        best_scores, best_ids = scores.max(dim=1)
        ambiguous = torch.zeros(len(embeddings), dtype=torch.bool, device=scores.device)
        if len(self.decision_groups) > 1:
            category_scores = torch.stack([scores[:, ids].max(dim=1).values
                                           for ids in self.decision_groups.values()], dim=1)
            first_two = category_scores.topk(2, dim=1).values
            ambiguous = (first_two[:, 0] - first_two[:, 1]) <= self.category_margin
        results = []
        score_rows = scores.tolist()
        for row_scores, score, idx, unclear in zip(score_rows, best_scores.tolist(),best_ids.tolist(),ambiguous.tolist()):
            species, stage = keys[idx]
            if score < self.threshold or unclear:
                species = stage = 'unknown'
            elif any(score - row_scores[j] <= self.category_margin for j in self.stage_competitors[idx]):
                stage = 'unknown'
            results.append((species,stage,score))
        return results


class CropContextClassifier:
    """Detect obvious crop plants and infer the dominant field crop without steering weed labels.

    Crop references are intentionally used only as context. Weed species are classified by a
    separate weed-only ReferenceClassifier so missing or weak crop references can never turn
    all detections into unknown.
    """

    def __init__(self, index, similarity_threshold=0.55, category_margin=0.05):
        import torch
        import torch.nn.functional as F

        if not -1 <= similarity_threshold <= 1:
            raise ValueError('Invalid crop similarity threshold')
        if not math.isfinite(category_margin) or not 0 <= category_margin <= 2:
            raise ValueError('Invalid crop category margin')

        self.threshold = similarity_threshold
        self.margin = category_margin
        records = index['metadata']['records']
        embeddings = index['embeddings']

        groups = defaultdict(list)
        for i, row in enumerate(records):
            kind = row.get('kind', 'weed')
            if kind in {'weed', 'crop'}:
                groups[(row['species'], kind)].append(i)

        self.keys = list(groups)
        self.crop_columns = [i for i, (_, kind) in enumerate(self.keys) if kind == 'crop']
        self.weed_columns = [i for i, (_, kind) in enumerate(self.keys) if kind == 'weed']
        self.crop_species = [self.keys[i][0] for i in self.crop_columns]

        if self.keys:
            self.centroids = torch.stack([
                F.normalize(embeddings[ids].mean(dim=0, keepdim=True), dim=1).squeeze(0)
                for ids in groups.values()
            ])
        else:
            self.centroids = embeddings.new_empty((0, embeddings.shape[1]))

    def _scores(self, embeddings):
        import torch.nn.functional as F
        if not len(embeddings) or not len(self.centroids):
            return embeddings.new_empty((len(embeddings), 0))
        return F.normalize(embeddings, dim=1) @ self.centroids.T

    def classify(self, embeddings):
        """Return (is_crop, crop_species, crop_score, best_weed_score) for each candidate."""
        import torch

        if not len(embeddings):
            return []
        if not self.crop_columns:
            return [(False, None, None, None) for _ in range(len(embeddings))]

        scores = self._scores(embeddings)
        crop_scores = scores[:, self.crop_columns]
        best_crop_scores, crop_ids = crop_scores.max(dim=1)

        if self.weed_columns:
            best_weed_scores = scores[:, self.weed_columns].max(dim=1).values
        else:
            best_weed_scores = torch.full_like(best_crop_scores, -1.0)

        flags = ((best_crop_scores >= self.threshold) &
                 ((best_crop_scores - best_weed_scores) >= self.margin))

        result = []
        for flag, crop_id, crop_score, weed_score in zip(
                flags.tolist(), crop_ids.tolist(),
                best_crop_scores.tolist(), best_weed_scores.tolist()):
            result.append((flag, self.crop_species[crop_id], crop_score, weed_score))
        return result

    def infer_crop(self, embeddings):
        """Infer the dominant crop from the strongest crop-like candidates in the image."""
        if not len(embeddings) or not self.crop_columns:
            return None, None

        crop_scores = self._scores(embeddings)[:, self.crop_columns]
        top_count = min(20, max(1, (len(embeddings) + 4) // 5))
        field_scores = crop_scores.topk(top_count, dim=0).values.mean(dim=0)
        score, idx = field_scores.max(dim=0)
        return self.crop_species[int(idx)], float(score)
