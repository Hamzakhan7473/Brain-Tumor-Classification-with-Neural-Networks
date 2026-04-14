"""
3D multimodal MRI + segmentation masks (BraTS-style layout).
Aligned with common Kaggle notebooks: 4 modalities + *_seg.nii.gz, label remap 0,1,2,4 → 0–3.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np


def _project_root():
    return Path(__file__).resolve().parents[2]


def _resolve_raw_dir(config: dict) -> Path:
    raw = config.get("dataset", {}).get("raw_dir", "data/raw_3d_seg")
    path = Path(raw)
    if not path.is_absolute():
        path = _project_root() / path
    return path


def remap_brats_seg_labels(seg: np.ndarray) -> np.ndarray:
    """
    BraTS mask values: 0 background, 1 NCR/NET, 2 ED, 4 ET → dense 0..3.
    """
    seg = np.asarray(seg, dtype=np.int32)
    out = np.zeros_like(seg, dtype=np.int32)
    out[seg == 1] = 1
    out[seg == 2] = 2
    out[seg == 4] = 3
    return out


def _find_seg_file(case_dir: Path) -> Optional[Path]:
    for pat in ("*_seg.nii.gz", "*_seg.nii", "seg.nii.gz"):
        found = sorted(case_dir.glob(pat))
        if found:
            return found[0]
    return None


def _find_modality_paths(case_dir: Path) -> Optional[list[str]]:
    """BraTS-style filenames inside one case folder."""
    globs = ("*_flair.nii.gz", "*_t1.nii.gz", "*_t1ce.nii.gz", "*_t2.nii.gz")
    paths = []
    for g in globs:
        m = sorted(case_dir.glob(g))
        if not m:
            return None
        # *_t1.nii.gz must not be t1ce
        if g == "*_t1.nii.gz":
            m = [p for p in m if "t1ce" not in p.name.lower()]
            if not m:
                return None
        paths.append(str(m[0]))
    return paths


def _list_case_dirs(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    out = []
    for d in sorted(raw_dir.iterdir()):
        if not d.is_dir():
            continue
        if _find_seg_file(d) is None:
            continue
        if _find_modality_paths(d) is None:
            continue
        out.append(d)
    return out


def _crop_pad_volume(vol: np.ndarray, target_shape: tuple[int, int, int]) -> np.ndarray:
    """vol: (D,H,W) or (D,H,W,C) — crop/pad center to target_shape (D,H,W)."""
    d, h, w = target_shape
    if vol.ndim == 3:
        D, H, W = vol.shape
        out = np.zeros((d, h, w), dtype=np.float32)
        c = 1
    else:
        D, H, W, C = vol.shape
        out = np.zeros((d, h, w, C), dtype=np.float32)
        c = vol.shape[-1]

    md, mh, mw = min(d, D), min(h, H), min(w, W)
    sd = max(0, (D - d) // 2)
    sh = max(0, (H - h) // 2)
    sw = max(0, (W - w) // 2)
    dd = max(0, (d - D) // 2)
    dh = max(0, (h - H) // 2)
    dw = max(0, (w - W) // 2)

    if vol.ndim == 3:
        out[dd : dd + md, dh : dh + mh, dw : dw + mw] = vol[sd : sd + md, sh : sh + mh, sw : sw + mw]
    else:
        out[dd : dd + md, dh : dh + mh, dw : dw + mw, :] = vol[sd : sd + md, sh : sh + mh, sw : sw + mw, :]
    return out


def _normalize_modal(vol_ch: np.ndarray) -> np.ndarray:
    """Per-volume z-score on non-zero voxels, then clip + scale to [0,1] (same idea as dataset_3d)."""
    v = vol_ch.astype(np.float32)
    nz = v != 0
    if nz.any():
        mu, sig = v[nz].mean(), v[nz].std()
        if sig > 1e-8:
            v = (v - mu) / sig
        v = np.clip(v, -3, 3)
    vmin, vmax = v.min(), v.max()
    v = (v - vmin) / (v.max() - vmin + 1e-8)
    return v


def load_brats_case(
    case_dir: Path,
    target_shape: tuple[int, int, int],
    num_modalities: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns x (D,H,W,4) float32, y (D,H,W) int32 labels."""
    try:
        import nibabel as nib
    except ImportError as e:
        raise ImportError("pip install nibabel") from e

    mod_paths = _find_modality_paths(case_dir)
    seg_path = _find_seg_file(case_dir)
    if not mod_paths or seg_path is None:
        raise FileNotFoundError(case_dir)

    vols = []
    for p in mod_paths[:num_modalities]:
        img = nib.load(p)
        arr = np.asarray(img.get_fdata(), dtype=np.float32)
        if arr.ndim > 3:
            arr = arr[..., 0]
        vols.append(_normalize_modal(_crop_pad_volume(arr, target_shape)))

    x = np.stack(vols, axis=-1)

    simg = nib.load(str(seg_path))
    seg = np.asarray(simg.get_fdata(), dtype=np.int32)
    if seg.ndim > 3:
        seg = seg[..., 0]
    seg = _crop_pad_volume(seg.astype(np.float32), target_shape).astype(np.int32)
    y = remap_brats_seg_labels(seg)
    return x.astype(np.float32), y


def get_dataset_3d_seg(config: dict, split: str):
    """
    tf.data.Dataset yielding (volume, sparse_labels).
    Expects: dataset.raw_dir with BraTS-style case folders (4 modalities + seg).
    """
    raw_dir = _resolve_raw_dir(config)
    cases = _list_case_dirs(raw_dir)
    if not cases:
        raise FileNotFoundError(
            f"No BraTS-style cases under {raw_dir}. "
            "Each case folder needs *_flair.nii.gz, *_t1.nii.gz, *_t1ce.nii.gz, *_t2.nii.gz, *_seg.nii.gz. "
            "See Kaggle: rastislav/3d-mri-brain-tumor-segmentation-u-net (BraTS)."
        )

    from sklearn.model_selection import train_test_split

    seed = config.get("splits", {}).get("seed", 42)
    train_ratio = config.get("splits", {}).get("train_ratio", 0.75)
    val_ratio = config.get("splits", {}).get("val_ratio", 0.15)
    test_ratio = config.get("splits", {}).get("test_ratio", 0.10)

    case_paths = [str(c) for c in cases]
    # No stratify by class (segmentation); random split of cases
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
    num_modalities = int(vol_cfg.get("channels", 4))
    batch_size = config.get("batch_size", 1)

    import tensorflow as tf

    def gen():
        for cdir in use:
            try:
                x, y = load_brats_case(Path(cdir), target_shape, num_modalities=num_modalities)
                yield x, y
            except Exception:
                continue

    ds = tf.data.Dataset.from_generator(
        gen,
        output_signature=(
            tf.TensorSpec(shape=target_shape + (num_modalities,), dtype=tf.float32),
            tf.TensorSpec(shape=target_shape, dtype=tf.int32),
        ),
    )
    if split == "train":
        ds = ds.shuffle(buffer_size=min(64, len(use) * 2), seed=seed, reshuffle_each_iteration=True)
    ds = ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
    return ds
