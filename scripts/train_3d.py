#!/usr/bin/env python3
"""Train the 3D CNN on NIfTI volumes (BraTS-style layout)."""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Train 3D CNN on brain MRI volumes (NIfTI)")
    parser.add_argument("--config", type=str, default=str(ROOT / "configs" / "model_3d.yaml"))
    parser.add_argument("--data-config", type=str, default=str(ROOT / "configs" / "data_3d.yaml"))
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    paths = config.setdefault("paths", {})
    for key in ("save_best", "save_final", "checkpoint_dir"):
        if paths.get(key) and not Path(paths[key]).is_absolute():
            paths[key] = str(ROOT / paths[key])

    with open(args.data_config) as f:
        data_config = yaml.safe_load(f)

    from src.data.dataset_3d import get_dataset_3d
    from src.training.train import run_training
    from models.model_3d import build_3d_cnn

    train_ds = get_dataset_3d(data_config, "train")
    val_ds = get_dataset_3d(data_config, "validation")

    model = build_3d_cnn(
        input_shape=tuple(config["model"]["input_shape"]),
        num_classes=config["model"]["num_classes"],
        filters=tuple(config["model"]["filters"]),
        dense_units=tuple(config["model"]["dense_units"]),
        dropout=config["model"]["dropout"],
    )
    run_training(model, train_ds, val_ds, config)


if __name__ == "__main__":
    main()
