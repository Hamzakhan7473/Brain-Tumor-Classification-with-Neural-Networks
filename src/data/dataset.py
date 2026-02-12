"""
Dataset loading and batching for brain MRI classification.
"""
import os
from pathlib import Path

import numpy as np
from tensorflow import keras


def get_dataset(config: dict, split: str):
    """
    Return a tf.data.Dataset or keras.utils.image_dataset_from_directory
    for train/val/test according to config.
    """
    raw_dir = Path(config.get("raw_dir", "data/raw"))
    target_size = tuple(config.get("image", {}).get("target_size", [224, 224]))
    batch_size = config.get("batch_size", 32)
    seed = config.get("splits", {}).get("seed", 42)
    classes = config.get("classes")
    # If you have fixed split dirs (e.g. data/raw/train, val, test), use them:
    split_dir = raw_dir / split if (raw_dir / split).exists() else raw_dir
    subset = split if split in ("train", "validation") else None
    validation_split = None
    if not (raw_dir / "train").exists() and split == "train":
        validation_split = (0.15, 0.75)  # (val_ratio, train_ratio) placeholder
    ds = keras.utils.image_dataset_from_directory(
        split_dir,
        labels="inferred",
        label_mode="categorical" if classes else "int",
        class_names=classes,
        image_size=target_size,
        batch_size=batch_size,
        shuffle=(split == "train"),
        seed=seed,
        subset=subset,
        validation_split=validation_split,
    )
    return ds


def load_image_for_inference(image_path: str, target_size=(224, 224), normalize: bool = True):
    """Load and preprocess a single image for inference."""
    from tensorflow.keras.preprocessing import image

    img = image.load_img(image_path, target_size=target_size)
    arr = image.img_to_array(img)
    arr = np.expand_dims(arr, axis=0)
    if normalize:
        arr = arr / 255.0
    return arr
