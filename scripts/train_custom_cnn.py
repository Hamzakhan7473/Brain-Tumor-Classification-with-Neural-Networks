#!/usr/bin/env python3
"""Train the custom CNN (Challenge 1)."""
import argparse
import sys
from pathlib import Path

import yaml

# Add project root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=str(ROOT / "configs" / "custom_cnn.yaml"))
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    # Resolve save paths relative to project root
    paths = config.setdefault("paths", {})
    for key in ("save_best", "save_final", "checkpoint_dir"):
        if paths.get(key) and not Path(paths[key]).is_absolute():
            paths[key] = str(ROOT / paths[key])

    # Load data config
    data_path = ROOT / "configs" / "data.yaml"
    with open(data_path) as f:
        data_config = yaml.safe_load(f)

    from src.data.dataset import get_dataset
    from src.training.train import run_training
    from models.custom_cnn import build_custom_cnn

    train_ds = get_dataset(data_config, "train")
    val_ds = get_dataset(data_config, "validation")

    model = build_custom_cnn(
        input_shape=tuple(config["model"]["input_shape"]),
        num_classes=config["model"]["num_classes"],
        filters=tuple(config["model"]["filters"]),
        dense_units=tuple(config["model"]["dense_units"]),
        dropout=config["model"]["dropout"],
    )
    run_training(model, train_ds, val_ds, config)


if __name__ == "__main__":
    main()
