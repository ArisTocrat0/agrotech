import hashlib
import logging
from pathlib import Path
from ..vision.image_utils import image_paths, load_image_rgb

PREPROCESS_VERSION = "rgb-exif-square224-v1"


def _record_key(row):
    return (row["sha256"], row["species"], row["stage"], row.get("kind", "weed"))


def build_reference_index(references: Path, output: Path, model_name: str,
                          device: str = "auto", batch_size: int = 16, force: bool = False,
                          model=None, crop_references: Path | None = None) -> dict:
    import torch
    from ..recognition.embeddings import DinoEmbeddingModel

    records = []
    roots = [(references, 'weed')]
    if crop_references and crop_references.exists():
        roots.append((crop_references, 'crop'))

    # Production data/ may be read-only. High-confidence field experience is written
    # to artifacts/experience and participates in matching on the next analysis.
    experience_root = output.parent / "experience"
    experience_weeds = experience_root / "Сорняки"
    experience_crops = experience_root / "Культуры"
    if experience_weeds.exists():
        roots.append((experience_weeds, 'weed'))
    if experience_crops.exists():
        roots.append((experience_crops, 'crop'))
    for root, kind in roots:
        for path in image_paths(root):
            relative = path.relative_to(root)
            if len(relative.parts) < 3:
                logging.warning("Skipping reference without species/stage: %s", path)
                continue
            records.append({"image_path":str(path.resolve()), "species":relative.parts[0],
                            "stage":relative.parts[1], "kind":kind,
                            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    if not records:
        raise ValueError(f"No references in species/stage folders: {references}")

    metadata = {"model_name": model_name, "preprocess": PREPROCESS_VERSION, "records": records}
    cached = None
    if output.exists() and not force:
        try:
            cached = torch.load(output, map_location="cpu", weights_only=True)
            if cached.get("metadata") == metadata:
                logging.info("Using cached reference index: %s", output)
                return cached
        except (OSError, RuntimeError, ValueError, EOFError):
            cached = None
            logging.warning("Cannot read index; rebuilding %s", output)

    model = model or DinoEmbeddingModel(model_name, device, batch_size)
    vectors = [None] * len(records)
    reused = 0

    # Field experience adds a few references after every analysis. Reuse embeddings
    # for unchanged files and encode only the new examples instead of rebuilding all
    # 10k+ references.
    if cached is not None and not force:
        old_meta = cached.get("metadata") or {}
        old_records = old_meta.get("records") or []
        old_embeddings = cached.get("embeddings")
        compatible = (
            old_meta.get("model_name") == model_name and
            old_meta.get("preprocess") == PREPROCESS_VERSION and
            old_embeddings is not None and len(old_embeddings) == len(old_records)
        )
        if compatible:
            old_by_key = {_record_key(row): i for i, row in enumerate(old_records)}
            old_embeddings = old_embeddings.to(model.device, non_blocking=True)
            for i, row in enumerate(records):
                old_i = old_by_key.get(_record_key(row))
                if old_i is not None:
                    vectors[i] = old_embeddings[old_i]
                    reused += 1

    missing = [i for i, vector in enumerate(vectors) if vector is None]
    if reused:
        logging.info("Reference index: reused %d embeddings; encoding %d new images.",
                     reused, len(missing))

    for start in range(0, len(missing), batch_size):
        ids = missing[start:start+batch_size]
        images = [load_image_rgb(Path(records[i]["image_path"])) for i in ids]
        encoded = model.encode(images)
        for index, vector in zip(ids, encoded):
            vectors[index] = vector

    result = {"metadata": metadata, "embeddings": torch.stack(vectors)}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    torch.save(result, temporary)
    temporary.replace(output)
    return result
