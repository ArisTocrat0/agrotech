"""Offline benchmark of the real cached model, frame processing and result export."""
import argparse
import json
import math
import os
import platform
import socket
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--index', type=Path, default=ROOT/'artifacts/reference_index.pt')
    parser.add_argument('--config', type=Path, default=ROOT/'config.yaml')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--speed-kmh', type=float, default=20)
    parser.add_argument('--camera-to-nozzle-m', type=float)
    parser.add_argument('--actuator-ms', type=float, default=0)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/benchmark_pipeline.json')
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    # Fail on any attempted Python socket connection, including accidental downloads.
    def no_network(*args, **kwargs):
        raise RuntimeError('Network access is disabled during the offline benchmark')
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    from src.config import load_config
    from src.recognition.embeddings import DinoEmbeddingModel
    from src.recognition.classifier import ReferenceClassifier
    from src.application.inference import run_inference
    from src.domain.performance import motion_budget
    from src.vision.nms import kernel
    import torch
    motion_budget(0, args.speed_kmh, args.camera_to_nozzle_m, args.actuator_ms)
    config = load_config(args.config)
    startup = perf_counter()
    index = torch.load(args.index, map_location='cpu', weights_only=True)
    if index['metadata']['model_name'] != config['model']['name']:
        raise ValueError('Index and configured model do not match')
    model = DinoEmbeddingModel(config['model']['name'], args.device, config['model']['batch_size'], offline=True)
    classifier = ReferenceClassifier(index, config['classification']['top_k'],
                                     config['classification']['similarity_threshold'],
                                     config['classification'].get('category_margin', .05))
    startup_seconds = perf_counter() - startup
    batches, latencies = [], []
    with tempfile.TemporaryDirectory(prefix='agro-benchmark-') as temporary:
        output = Path(temporary)
        cold_start = perf_counter()
        cold_results = run_inference(args.input, output, config, model, classifier)
        cold_seconds = perf_counter() - cold_start
        frames = []
        for _ in range(args.repeats):
            started = perf_counter()
            rows = run_inference(args.input, output, config, model, classifier)
            batches.append(perf_counter() - started)
            latencies.extend(row['processing_seconds'] for row in rows)
            frames = [{'image': r['image'], 'width': r['width'], 'height': r['height'],
                       'candidates': r['total_candidates']} for r in rows]
    ordered = sorted(latencies)
    p95 = ordered[math.ceil(.95 * len(ordered)) - 1]
    report = {
        'scope': 'real DINOv2 + tiling + NMS + rows + annotation + disk export; no camera or actuator',
        'offline': True, 'python_socket_connections_disabled': True,
        'platform': platform.platform(), 'device': str(model.device),
        'torch_version': torch.__version__, 'torch_threads': torch.get_num_threads(),
        'native_nms': kernel() is not None, 'config': config,
        'model_startup_seconds': startup_seconds, 'cold_batch_seconds': cold_seconds,
        'repeats': args.repeats, 'frames': frames, 'samples': len(latencies),
        'median_frame_seconds': median(latencies), 'p95_frame_seconds': p95,
        'max_frame_seconds': max(latencies),
        'throughput_fps_including_export': len(frames) * args.repeats / sum(batches),
        'motion_p95': motion_budget(p95, args.speed_kmh, args.camera_to_nozzle_m, args.actuator_ms),
        'motion_max_including_cold': motion_budget(max(latencies + [r['processing_seconds'] for r in cold_results]),
                                                   args.speed_kmh, args.camera_to_nozzle_m, args.actuator_ms),
        'field_ready': False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
