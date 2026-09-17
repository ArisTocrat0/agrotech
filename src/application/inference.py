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
            for start in range(0, len(candidates), model.batch_size):
                batch = candidates[start:start+model.batch_size]
                crops = [candidate_crop(tile.image, c, config["classification"]["crop_padding"]) for c in batch]
                predictions = classifier.classify(model.encode(crops))
                for c, crop, (species, stage, score) in zip(batch, crops, predictions):
                    c.tile_id = tile.tile_id
                    detections.append(WeedDetection(0, species, stage, score, c.x1+tile.offset_x,
                                                   c.y1+tile.offset_y, c.x2+tile.offset_x, c.y2+tile.offset_y,
                                                   getattr(classifier,"species_kinds",{}).get(species,"")))
                    if save_debug and debug_crops < config["debug"]["max_crops"]:
                        crop.save(debug_dir/f"crop_{debug_crops}.png")
                        debug_crops += 1
        detections = nms(detections, **config["nms"])
        result = image_result(name, image.width, image.height, detections)
        result['rows'] = estimate_rows(image,detector)
        result['gsd_cm'] = config.get('gsd_cm')
        recount(result)
        result['processing_seconds'] = round(perf_counter()-started,3)
        results.append(result)
        logging.info("%s: %d candidates, %.2fs", name, len(detections), result['processing_seconds'])
        target = output/"annotated"/Path(name + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        annotate(image, detections).save(target)
    save_results(results, output)
    return results
