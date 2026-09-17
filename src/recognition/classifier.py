"""Batched reference matching with an ambiguity guard between crops and weeds."""
from collections import defaultdict


class ReferenceClassifier:
    def __init__(self, index, top_k=5, similarity_threshold=0.55, category_margin=0.05):
        if top_k < 1 or not -1 <= similarity_threshold <= 1:
            raise ValueError('Invalid classification settings')
        self.embeddings = index['embeddings']
        self.top_k, self.threshold = top_k, similarity_threshold
        self.category_margin = category_margin
        self.groups = defaultdict(list)
        self.species_kinds = {}
        for i, row in enumerate(index['metadata']['records']):
            self.groups[(row['species'],row['stage'])].append(i)
            self.species_kinds[row['species']] = row.get('kind','weed')

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
        crop_ids = [i for i,key in enumerate(keys) if self.species_kinds[key[0]] == 'crop']
        weed_ids = [i for i,key in enumerate(keys) if self.species_kinds[key[0]] == 'weed']
        ambiguous = torch.zeros(len(embeddings),dtype=torch.bool)
        if crop_ids and weed_ids:
            ambiguous = (scores[:,crop_ids].max(dim=1).values-scores[:,weed_ids].max(dim=1).values).abs() < self.category_margin
        results = []
        for score, idx, unclear in zip(best_scores.tolist(),best_ids.tolist(),ambiguous.tolist()):
            species, stage = keys[idx]
            if score < self.threshold or unclear:
                species = stage = 'unknown'
            results.append((species,stage,score))
        return results
