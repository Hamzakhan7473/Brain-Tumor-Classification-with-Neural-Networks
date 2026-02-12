"""
Data augmentation pipelines for training (config-driven).
"""
from tensorflow import keras


def get_augmentation_layers(config: dict):
    """Build a keras.Sequential of augmentation layers from config."""
    aug_cfg = config.get("augmentation", {}).get("train", {})
    layers = [
        keras.layers.RandomFlip("horizontal" if aug_cfg.get("horizontal_flip", True) else None),
        keras.layers.RandomRotation(aug_cfg.get("rotation_range", 0.15) / 360.0),
        keras.layers.RandomZoom(aug_cfg.get("zoom_range", 0.1)),
    ]
    return keras.Sequential(layers, name="augmentation")
