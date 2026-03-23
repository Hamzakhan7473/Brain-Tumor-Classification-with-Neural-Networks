"""
3D volume dataset for brain MRI (NIfTI / BraTS-style).
Loads volumes from class/case_id/*.nii.gz, crops/pads to fixed shape, returns tf.data.Dataset.
Requires: nibabel (pip install nibabel).
"""
from pathlib import Path

import numpy as np


def _project_root():
    return Path(__file__).resolve().parents[2]


def _resolve_raw_dir(config: dict) -> Path:
    raw = config.get("dataset", {}).get("raw_dir", "data/raw_3d")
    path = Path(raw)
    if not path.is_absolute():
        path = _project_root() / path
    return path


def _find_volume_paths_and_labels(config: dict):
    """
    Scan raw_3d for structure: raw_3d/<class>/<case_id>/<any>.nii.gz.
    Returns list of (path_to_nifti, label_index).
    """
    raw_dir = _resolve_raw_dir(config)
    if not raw_dir.exists():
        return [], []

    classes = config.get("classes", ["glioma", "meningioma", "pituitary", "notumor"])
    class_to_idx = {c: i for i, c in enumerate(classes)}
    preferred = config.get("volume", {}).get("preferred_sequences", ["flair.nii.gz", "t2.nii.gz", "t1.nii.gz", "volume.nii.gz"])

    paths = []
    labels = []

    for class_name in classes:
        class_dir = raw_dir / class_name
        if not class_dir.is_dir():
            continue
        for case_dir in sorted(class_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            chosen = None
            for name in preferred:
                p = case_dir / name
                if p.exists():
                    chosen = p
                    break
            if chosen is None:
                for p in case_dir.glob("*.nii.gz"):
                    chosen = p
                    break
            if chosen is not None:
                paths.append(str(chosen))
                labels.append(class_to_idx[class_name])

    return paths, np.array(labels, dtype=np.int32)


def _load_nifti_volume(path: str, target_shape: tuple, normalize: bool = True) -> np.ndarray:
    """Load one NIfTI, crop/pad to target_shape (D,H,W), normalize. Returns (D,H,W,1)."""
    try:
        import nibabel as nib
    except ImportError:
        raise ImportError("Install nibabel for 3D NIfTI support: pip install nibabel")

    img = nib.load(path)
    vol = np.asarray(img.get_fdata(), dtype=np.float32)
    # Use first channel if 4D (time/sequence)
    if vol.ndim > 3:
        vol = vol[..., 0]
    if vol.ndim != 3:
        raise ValueError(f"Expected 3D volume, got shape {vol.shape} from {path}")

    # Crop or pad to target_shape
    d, h, w = target_shape
    D, H, W = vol.shape
    out = np.zeros((d, h, w), dtype=np.float32)
    md, mh, mw = min(d, D), min(h, H), min(w, W)
    # Center crop or pad
    start_d = max(0, (D - d) // 2)
    start_h = max(0, (H - h) // 2)
    start_w = max(0, (W - w) // 2)
    out[:md, :mh, :mw] = vol[start_d : start_d + md, start_h : start_h + mh, start_w : start_w + mw]

    if normalize:
        non_zero = out != 0
        if non_zero.any():
            mean, std = out[non_zero].mean(), out[non_zero].std()
            if std > 1e-8:
                out = (out - mean) / std
        out = np.clip(out, -3, 3)  # clip outliers
        out = (out - out.min()) / (out.max() - out.min() + 1e-8)  # 0-1

    return np.expand_dims(out, axis=-1)  # (D,H,W,1)


def get_dataset_3d(config: dict, split: str):
    """
    Return tf.data.Dataset for 3D volumes (train/val/test).
    Splits by image-level (or patient-level if metadata_file set) in same ratio as 2D.
    """
    paths, labels = _find_volume_paths_and_labels(config)
    if len(paths) == 0:
        raise FileNotFoundError(
            f"No 3D volumes found under {_resolve_raw_dir(config)}. "
            "Expect structure: raw_3d/<class>/<case_id>/flair.nii.gz (or t1/t2/volume.nii.gz). "
            "See data/README.md and docs/roadmap-research-to-hospital-grade.md for BraTS."
        )

    from sklearn.model_selection import train_test_split

    seed = config.get("splits", {}).get("seed", 42)
    train_ratio = config.get("splits", {}).get("train_ratio", 0.75)
    val_ratio = config.get("splits", {}).get("val_ratio", 0.15)
    test_ratio = config.get("splits", {}).get("test_ratio", 0.10)

    # Stratified split: train / rest
    train_paths, rest_paths, train_labels, rest_labels = train_test_split(
        paths, labels, train_size=train_ratio, stratify=labels, random_state=seed
    )
    val_ratio_adj = val_ratio / (val_ratio + test_ratio) if (val_ratio + test_ratio) > 0 else 0.5
    val_paths, test_paths, val_labels, test_labels = train_test_split(
        rest_paths, rest_labels, train_size=val_ratio_adj, stratify=rest_labels, random_state=seed
    )

    if split == "train":
        p, l = train_paths, train_labels
    elif split in ("validation", "val"):
        p, l = val_paths, val_labels
    else:
        p, l = test_paths, test_labels

    if len(p) == 0:
        raise ValueError(f"No samples in 3D {split} split.")

    vol_config = config.get("volume", {})
    target_shape = tuple(vol_config.get("shape", [96, 96, 96]))
    normalize = vol_config.get("normalize", True)
    num_classes = len(config.get("classes", 4))
    batch_size = config.get("batch_size", 4)

    import tensorflow as tf

    def gen():
        for path, label in zip(p, l):
            vol = _load_nifti_volume(path, target_shape, normalize=normalize)
            one_hot = np.eye(num_classes, dtype=np.float32)[label]
            yield vol, one_hot

    output_signature = (
        tf.TensorSpec(shape=tuple(target_shape) + (1,), dtype=tf.float32),
        tf.TensorSpec(shape=(num_classes,), dtype=tf.float32),
    )
    ds = tf.data.Dataset.from_generator(
        gen,
        output_signature=output_signature,
    )
    if split == "train":
        ds = ds.shuffle(buffer_size=min(256, len(p) * 2), seed=seed)
    ds = ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
    return ds
