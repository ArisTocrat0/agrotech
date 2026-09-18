import argparse
import logging
import os
from pathlib import Path
from src.config import load_config, DEFAULT_CONFIG
from src.image_utils import image_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Olzha Agro: weed candidates with DINOv2")
    parser.add_argument("--crop", choices=("Пшеница", "Ячмень", "Подсолнечник"),
                        help="Deprecated hint; crop is inferred automatically and never blocks weed search.")
    parser.add_argument("--references", type=Path, default=Path("data/Сорняки"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--tile-size", type=int)
    parser.add_argument("--overlap", type=float)
    parser.add_argument("--similarity-threshold", type=float)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--gsd-cm", type=float)
    parser.add_argument("--online", action="store_true", help="Allow the initial model download")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if not args.online:
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = load_config(args.config)
    config["gsd_cm"] = args.gsd_cm
    # Manual crop selection is kept only for backward-compatible CLI/API calls.
    # Inference chooses crop context automatically and never gates weed recognition on it.
    config["crop_hint"] = args.crop
    config["crop"] = None
    for key, value in [("tile_size", args.tile_size), ("overlap", args.overlap)]:
        if value is not None:
            config["tiling"][key] = value
    if args.batch_size is not None:
        if not 1 <= args.batch_size <= 128:
            parser.error("Batch size must be between 1 and 128")
        config["model"]["batch_size"] = args.batch_size
    if args.similarity_threshold is not None:
        config["classification"]["similarity_threshold"] = args.similarity_threshold
    if not image_paths(args.input) or not image_paths(args.references):
        parser.error("Input images and species/stage reference images are required")

    from src.embeddings import DinoEmbeddingModel
    from src.reference_index import build_reference_index
    from src.classifier import (
        ReferenceClassifier,
        CropContextClassifier,
        index_for_kind,
    )
    from src.inference import run_inference

    m = config["model"]
    model = DinoEmbeddingModel(m["name"], args.device, m["batch_size"], offline=not args.online)
    index = build_reference_index(
        args.references,
        Path("artifacts/reference_index.pt"),
        m["name"],
        args.device,
        m["batch_size"],
        model=model,
        crop_references=Path("data/Культуры"),
    )

    # Cached indexes are intentionally loaded on CPU for portability. Matching is a
    # large matrix multiplication, so move it once instead of moving every query.
    index['embeddings'] = index['embeddings'].to(model.device, non_blocking=True)

    # Restore the old useful behavior: weed labels are learned/matched only against
    # weed references. Crop examples can no longer steal the best class or force all
    # candidates to unknown.
    weed_index = index_for_kind(index, 'weed')
    classifier = ReferenceClassifier(
        weed_index,
        config["classification"]["top_k"],
        config["classification"]["similarity_threshold"],
        config['classification'].get('category_margin', 0.05),
    )

    crop_classifier = None
    if any(row.get('kind') == 'crop' for row in index['metadata']['records']):
        crop_classifier = CropContextClassifier(
            index,
            config["classification"]["similarity_threshold"],
            config['classification'].get('category_margin', 0.05),
        )
        logging.info(
            "Культура определяется автоматически как контекст; основной поиск использует только эталоны сорняков."
        )
    else:
        logging.info("Эталонов культур нет; поиск сорняков всё равно выполняется.")

    run_inference(
        args.input,
        args.output,
        config,
        model,
        classifier,
        args.debug,
        crop_classifier=crop_classifier,
    )


if __name__ == "__main__":
    main()
