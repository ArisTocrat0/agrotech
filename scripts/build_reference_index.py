import argparse
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import load_config, DEFAULT_CONFIG
from src.reference_index import build_reference_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cached DINOv2 references")
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/reference_index.pt"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    config = load_config(args.config)["model"]
    build_reference_index(args.references, args.output, config["name"], args.device, config["batch_size"], args.force)


if __name__ == "__main__":
    main()
