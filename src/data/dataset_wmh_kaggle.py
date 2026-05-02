"""
WMH segmentation — Kaggle layout (farahmo/wmh-dataset style).

Expects each case folder under ``training/`` (relative to dataset root) with:
  - ``pre/FLAIR.nii``, ``pre/T1.nii`` (registered/resampled volumes)
  - ``wmh.nii`` (label volume; values 0,1,2,... — collapsed to binary {0,1} for foreground WMH)

Set ``WMH_DATA_DIR`` to an absolute path to override ``dataset.raw_dir`` (e.g. Kaggle Hub cache).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from src.data.dataset_3d_seg import _crop_pad_volume, _normalize_modal


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_wmh_root(config: dict) -> Path:
    env = os.environ.get("WMH_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    raw = config.get("dataset", {}).get("raw_dir", "data/wmh_kaggle")
    path = Path(raw)
    if not path.is_absolute():
        path = _project_root() / path
    return path.resolve()


def _find_training_cases(root: Path) -> list[Path]:
    """Leaf case dirs containing ``wmh.nii`` and ``pre/FLAIR.nii``."""
    sub = config_training_subdir(root)
    if not sub.exists():
        return []
    cases: list[Path] = []
    for wmh in sub.rglob("wmh.nii"):
        case_dir = wmh.parent
        flair = case_dir / "pre" / "FLAIR.nii"
        t1 = case_dir / "pre" / "T1.nii"
        if flair.is_file() and t1.is_file():
            cases.append(case_dir)
    # Deduplicate (rglob shouldn't duplicate, but be safe)
    uniq = sorted(set(cases), key=lambda p: str(p))
    return uniq


def config_training_subdir(root: Path) -> Path:
    """``training/`` under WMH root, or ``root`` if it already looks like training tree."""
    train = root / "training"
    if train.is_dir():
        return train
    return root


def load_wmh_case(case_dir: Path, target_shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns x (D,H,W,2) float32 — FLAIR + T1; y (D,H,W) int32 labels in {0,1} (binary WMH).
    """
    try:
        import nibabel as nib
    except ImportError as e:
        raise ImportError("pip install nibabel") from e

    flair_p = case_dir / "pre" / "FLAIR.nii"
    t1_p = case_dir / "pre" / "T1.nii"
    mask_p = case_dir / "wmh.nii"
    if not (flair_p.is_file() and t1_p.is_file() and mask_p.is_file()):
        raise FileNotFoundError(case_dir)

    vols = []
    for p in (flair_p, t1_p):
        img = nib.load(str(p))
        arr = np.asarray(img.get_fdata(), dtype=np.float32)
        if arr.ndim > 3:
            arr = arr[..., 0]
        vols.append(_normalize_modal(_crop_pad_volume(arr, target_shape)))

    x = np.stack(vols, axis=-1).astype(np.float32)

    simg = nib.load(str(mask_p))
    seg = np.asarray(simg.get_fdata(), dtype=np.float32)
    if seg.ndim > 3:
        seg = seg[..., 0]
    seg = _crop_pad_volume(seg, target_shape)
    # Binary WMH: any non-zero label -> 1 (MICCAI-style masks may use 1 vs 2 for subtypes)
    y = (seg > 0.5).astype(np.int32)
    return x, y


def get_dataset_wmh_kaggle(config: dict, split: str):
    """
    tf.data.Dataset yielding (volume, sparse_labels) for binary WMH (classes 0–1).
    Scans only the ``training/`` subtree; splits cases train/val/test by ``splits`` ratios.
    """
    root = _resolve_wmh_root(config)
    cases = _find_training_cases(root)
    if not cases:
        raise FileNotFoundError(
            f"No WMH cases under {root / 'training'}. "
            "Expected Kaggle layout: training/**/pre/FLAIR.nii, pre/T1.nii, wmh.nii. "
            "Set WMH_DATA_DIR or symlink data/wmh_kaggle → …/wmh_data."
        )

    from sklearn.model_selection import train_test_split

    seed = config.get("splits", {}).get("seed", 42)
    train_ratio = config.get("splits", {}).get("train_ratio", 0.75)
    val_ratio = config.get("splits", {}).get("val_ratio", 0.15)
    test_ratio = config.get("splits", {}).get("test_ratio", 0.10)

    case_paths = [str(c) for c in cases]
    train_c, rest = train_test_split(case_paths, train_size=train_ratio, random_state=seed)
    val_ratio_adj = val_ratio / (val_ratio + test_ratio) if (val_ratio + test_ratio) > 0 else 0.5
    val_c, test_c = train_test_split(rest, train_size=val_ratio_adj, random_state=seed)

    if split == "train":
        use = train_c
    elif split in ("validation", "val"):
        use = val_c
    else:
        use = test_c

    if not use:
        raise ValueError(f"No cases in split {split}")

    vol_cfg = config.get("volume", {})
    target_shape = tuple(vol_cfg.get("shape", [96, 96, 96]))
    ch = int(vol_cfg.get("channels", 2))
    batch_size = config.get("batch_size", 1)

    import tensorflow as tf

    def gen():
        for cdir in use:
            try:
                x, y = load_wmh_case(Path(cdir), target_shape)
                yield x, y
            except Exception:
                continue

    ds = tf.data.Dataset.from_generator(
        gen,
        output_signature=(
            tf.TensorSpec(shape=target_shape + (ch,), dtype=tf.float32),
            tf.TensorSpec(shape=target_shape, dtype=tf.int32),
        ),
    )
    if split == "train":
        ds = ds.shuffle(buffer_size=min(32, len(use) * 2), seed=seed, reshuffle_each_iteration=True)
    ds = ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
    return ds
