"""
Keras inference preprocessing — channels-last (N,H,W,C) / (N,D,H,W,C).

2D normalization matches training via src/data/dataset.py :: Rescaling(1/255) → ``div255``.

WMH volumes use the same per-modality pipeline as ``load_wmh_case`` (crop/pad +
``_normalize_modal``), duplicating single uploaded NIfTI for both FLAIR/T1 slots
when only one volume is uploaded.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, UnidentifiedImageError


def normalize(arr: np.ndarray, method: str) -> np.ndarray:
    """Apply normalization matching training where possible."""
    x = arr.astype(np.float32)
    if method == "div255":
        return x / 255.0

    if method == "imagenet":
        x = x / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        return (x - mean) / std

    if method == "keras_xception":
        return (x / 127.5) - 1.0

    if method == "zscore":
        mu = x.mean()
        sig = float(x.std())
        return (x - mu) / max(sig, 1e-8)

    if method == "minmax":
        lo, hi = float(x.min()), float(x.max())
        return (x - lo) / max(hi - lo, 1e-8)

    return x / 255.0


def load_2d(
    file_bytes: bytes,
    filename: str,
    target_h: int,
    target_w: int,
    channels: int,
    norm: str,
    content_type: Optional[str] = None,
) -> Tuple[np.ndarray, Optional[dict]]:
    """
    Load JPEG/PNG/DICOM → ndarray (1, H, W, C) float32 ready for predict.

    Returns (batch, optional_dicom_meta).
    """
    ext = Path(filename or "scan.jpg").suffix.lower()
    dicom_meta = None

    ct = (content_type or "").lower()
    if ext == ".dcm" or ext == ".dicom" or ct in ("application/dicom", "application/dicom+xml"):
        arr_2d, dicom_meta = _load_dicom_2d(file_bytes)
    else:
        try:
            arr_2d = _pil_to_hwc_gray_or_rgb(file_bytes, channels)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError(f"Invalid or unsupported raster image: {filename}") from exc

    pil_mode = "RGB" if channels == 3 else "L"
    if arr_2d.ndim != 2 and arr_2d.ndim != 3:
        raise ValueError(f"Unsupported array shape after decode: {arr_2d.shape}")

    img = Image.fromarray(arr_2d if arr_2d.dtype == np.uint8 else np.clip(arr_2d, 0, 255).astype(np.uint8)).convert(pil_mode)
    img = img.resize((target_w, target_h), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[:, :, np.newaxis]

    # div255/imagenet expect 0–255 scale before normalization
    if norm in ("div255", "imagenet", "keras_xception") and arr.max() <= 1.0 + 1e-6:
        arr = arr * 255.0

    if channels == 3 and arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)

    arr = normalize(arr, norm)
    return arr[np.newaxis, ...], dicom_meta


def _pil_to_hwc_gray_or_rgb(file_bytes: bytes, channels: int) -> np.ndarray:
    mode = "RGB" if channels == 3 else "L"
    img = Image.open(io.BytesIO(file_bytes)).convert(mode)
    return np.asarray(img, dtype=np.uint8)


def _load_dicom_2d(file_bytes: bytes) -> tuple[np.ndarray, dict]:
    """Window + HU rescale → uint8 grayscale for resizing."""
    import pydicom

    ds = pydicom.dcmread(io.BytesIO(file_bytes))
    pix = ds.pixel_array.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1.0))
    inter = float(getattr(ds, "RescaleIntercept", 0.0))
    pix = pix * slope + inter

    wc = getattr(ds, "WindowCenter", 40)
    ww = getattr(ds, "WindowWidth", 80)
    wc = float(wc[0] if hasattr(wc, "__iter__") and not isinstance(wc, (str, bytes)) else wc)
    ww = float(ww[0] if hasattr(ww, "__iter__") and not isinstance(ww, (str, bytes)) else ww)
    lo, hi = wc - ww / 2.0, wc + ww / 2.0
    pix = np.clip(pix, lo, hi)

    lo, hi = float(pix.min()), float(pix.max())
    pix_uint8 = ((pix - lo) / max(hi - lo, 1e-8) * 255.0).clip(0, 255).astype(np.uint8)

    meta = {
        "study_instance_uid": str(getattr(ds, "StudyInstanceUID", "") or ""),
        "series_instance_uid": str(getattr(ds, "SeriesInstanceUID", "") or ""),
        "sop_instance_uid": str(getattr(ds, "SOPInstanceUID", "") or ""),
    }
    return pix_uint8, meta


def load_wmh_nifti_dual_channel(
    file_bytes: bytes,
    filename: str,
    target_d: int,
    target_h: int,
    target_w: int,
) -> np.ndarray:
    """
    Upload one NIfTI → (1, D, H, W, 2) after crop/pad + per-channel ``_normalize_modal``,
    same as ``load_wmh_case`` modality branch. Second channel repeats the first
    when only one series is uploaded.
    """
    import tempfile

    import nibabel as nib

    from src.data.dataset_3d_seg import _crop_pad_volume, _normalize_modal

    target_shape = (target_d, target_h, target_w)
    suffix = ".nii.gz" if filename.lower().endswith(".gz") else ".nii"

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(file_bytes)
            tmp_path = f.name
        img = nib.load(tmp_path)
        vol = np.asarray(img.get_fdata(), dtype=np.float32)
        if vol.ndim > 3:
            vol = vol[..., 0]
        if vol.ndim != 3:
            raise ValueError(f"Expected 3D volume after squeeze, got {vol.shape}")

        ch = _normalize_modal(_crop_pad_volume(vol, target_shape))
        stacked = np.stack([ch, ch], axis=-1).astype(np.float32)
        return stacked[np.newaxis, ...]
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass
