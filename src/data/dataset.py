"""
Dataset loading and batching for brain MRI classification.
TensorFlow/Keras imported only inside functions that need them (avoids protobuf errors at app startup).
"""
from pathlib import Path

import numpy as np


def _project_root():
    """Project root (parent of src)."""
    return Path(__file__).resolve().parents[2]


def _resolve_raw_dir(config: dict) -> Path:
    raw = config.get("dataset", {}).get("raw_dir", "data/raw")
    path = Path(raw)
    if not path.is_absolute():
        path = _project_root() / path
    return path


def get_dataset(config: dict, split: str):
    """
    Return a tf.data.Dataset for train/val/test.
    Expects raw_dir to contain class subfolders (e.g. glioma/, meningioma/, ...).
    Uses validation_split for train/validation; for 'test' returns validation subset.
    """
    from tensorflow import keras

    raw_dir = _resolve_raw_dir(config)
    if not raw_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {raw_dir}. Download the dataset first (see data/README.md).")

    image_config = config.get("image", {})
    target_size = tuple(image_config.get("target_size", [224, 224]))
    batch_size = config.get("batch_size", 32)
    seed = config.get("splits", {}).get("seed", 42)
    classes = config.get("classes")
    val_ratio = config.get("splits", {}).get("val_ratio", 0.15)
    # Keras: validation_split is the fraction reserved for validation (e.g. 0.2 = 20% val)
    validation_split = val_ratio

    if split == "train":
        subset = "training"
    elif split in ("validation", "val"):
        subset = "validation"
    elif split == "test":
        # Use same validation subset as test if no separate test split
        subset = "validation"
    else:
        subset = None
        validation_split = None

    ds = keras.utils.image_dataset_from_directory(
        str(raw_dir),
        labels="inferred",
        label_mode="categorical",
        class_names=classes,
        image_size=target_size,
        batch_size=batch_size,
        shuffle=(split == "train"),
        seed=seed,
        subset=subset,
        validation_split=validation_split,
    )

    # Normalize to [0, 1]
    if image_config.get("normalize", True):
        normalization = keras.layers.Rescaling(1.0 / 255.0)
        ds = ds.map(lambda x, y: (normalization(x), y), num_parallel_calls=None)

    return ds


def load_image_for_inference(image_path: str, target_size=(224, 224), normalize: bool = True):
    """Load and preprocess a single image from file path for inference."""
    from PIL import Image

    img = Image.open(image_path).convert("RGB").resize(target_size)
    arr = np.asarray(img, dtype=np.float32)
    arr = np.expand_dims(arr, axis=0)
    if normalize:
        arr = arr / 255.0
    return arr.astype(np.float32)


def load_image_from_bytes(image_bytes: bytes, target_size=(224, 224), normalize: bool = True):
    """Load and preprocess an image from bytes (e.g. Streamlit upload) for inference."""
    import io
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize(target_size)
    arr = np.asarray(img, dtype=np.float32)
    arr = np.expand_dims(arr, axis=0)
    if normalize:
        arr = arr / 255.0
    return arr.astype(np.float32)
