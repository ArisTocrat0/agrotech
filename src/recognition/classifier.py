"""Reference matching with independent species, stage and crop/weed decisions."""
from collections import defaultdict
import math
from ..domain.agronomy import stage_window


class ReferenceClassifier:
    def __init__(self, index, top_k=5, similarity_threshold=0.55, category_margin=0.05):
        if (top_k < 1 or not -1 <= similarity_threshold <= 1
                or not math.isfinite(category_margin) or not 0 <= category_margin <= 2):
            raise ValueError('Invalid classification settings')
        self.embeddings = index['embeddings']
        self.top_k, self.threshold = top_k, similarity_threshold
        # This is a score margin, not a probability threshold.
        self.category_margin = category_margin
        self.groups = defaultdict(list)
        self.species_kinds = {}
        for i, row in enumerate(index['metadata']['records']):
            kind = row.get('kind', 'weed')
            if kind not in {'weed', 'crop'}:
                raise ValueError('Reference kind must be weed or crop')
            if row['species'] in self.species_kinds and self.species_kinds[row['species']] != kind:
                raise ValueError('Conflicting crop/weed references for the same species')
            self.groups[(row['species'], row['stage'])].append(i)
            self.species_kinds[row['species']] = kind
        if not self.groups:
            raise ValueError('Reference index is empty')

        self.keys = list(self.groups)
        self.species = list(dict.fromkeys(species for species, _ in self.keys))
        self.species_group_ids = {
            species: [i for i, (candidate, _) in enumerate(self.keys) if candidate == species]
            for species in self.species
        }
        self.kind_group_ids = {
            kind: [i for i, (species, _) in enumerate(self.keys)
                   if self.species_kinds[species] == kind]
            for kind in ('crop', 'weed')
        }
        self.available_kinds = [kind for kind, ids in self.kind_group_ids.items() if ids]

    @staticmethod
    def _top_margin(scores):
        import torch
        if scores.shape[1] == 1:
            values = scores[:, 0]
            indices = torch.zeros(len(scores), dtype=torch.long, device=scores.device)
            margins = torch.full_like(values, float('inf'))
            return values, indices, margins
        top = scores.topk(2, dim=1)
        return top.values[:, 0], top.indices[:, 0], top.values[:, 0] - top.values[:, 1]

    def classify_detailed(self, embeddings):
        import torch
        if len(embeddings) == 0:
            return []
        similarities = embeddings @ self.embeddings.T
        group_scores = torch.stack([
            similarities[:, ids].topk(min(self.top_k, len(ids)), dim=1).values.mean(dim=1)
            for ids in self.groups.values()
        ], dim=1)

        species_scores = torch.stack([
            group_scores[:, ids].max(dim=1).values
            for ids in self.species_group_ids.values()
        ], dim=1)
        species_best, species_ids, species_margins = self._top_margin(species_scores)

        category_best = category_ids = category_margins = None
        if len(self.available_kinds) == 2:
            category_scores = torch.stack([
                group_scores[:, self.kind_group_ids[kind]].max(dim=1).values
                for kind in self.available_kinds
            ], dim=1)
            category_best, category_ids, category_margins = self._top_margin(category_scores)

        group_rows = group_scores.detach().cpu().tolist()
        species_best_values = species_best.detach().cpu().tolist()
        species_id_values = species_ids.detach().cpu().tolist()
        species_margin_values = species_margins.detach().cpu().tolist()
        if category_ids is not None:
            category_id_values = category_ids.detach().cpu().tolist()
            category_best_values = category_best.detach().cpu().tolist()
            category_margin_values = category_margins.detach().cpu().tolist()
        else:
            category_id_values = [None] * len(embeddings)
            category_best_values = [None] * len(embeddings)
            category_margin_values = [None] * len(embeddings)

        results = []
        for row_scores, best_score, species_id, species_margin, category_id, category_score, category_margin in zip(
                group_rows, species_best_values, species_id_values, species_margin_values,
                category_id_values, category_best_values, category_margin_values):
            raw_species = self.species[species_id]
            species_accepted = (
                best_score >= self.threshold
                and (len(self.species) == 1 or species_margin > self.category_margin)
            )
            reasons = []
            if best_score < self.threshold:
                reasons.append('low_species_similarity')
            elif len(self.species) > 1 and species_margin <= self.category_margin:
                reasons.append('low_species_margin')

            best_stage = 'unknown'
            stage_status = 'unknown_untrained'
            if species_accepted:
                stage_ids = self.species_group_ids[raw_species]
                ranked = sorted(
                    ((row_scores[group_id], self.keys[group_id][1]) for group_id in stage_ids),
                    reverse=True
                )
                best_stage = ranked[0][1]
                competing_windows = [
                    score for score, stage in ranked[1:]
                    if stage_window(stage) != stage_window(best_stage)
                ]
                if competing_windows and ranked[0][0] - max(competing_windows) <= self.category_margin:
                    best_stage = 'unknown'
                    stage_status = 'unknown_ambiguous'
                else:
                    stage_status = 'known' if best_stage != 'unknown' else 'unknown_untrained'

            category_prediction = self.species_kinds[raw_species]
            category_accepted = False
            category_value = None
            category_margin_value = None
            if len(self.available_kinds) < 2:
                reasons.append('category_reference_missing')
            else:
                category_prediction = self.available_kinds[category_id]
                category_value = float(category_score)
                category_margin_value = float(category_margin)
                category_accepted = category_margin > self.category_margin
                if not category_accepted:
                    reasons.append('low_category_margin')

            results.append({
                'species': raw_species if species_accepted else 'unknown',
                'species_prediction': raw_species,
                'stage': best_stage if species_accepted else 'unknown',
                'stage_status': stage_status if species_accepted else 'unknown_species',
                'model_score': float(best_score),
                'score_type': 'cosine_similarity_not_probability',
                'species_margin': float(species_margin) if math.isfinite(species_margin) else None,
                'species_margin_type': 'cosine_margin_not_probability',
                'species_accepted': bool(species_accepted),
                'category': category_prediction if category_accepted else 'unknown',
                'category_prediction': category_prediction,
                'category_score': category_margin_value,
                'category_raw_score': category_value,
                'category_score_type': (
                    'cosine_margin_not_probability' if category_margin_value is not None else None),
                'category_accepted': bool(category_accepted),
                'uncertainty_reasons': reasons,
            })
        return results

    def classify(self, embeddings):
        """Compatibility triple: species, stage and cosine similarity score."""
        return [(row['species'], row['stage'], row['model_score'])
                for row in self.classify_detailed(embeddings)]
