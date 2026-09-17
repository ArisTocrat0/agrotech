from dataclasses import dataclass


@dataclass
class DetectionCandidate:
    x1: int
    y1: int
    x2: int
    y2: int
    tile_id: int = 0
    source: str = "vegetation"


@dataclass
class WeedDetection:
    id: int
    species: str
    stage: str
    similarity_score: float
    x1: int
    y1: int
    x2: int
    y2: int
    kind: str = ""
