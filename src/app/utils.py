"""App utilities: config loading, project path."""
import sys
from pathlib import Path

import yaml


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_project_in_path():
    root = project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def load_app_config():
    ensure_project_in_path()
    config_path = project_root() / "configs" / "app.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def load_data_config():
    ensure_project_in_path()
    config_path = project_root() / "configs" / "data.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def get_class_names() -> list:
    """Class names for display (from data config)."""
    config = load_data_config()
    return config.get("classes", ["glioma", "meningioma", "no_tumor", "pituitary"])
