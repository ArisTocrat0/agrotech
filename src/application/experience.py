"""Persistent experience gathered from field analyses.

High-confidence automatic examples are promoted to the local reference dataset. Human
review can promote corrected examples too. The reference index reuses cached embeddings,
so adding experience does not require re-encoding the whole library.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

AUTO_STAGE = "Автоопыт"
MAX_AUTO_PER_SPECIES = 300


def _safe_component(value: str) -> str:
    value = (value or "").strip()
    if not value or value in {".", ".."} or any(c in value for c in "/\\"):
        raise ValueError("Invalid experience label")
    return value[:100]


def _png_bytes(image: Image.Image) -> bytes:
    data = BytesIO()
    image.convert("RGB").save(data, format="PNG")
    return data.getvalue()


def remember_exemplar(root: Path, image: Image.Image, kind: str, species: str,
                      score: float | None, source: str = "automatic") -> bool:
    """Save one deduplicated exemplar into data/ so the next index build can reuse it."""
    if kind not in {"weed", "crop"}:
        return False
    if not species or species == "unknown":
        return False

    species = _safe_component(species)
    # data/ is commonly mounted read-only in production. Keep learned field
    # experience under artifacts/, which is the writable persistent model volume.
    base = root / "artifacts" / "experience" / ("Сорняки" if kind == "weed" else "Культуры")
    folder = base / species / AUTO_STAGE

    payload = _png_bytes(image)
    digest = hashlib.sha256(payload).hexdigest()
    target = folder / f"{digest}.png"

    try:
        folder.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return False

        # Avoid unbounded self-training growth. Human-labelled exemplars are allowed even
        # after the automatic quota because they are more valuable than pseudo labels.
        if source != "human" and sum(1 for p in folder.glob("*.png") if p.is_file()) >= MAX_AUTO_PER_SPECIES:
            return False

        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
    except OSError as exc:
        logging.warning("Cannot persist field experience %s/%s: %s", kind, species, exc)
        return False

    log = root / "artifacts" / "experience_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "species": species,
        "stage": AUTO_STAGE,
        "score": score,
        "source": source,
        "sha256": digest,
        "path": str(target.relative_to(root)),
    }
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
    return True


def save_unresolved_review(root: Path, image: Image.Image, decision: str) -> bool:
    """Keep reviewed kind-only examples without polluting species training labels."""
    if decision not in {"weed", "crop"}:
        return False
    payload = _png_bytes(image)
    digest = hashlib.sha256(payload).hexdigest()
    folder = root / "artifacts" / "experience_kind" / decision
    target = folder / f"{digest}.png"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return False
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
        return True
    except OSError as exc:
        logging.warning("Cannot persist reviewed kind example %s: %s", decision, exc)
        return False
