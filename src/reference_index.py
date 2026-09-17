import hashlib
import logging
from pathlib import Path
from .image_utils import image_paths, load_image_rgb

PREPROCESS_VERSION = "rgb-exif-square224-v1"


def build_reference_index(references: Path, output: Path, model_name: str,
                          device: str = "auto", batch_size: int = 16, force: bool = False,
                          model=None) -> dict:
    import torch
    from .embeddings import DinoEmbeddingModel
    records = []
    for path in image_paths(references):
        relative = path.relative_to(references)
        if len(relative.parts) < 3:
            logging.warning("Skipping reference without species/stage: %s", path)
            continue
        records.append({"image_path": str(path.resolve()), "species": relative.parts[0],
                        "stage": relative.parts[1], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not records:
        raise ValueError(f"No references in species/stage folders: {references}")
    metadata = {"model_name": model_name, "preprocess": PREPROCESS_VERSION, "records": records}
    if output.exists() and not force:
        try:
            cached = torch.load(output, map_location="cpu", weights_only=True)
            if cached.get("metadata") == metadata:
                logging.info("Using cached reference index: %s", output)
                return cached
        except (OSError, RuntimeError, ValueError, EOFError):
            logging.warning("Cannot read index; rebuilding %s", output)
    model = model or DinoEmbeddingModel(model_name, device, batch_size)
    chunks = []
    for start in range(0, len(records), batch_size):
        images = [load_image_rgb(Path(r["image_path"])) for r in records[start:start+batch_size]]
        chunks.append(model.encode(images))
    result = {"metadata": metadata, "embeddings": torch.cat(chunks)}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    torch.save(result, temporary)
    temporary.replace(output)
    return result
