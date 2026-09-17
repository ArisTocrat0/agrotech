from pathlib import Path
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1]/"config.yaml"


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Config must be a mapping")
    for section in ["model", "tiling", "vegetation", "classification", "nms", "debug"]:
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Missing config section: {section}")
    return config
