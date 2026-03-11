"""
Dataset loading and batching for brain MRI classification.
TensorFlow/Keras imported only inside functions that need them (avoids protobuf errors at app startup).

Supports two split strategies:
- Image-level (default): Keras validation_split over files; same patient can appear in train and test.
- Patient-level: when splits.patient_split is true and splits.metadata_file is set, splits by patient_id
  so the same patient never appears in more than one split (avoids data leakage).
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


def _get_patient_splits(config: dict):
    """
    Load metadata CSV and return train/val/test lists of (file_path, label_index).
    CSV must have columns: filename (path relative to raw_dir, e.g. glioma/img1.jpg), patient_id.
    Class is inferred from the first path component.
    """
    import pandas as pd
    from sklearn.model_selection import train_test_split

    raw_dir = _resolve_raw_dir(config)
    splits_config = config.get("splits", {})
    meta_path = splits_config.get("metadata_file")
    if not meta_path:
        return None
    path = Path(meta_path)
    if not path.is_absolute():
        path = _project_root() / path
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "filename" not in df.columns or "patient_id" not in df.columns:
        return None
    df["class"] = df["filename"].str.split("/").str[0].str.strip()
    classes = config.get("classes")
    if not classes:
        classes = sorted(df["class"].unique().tolist())
    class_to_idx = {c: i for i, c in enumerate(classes)}
    df["label_idx"] = df["class"].map(class_to_idx)
    df = df.dropna(subset=["label_idx"])
    # One row per patient: use first class (all slices of same patient typically same class)
    patient_label = df.groupby("patient_id")["label_idx"].first().reset_index()
    train_ratio = splits_config.get("train_ratio", 0.75)
    val_ratio = splits_config.get("val_ratio", 0.15)
    test_ratio = splits_config.get("test_ratio", 0.10)
    seed = splits_config.get("seed", 42)
    # Stratified split: first train vs rest, then val vs test
    train_patients, rest_patients = train_test_split(
        patient_label["patient_id"],
        test_size=1 - train_ratio,
        stratify=patient_label["label_idx"],
        random_state=seed,
    )
    n_rest = len(rest_patients)
    rest_df = patient_label[patient_label["patient_id"].isin(rest_patients)]
    val_ratio_adj = val_ratio / (val_ratio + test_ratio) if (val_ratio + test_ratio) > 0 else 0.5
    val_patients, test_patients = train_test_split(
        rest_df["patient_id"].tolist(),
        test_size=1 - val_ratio_adj,
        stratify=rest_df["label_idx"].values,
        random_state=seed,
    )
    out = {}
    for name, pid_list in (("train", train_patients), ("val", val_patients), ("test", test_patients)):
        files = df[df["patient_id"].isin(pid_list)]
        paths = [str(raw_dir / row["filename"]) for _, row in files.iterrows()]
        labels = files["label_idx"].values.astype(np.int32)
        out[name] = (paths, labels)
    return out


def get_dataset(config: dict, split: str):
    """
    Return a tf.data.Dataset for train/val/test.
    Expects raw_dir to contain class subfolders (e.g. glioma/, meningioma/, ...).
    If splits.patient_split is true and splits.metadata_file exists, splits by patient_id.
    Otherwise uses Keras validation_split (image-level).
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
    num_classes = len(classes) if classes else 4
    use_patient_split = config.get("splits", {}).get("patient_split", False)
    patient_splits = _get_patient_splits(config) if use_patient_split else None

    if patient_splits is not None:
        split_key = "train" if split == "train" else ("val" if split in ("validation", "val") else "test")
        paths, labels = patient_splits[split_key]
        if len(paths) == 0:
            raise ValueError(f"No samples in {split} split. Check metadata_file and patient_id assignments.")
        ds = _dataset_from_paths(paths, labels, target_size, batch_size, num_classes, shuffle=(split == "train"), seed=seed)
        if image_config.get("normalize", True):
            normalization = keras.layers.Rescaling(1.0 / 255.0)
            ds = ds.map(lambda x, y: (normalization(x), y), num_parallel_calls=None)
        return ds

    # Image-level split (original behavior)
    val_ratio = config.get("splits", {}).get("val_ratio", 0.15)
    validation_split = val_ratio
    if split == "train":
        subset = "training"
    elif split in ("validation", "val"):
        subset = "validation"
    elif split == "test":
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
    if image_config.get("normalize", True):
        normalization = keras.layers.Rescaling(1.0 / 255.0)
        ds = ds.map(lambda x, y: (normalization(x), y), num_parallel_calls=None)
    return ds


def _dataset_from_paths(paths, labels, target_size, batch_size, num_classes, shuffle=True, seed=42):
    """Build tf.data.Dataset from list of file paths and integer labels."""
    import tensorflow as tf

    def load_and_label(path, label):
        raw = tf.io.read_file(path)
        img = tf.io.decode_image(raw, channels=3, expand_animations=False)
        img = tf.image.resize(img, target_size)
        img.set_shape((target_size[0], target_size[1], 3))
        one_hot = tf.one_hot(label, depth=num_classes)
        return img, one_hot

    ds = tf.data.Dataset.from_tensor_slices((paths, labels))
    if shuffle:
        ds = ds.shuffle(buffer_size=len(paths), seed=seed)
    ds = ds.map(
        lambda p, l: load_and_label(p, l),
        num_parallel_calls=tf.data.AUTOTUNE,
    )
    ds = ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
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
