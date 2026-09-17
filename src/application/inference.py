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


def run_inference(input_path: Path, output: Path, config: dict, model, classifier, debug: bool = False) -> list[dict]:
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
        # Encode across tile boundaries so sparse tiles do not produce many tiny GPU
        # launches. DinoEmbeddingModel still chunks this list to the configured batch.
        predictions = classifier.classify(model.encode([item[1] for item in pending]))
        for (c, _crop, offset_x, offset_y), (species, stage, score) in zip(pending, predictions):
            detections.append(WeedDetection(0, species, stage, score, c.x1+offset_x,
                                           c.y1+offset_y, c.x2+offset_x, c.y2+offset_y,
                                           getattr(classifier,"species_kinds",{}).get(species,"")))
        detections = nms(detections, **config["nms"])
        result = image_result(name, image.width, image.height, detections)
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
        logging.info("%s: %d candidates, %.2fs", name, len(detections), result['processing_seconds'])
    save_results(results, output)
    return results
