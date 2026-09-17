from collections import defaultdict


class ReferenceClassifier:
    def __init__(self, index: dict, top_k: int = 5, similarity_threshold: float = 0.55):
        if top_k < 1 or not -1 <= similarity_threshold <= 1:
            raise ValueError("Invalid classification settings")
        self.embeddings = index["embeddings"]
        self.top_k, self.threshold = top_k, similarity_threshold
        self.groups = defaultdict(list)
        for i, row in enumerate(index["metadata"]["records"]):
            self.groups[(row["species"], row["stage"])].append(i)

    def classify(self, embeddings) -> list[tuple[str, str, float]]:
        similarities = embeddings @ self.embeddings.T
        results = []
        for row in similarities:
            scores = [(float(row[indices].topk(min(self.top_k, len(indices))).values.mean()), key)
                      for key, indices in self.groups.items()]
            score, (species, stage) = max(scores)
            if score < self.threshold:
                species = stage = "unknown"
            results.append((species, stage, score))
        return results
