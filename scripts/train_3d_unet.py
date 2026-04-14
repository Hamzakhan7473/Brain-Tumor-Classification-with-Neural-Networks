#!/usr/bin/env python3
"""
Train 3D U-Net for brain tumor segmentation (BraTS-style data).

Inspired by: https://www.kaggle.com/code/rastislav/3d-mri-brain-tumor-segmentation-u-net

Data layout (per case folder under raw_dir):
  *_flair.nii.gz, *_t1.nii.gz, *_t1ce.nii.gz, *_t2.nii.gz, *_seg.nii.gz

Download BraTS or similar from Kaggle, unzip so each training case is one subfolder.

Usage:
  python scripts/train_3d_unet.py \\
    --config configs/model_3d_unet.yaml \\
    --data-config configs/data_3d_seg.yaml
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Train 3D U-Net (BraTS segmentation)")
    parser.add_argument("--config", type=str, default=str(ROOT / "configs" / "model_3d_unet.yaml"))
    parser.add_argument("--data-config", type=str, default=str(ROOT / "configs" / "data_3d_seg.yaml"))
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    paths = config.setdefault("paths", {})
    for key in ("save_best", "save_final", "checkpoint_dir"):
        if paths.get(key) and not Path(paths[key]).is_absolute():
            paths[key] = str(ROOT / paths[key])

    with open(args.data_config) as f:
        data_config = yaml.safe_load(f)

    # Align volume shape / channels with model
    vol = data_config.setdefault("volume", {})
    m = config["model"]
    vol["shape"] = list(m["input_shape"][:3])
    vol["channels"] = m["input_shape"][3]

    from src.data.dataset_3d_seg import get_dataset_3d_seg
    from src.training.train_seg import run_training_seg
    from models.unet3d import build_unet_3d

    train_ds = get_dataset_3d_seg(data_config, "train")
    val_ds = get_dataset_3d_seg(data_config, "validation")

    model = build_unet_3d(
        input_shape=tuple(m["input_shape"]),
        num_classes=m["num_classes"],
        base_filters=m.get("base_filters", 32),
        depth=m.get("depth", 4),
        name=m.get("name", "unet_3d"),
    )
    run_training_seg(model, train_ds, val_ds, config)


if __name__ == "__main__":
    main()
