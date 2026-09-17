"""Reference matching guarded across crops, weed classes, life cycles and phases."""
from collections import defaultdict
import math
from ..domain.agronomy import plant_info, stage_window


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
