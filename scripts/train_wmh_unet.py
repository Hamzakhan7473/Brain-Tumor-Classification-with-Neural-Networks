#!/usr/bin/env python3
"""
Train 3D U-Net for WMH segmentation (Kaggle farahmo/wmh-dataset layout).

Each case: ``training/**/pre/FLAIR.nii``, ``pre/T1.nii``, ``wmh.nii`` (binary mask after load).

Usage:
  export WMH_DATA_DIR="$HOME/.cache/kagglehub/datasets/farahmo/wmh-dataset/versions/1/wmh_data"
  # or: ln -sfn …/wmh_data data/wmh_kaggle

  python scripts/train_wmh_unet.py \\
    --config configs/model_wmh_unet.yaml \\
    --data-config configs/data_wmh_kaggle.yaml
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Train 3D U-Net (WMH segmentation, Kaggle layout)")
    parser.add_argument("--config", type=str, default=str(ROOT / "configs" / "model_wmh_unet.yaml"))
    parser.add_argument("--data-config", type=str, default=str(ROOT / "configs" / "data_wmh_kaggle.yaml"))
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="Override training.epochs from config (e.g. 3 for a quick demo screenshot).",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)
    if args.epochs is not None:
        config.setdefault("training", {})["epochs"] = int(args.epochs)

    paths = config.setdefault("paths", {})
    for key in ("save_best", "save_final", "checkpoint_dir"):
        if paths.get(key) and not Path(paths[key]).is_absolute():
            paths[key] = str(ROOT / paths[key])

    with open(args.data_config) as f:
        data_config = yaml.safe_load(f)

    vol = data_config.setdefault("volume", {})
    m = config["model"]
    vol["shape"] = list(m["input_shape"][:3])
    vol["channels"] = m["input_shape"][3]

    from src.data.dataset_wmh_kaggle import get_dataset_wmh_kaggle
    from src.training.train_seg import run_training_seg
    from models.unet3d import build_unet_3d

    train_ds = get_dataset_wmh_kaggle(data_config, "train")
    val_ds = get_dataset_wmh_kaggle(data_config, "validation")

    model = build_unet_3d(
        input_shape=tuple(m["input_shape"]),
        num_classes=m["num_classes"],
        base_filters=m.get("base_filters", 32),
        depth=m.get("depth", 4),
        name=m.get("name", "unet_3d_wmh"),
    )
    run_training_seg(model, train_ds, val_ds, config)


if __name__ == "__main__":
    main()
