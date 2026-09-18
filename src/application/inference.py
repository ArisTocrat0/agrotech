import logging
from time import perf_counter
from pathlib import Path
from PIL import Image, ImageDraw
from ..vision.image_utils import image_paths, load_image_rgb, candidate_crop
from ..vision.tiling import iter_tiles
from ..domain.types import WeedDetection
from ..vision.vegetation import VegetationDetector
from ..vision.nms import nms
from ..infrastructure.exporters import image_result, save_results
from ..vision.visualization import annotate
from ..vision.rows import estimate_rows
from ..infrastructure.exporters import recount
from ..domain.performance import motion_budget


def run_inference(input_path: Path, output: Path, config: dict, model, classifier,
                  debug: bool = False, crop_classifier=None) -> list[dict]:
    paths = image_paths(input_path)
    if not paths:
        raise ValueError(f"No input images: {input_path}")
    results = []
    detector = VegetationDetector(config["vegetation"])
    debug_tiles = debug_crops = 0
    for path in paths:
        logging.info("Processing %s", path)
        started = perf_counter()
        image = load_image_rgb(path)
        name = path.name if input_path.is_file() else path.relative_to(input_path).as_posix()
        detections = []
        pending = []
        seen_boxes = set()
        for tile in iter_tiles(image, **config["tiling"]):
            mask = detector.mask(tile.image)
            candidates = detector.candidates(mask)
            unique = []
            for candidate in candidates:
                key = (candidate.x1+tile.offset_x,candidate.y1+tile.offset_y,
                       candidate.x2+tile.offset_x,candidate.y2+tile.offset_y)
                if key not in seen_boxes:
                    seen_boxes.add(key)
                    unique.append(candidate)
            candidates = unique
            save_debug = debug and debug_tiles < config["debug"]["max_tiles"]
            if save_debug:
                debug_dir = output/"debug"/str(debug_tiles)
                debug_dir.mkdir(parents=True, exist_ok=True)
                tile.image.save(debug_dir/"tile.png")
                Image.fromarray(mask).save(debug_dir/"mask.png")
                components = tile.image.copy()
                draw = ImageDraw.Draw(components)
                for c in candidates:
                    draw.rectangle((c.x1, c.y1, c.x2-1, c.y2-1), outline="red", width=2)
                components.save(debug_dir/"components.png")
                debug_tiles += 1
            for c in candidates:
                crop = candidate_crop(tile.image, c, config["classification"]["crop_padding"])
                c.tile_id = tile.tile_id
                pending.append((c, crop, tile.offset_x, tile.offset_y))
                if save_debug and debug_crops < config["debug"]["max_crops"]:
                    crop.save(debug_dir/f"crop_{debug_crops}.png")
                    debug_crops += 1

        # Encode candidates once. Crop recognition is only a context/filter and can
        # never suppress weed classification globally.
        embeddings = model.encode([item[1] for item in pending])
        predictions = classifier.classify(embeddings)

        crop_context = (crop_classifier.classify(embeddings)
                        if crop_classifier is not None else
                        [(False, None, None, None) for _ in pending])
        inferred_crop, inferred_crop_score = (
            crop_classifier.infer_crop(embeddings)
            if crop_classifier is not None else (None, None)
        )

        from .experience import remember_exemplar
        auto_learn_threshold = max(
            0.75,
            float(config["classification"]["similarity_threshold"]) + 0.10,
        )
        ignored_crops = 0
        learned_weed_examples = 0
        learned_crop_examples = 0
        review_required_by_box = {}
        for (c, crop_image, offset_x, offset_y), (species, stage, score), crop_info in zip(
                pending, predictions, crop_context):
            is_crop, crop_species, crop_score, _weed_score = crop_info
            box = (c.x1+offset_x, c.y1+offset_y, c.x2+offset_x, c.y2+offset_y)
            if is_crop:
                ignored_crops += 1
                if crop_score is not None and crop_score >= auto_learn_threshold:
                    learned_crop_examples += int(remember_exemplar(
                        Path(__file__).resolve().parents[2],
                        crop_image,
                        "crop",
                        crop_species,
                        crop_score,
                    ))
                continue
            kind = getattr(classifier, "species_kinds", {}).get(species, "")
            confident = (
                kind == "weed" and
                species != "unknown" and
                score is not None and
                score >= auto_learn_threshold
            )
            if confident:
                learned_weed_examples += int(remember_exemplar(
                    Path(__file__).resolve().parents[2],
                    crop_image,
                    "weed",
                    species,
                    score,
                ))
            review_required_by_box[box] = not confident
            detections.append(WeedDetection(
                0, species, stage, score,
                *box,
                kind,
            ))

        detections = nms(detections, **config["nms"])
        result = image_result(name, image.width, image.height, detections)

        # Automatic crop is informational only. The weed classifier does not contain
        # crop classes and does not depend on this result.
        result['mode'] = 'weed_first'
        result['crop'] = inferred_crop
        result['crop_score'] = inferred_crop_score
        result['crop_source'] = 'automatic_context' if inferred_crop else 'not_detected'
        result['ignored_crop_candidates'] = ignored_crops
        result['crop_supported'] = bool(inferred_crop)
        result['learning_report'] = config.get('learning_report')
        for row in result['detections']:
            row['decision_source'] = 'weed_only_reference_match'
            row['score_type'] = 'cosine_similarity'
            b = row['bbox']
            box = (b['x1'], b['y1'], b['x2'], b['y2'])
            row['review_required'] = review_required_by_box.get(box, True)
            row['auto_learned'] = not row['review_required']
        result['auto_learned_weeds'] = learned_weed_examples
        result['auto_learned_crops'] = learned_crop_examples
        result['review_required_count'] = sum(
            bool(row.get('review_required')) for row in result['detections']
        )
        if inferred_crop:
            logging.info(
                "Автовыбор культуры: %s (score=%.4f); культурных кандидатов проигнорировано: %d",
                inferred_crop, inferred_crop_score, ignored_crops,
            )
        elif crop_classifier is not None:
            logging.info("Культура автоматически не определена; поиск сорняков продолжается без неё.")

        result['rows'] = estimate_rows(image,detector)
        result['gsd_cm'] = config.get('gsd_cm')
        recount(result)
        result['analysis_seconds'] = perf_counter()-started
        target = output/"annotated"/Path(name + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        annotate(image, detections).save(target)
        result['processing_seconds'] = perf_counter()-started
        result['performance'] = {
            'scope': 'image_load_through_annotation_save_excludes_model_startup_and_final_export',
            'fps': 1 / result['processing_seconds'],
            'motion_at_18_kmh': motion_budget(result['processing_seconds'], 18),
            'motion_at_20_kmh': motion_budget(result['processing_seconds'], 20),
        }
        results.append(result)
        logging.info(
            "%s: %d weed/unknown candidates, %d crop candidates ignored, %d new weed examples, %d new crop examples, %d require review, %.2fs",
            name, len(detections), ignored_crops, learned_weed_examples,
            learned_crop_examples, result['review_required_count'],
            result['processing_seconds'],
        )
    save_results(results, output)
    return results
