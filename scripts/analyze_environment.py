"""Isolated job worker; never downloads weights or calls external services."""
import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def processing_timeout(signum, frame):
    raise TimeoutError('Лимит обработки: 15 минут.')


def main():
    from src.environment.model import LocalYoloDetector
    from src.environment.pipeline import analyze
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    # Cooperative POSIX deadline. Python may defer it during a native C call;
    # this is not a hard wall-clock guarantee for a stalled decoder/model.
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, processing_timeout)
        signal.alarm(900)
    manifest = json.loads((args.job / 'manifest.json').read_text(encoding='utf-8'))
    detector = LocalYoloDetector(manifest['options']['confidence'])
    result = analyze(args.job, manifest, detector)
    print(f"Environmental analysis: {result['status']}; {len(result['events'])} unreviewed hypotheses.")


if __name__ == '__main__':
    main()
