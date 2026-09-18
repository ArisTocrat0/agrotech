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


def _fallback_predictions(classifier, embeddings):
    rows = []
    for species, stage, score in classifier.classify(embeddings):
        predicted_kind = getattr(classifier, "species_kinds", {}).get(species)
        rows.append({
            'species': species,
            'species_prediction': species if species != 'unknown' else None,
            'stage': stage,
            'model_score': score,
            'score_type': 'model_score',
            'species_accepted': species != 'unknown',
            'category': predicted_kind or ('unknown' if species == 'unknown' else 'weed'),
            'category_prediction': predicted_kind,
            'category_score': None,
            'category_score_type': None,
            'category_accepted': species != 'unknown' and predicted_kind in {'weed', 'crop'},
            'uncertainty_reasons': [] if species != 'unknown' else ['low_species_confidence'],
        })
    return rows


def _uncertainty_message(code, crop=None):
    messages = {
        'unsupported_crop': (f'Нет обучающих примеров выбранной культуры «{crop}»: '
                             'вид растения сохранён, но категория «сорняк/культура» не подтверждена.'),
        'insufficient_calibration_data': 'Недостаточно validation-данных для калибровки порога вида.',
        'species_calibration_unavailable': 'Порог принятия вида не откалиброван на validation.',
        'low_species_margin': 'Разница между лучшими вариантами вида ниже откалиброванного порога.',
        'insufficient_category_calibration': 'Недостаточно validation-данных для калибровки категории.',
        'category_calibration_unavailable': 'Порог категории «сорняк/культура» не откалиброван.',
        'low_category_margin': 'Категория «сорняк/культура» неоднозначна.',
        'low_species_confidence': 'Модель не приняла предсказание вида.',
    }
    return messages.get(code, code)


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
        timings = {
            'image_load_seconds': 0., 'vegetation_mask_seconds': 0.,
            'candidate_extraction_seconds': 0., 'crop_preparation_seconds': 0.,
            'preprocessing_seconds': 0., 'dinov2_seconds': 0.,
            'embedding_total_seconds': 0., 'classification_seconds': 0.,
            'nms_seconds': 0., 'row_estimation_seconds': 0.,
            'annotation_export_seconds': 0.,
        }
        stage_started = perf_counter()
        image = load_image_rgb(path)
        timings['image_load_seconds'] = perf_counter() - stage_started
        name = path.name if input_path.is_file() else path.relative_to(input_path).as_posix()
        detections = []
        pending = []
        seen_boxes = set()
        for tile in iter_tiles(image, **config["tiling"]):
            stage_started = perf_counter()
            mask = detector.mask(tile.image)
            timings['vegetation_mask_seconds'] += perf_counter() - stage_started
            stage_started = perf_counter()
            candidates = detector.candidates(mask)
            timings['candidate_extraction_seconds'] += perf_counter() - stage_started
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
                stage_started = perf_counter()
                crop = candidate_crop(tile.image, c, config["classification"]["crop_padding"])
                timings['crop_preparation_seconds'] += perf_counter() - stage_started
                c.tile_id = tile.tile_id
                pending.append((c, crop, tile.offset_x, tile.offset_y))
                if save_debug and debug_crops < config["debug"]["max_crops"]:
                    crop.save(debug_dir/f"crop_{debug_crops}.png")
                    debug_crops += 1

        crop = config.get('crop')
        crop_species = (config.get('learning_report') or {}).get('crop_species', [])
        crop_supported = not crop or crop in crop_species
        if crop and not crop_supported:
            logging.warning(
                'Нет обучающих данных культуры %s; вид будет распознаваться отдельно, '
                'а категория сорняк/культура останется неопределённой.', crop)

        stage_started = perf_counter()
        embeddings = model.encode([item[1] for item in pending])
        timings['embedding_total_seconds'] = perf_counter() - stage_started
        profile = getattr(model, 'last_profile', {}) or {}
        timings['preprocessing_seconds'] = float(profile.get('preprocessing_seconds', 0.))
        timings['dinov2_seconds'] = float(profile.get('model_seconds', 0.))

        stage_started = perf_counter()
        if hasattr(classifier, 'classify_detailed'):
            predictions = classifier.classify_detailed(embeddings)
        else:
            predictions = _fallback_predictions(classifier, embeddings)
        timings['classification_seconds'] = perf_counter() - stage_started

        for (c, _crop, offset_x, offset_y), prediction in zip(pending, predictions):
            species = prediction.get('species', 'unknown')
            species_prediction = prediction.get('species_prediction') or (
                species if species != 'unknown' else None)
            predicted_kind = prediction.get('category_prediction')
            kind = prediction.get('category', 'unknown')
            category_accepted = bool(prediction.get('category_accepted'))
            reasons = list(dict.fromkeys(prediction.get('uncertainty_reasons') or []))

            if crop:
                if not crop_supported:
                    kind = 'unknown'
                    category_accepted = False
                    if 'unsupported_crop' not in reasons:
                        reasons.append('unsupported_crop')
                elif kind == 'crop' and species != 'unknown' and species != crop:
                    # A confidently identified different crop is volunteer crop in the
                    # selected field context. Preserve the raw model category separately.
                    species = 'Падалица ' + species.lower()
                    kind = 'weed'

            detection = WeedDetection(
                0, species, prediction.get('stage', 'unknown'),
                float(prediction.get('model_score', 0.)),
                c.x1+offset_x, c.y1+offset_y, c.x2+offset_x, c.y2+offset_y, kind)
            detection.species_prediction = species_prediction
            detection.species_accepted = bool(prediction.get('species_accepted', species != 'unknown'))
            detection.model_score = float(prediction.get('model_score', 0.))
            detection.score_type = prediction.get('score_type', 'model_score')
            detection.category_prediction = predicted_kind
            detection.category_score = prediction.get('category_score')
            detection.category_score_type = prediction.get('category_score_type')
            detection.category_accepted = category_accepted
            detection.uncertainty_reasons = reasons
            detection.uncertainty_messages = [_uncertainty_message(code, crop) for code in reasons]
            detection.prediction_status = (
                'recognized' if species != 'unknown' and kind in {'weed', 'crop'} else 'uncertain')
            detection.stage_status = (
                'known' if detection.stage != 'unknown' else 'unknown_untrained')
            detections.append(detection)

        stage_started = perf_counter()
        detections = nms(detections, **config["nms"])
        timings['nms_seconds'] = perf_counter() - stage_started
        result = image_result(name, image.width, image.height, detections)
        if crop:
            result['mode'] = 'automatic'
            result['crop'] = crop
            result['learning_report'] = config.get('learning_report')
            result['crop_supported'] = crop_supported
            result['manual_review_required'] = False
            result['analysis_status'] = 'complete'
            result['unsupported_crop_message'] = (
                None if crop_supported else _uncertainty_message('unsupported_crop', crop))
        stage_started = perf_counter()
        result['rows'] = estimate_rows(image,detector)
        timings['row_estimation_seconds'] = perf_counter() - stage_started
        result['gsd_cm'] = config.get('gsd_cm')
        recount(result)
        result['analysis_seconds'] = perf_counter()-started
        target = output/"annotated"/Path(name + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage_started = perf_counter()
        annotate(image, detections).save(target)
        timings['annotation_export_seconds'] = perf_counter() - stage_started
        result['processing_seconds'] = perf_counter()-started
        result['performance'] = {
            'scope': 'image_load_through_annotation_save_excludes_model_startup_and_final_json_csv_export',
            'fps': 1 / result['processing_seconds'],
            'motion_at_18_kmh': motion_budget(result['processing_seconds'], 18),
            'motion_at_20_kmh': motion_budget(result['processing_seconds'], 20),
            'timings': timings,
        }
        results.append(result)
        logging.info("%s: %d candidates, %.2fs", name, len(detections), result['processing_seconds'])
    save_results(results, output)
    return results
