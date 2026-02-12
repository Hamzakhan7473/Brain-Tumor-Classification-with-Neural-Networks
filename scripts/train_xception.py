#!/usr/bin/env python3
"""Train the Xception model."""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=str(ROOT / "configs" / "xception.yaml"))
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    data_path = ROOT / "configs" / "data.yaml"
    with open(data_path) as f:
        data_config = yaml.safe_load(f)

    from src.data.dataset import get_dataset
    from src.training.train import run_training
    from models.xception_model import build_xception

    train_ds = get_dataset(data_config, "train")
    val_ds = get_dataset(data_config, "validation")

    model = build_xception(
        input_shape=tuple(config["model"]["input_shape"]),
        num_classes=config["model"]["num_classes"],
        trainable_layers=config["model"]["trainable_layers"],
        dropout=config["model"]["dropout"],
        pooling=config["model"]["pooling"],
    )
    run_training(model, train_ds, val_ds, config)


if __name__ == "__main__":
    main()
