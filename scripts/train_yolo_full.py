"""Train a validated YOLO detection dataset on CUDA."""
import argparse
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate_dataset(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not config.get("names"):
        raise ValueError("dataset.yaml must define non-empty names")
    if not config.get("train") or not config.get("val"):
        raise ValueError("dataset.yaml must define train and val")
    base = Path(config.get("path", path.parent))
    if not base.is_absolute():
        base = (path.parent / base).resolve()
    train = (base / config["train"]).resolve()
    val = (base / config["val"]).resolve()
    if train == val:
        raise ValueError("train and val must be different; evaluation leakage is forbidden")
    for split, folder in (("train", train), ("val", val)):
        if not folder.exists():
            raise ValueError(f"{split} images do not exist: {folder}")
        label_folder = Path(str(folder).replace("/images/", "/labels/"))
        labels = list(label_folder.rglob("*.txt")) if label_folder.exists() else []
        if not labels or not any(item.read_text(encoding="utf-8").strip() for item in labels):
            raise ValueError(f"{split} has no non-empty YOLO labels: {label_folder}")
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Full GPU YOLO training with split validation")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--model", default=str(ROOT / "artifacts/yolo11n.pt"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=-1, help="-1 lets Ultralytics fit the GPU")
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--name", default="agrotech_yolo")
    args = parser.parse_args()
    if args.epochs < 1 or args.imgsz < 128 or args.workers < 0 or args.patience < 0:
        parser.error("invalid training limits")
    data = args.data.resolve()
    validate_dataset(data)
    model_path = Path(args.model)
    if not model_path.exists():
        raise ValueError(f"model weights do not exist: {model_path}")

    config_dir = ROOT / "outputs" / "yolo_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["YOLO_CONFIG_DIR"] = str(config_dir)
    os.environ["MPLCONFIGDIR"] = str(config_dir / "matplotlib")
    os.environ["YOLO_AUTOINSTALL"] = "false"

    import torch
    from ultralytics import YOLO, settings
    if args.device != "cpu" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    for key in ("sync", "wandb", "mlflow", "clearml", "comet", "neptune"):
        if key in settings:
            settings.update({key: False})
    model = YOLO(str(model_path))
    model.train(
        data=str(data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=args.device, workers=args.workers, patience=args.patience,
        project=str(ROOT / "outputs" / "yolo_training"), name=args.name,
        exist_ok=False, seed=42, deterministic=True, amp=True, cache=False,
        pretrained=True, save=True, val=True, plots=True, close_mosaic=10,
    )


if __name__ == "__main__":
    main()
