"""
DICOM ingestion for brain MRI.
Reads DICOM (single image or series), extracts pixel array, and returns
a numpy array suitable for the existing 2D classifier (H, W, 3) normalized.
Phase 1 of roadmap: DICOM in/out before 3D segmentation.
"""
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np


def load_dicom_slice(
    path_or_bytes: Union[str, Path, bytes],
    frame_index: Optional[int] = None,
    target_size: Tuple[int, int] = (224, 224),
    normalize: bool = True,
) -> Tuple[np.ndarray, Optional[dict]]:
    """
    Load one or more frames from a DICOM file and return one slice as (1, H, W, 3) float32.

    - If single frame: use it. If multi-frame: use frame_index (default middle).
    - Grayscale is converted to 3 channels (stack).
    - Resized to target_size and normalized to [0, 1] if normalize=True.
    - Returns (array, metadata_dict). metadata_dict includes SeriesInstanceUID, SOPInstanceUID,
      and Modality when available (for logging); None if read fails.
    """
    try:
        import pydicom
    except ImportError:
        raise ImportError("pydicom is required for DICOM support. Install with: pip install pydicom")

    if isinstance(path_or_bytes, bytes):
        import io
        ds = pydicom.dcmread(io.BytesIO(path_or_bytes))
    else:
        path = Path(path_or_bytes)
        if not path.exists():
            return np.zeros((1, *target_size, 3), dtype=np.float32), None
        ds = pydicom.dcmread(str(path))

    meta = {}
    try:
        if hasattr(ds, "SeriesInstanceUID"):
            meta["SeriesInstanceUID"] = str(ds.SeriesInstanceUID)
        if hasattr(ds, "SOPInstanceUID"):
            meta["SOPInstanceUID"] = str(ds.SOPInstanceUID)
        if hasattr(ds, "Modality"):
            meta["Modality"] = str(ds.Modality)
    except Exception:
        pass

    pix = ds.pixel_array
    if pix is None:
        return np.zeros((1, *target_size, 3), dtype=np.float32), meta

    # Multi-frame: (N, H, W) or (N, H, W, C)
    if pix.ndim == 3:
        n_frames = pix.shape[0]
        idx = frame_index if frame_index is not None else n_frames // 2
        idx = max(0, min(idx, n_frames - 1))
        pix = pix[idx]
    elif pix.ndim == 4:
        n_frames = pix.shape[0]
        idx = frame_index if frame_index is not None else n_frames // 2
        idx = max(0, min(idx, n_frames - 1))
        pix = pix[idx]
        if pix.ndim == 3:
            pix = pix[..., 0] if pix.shape[-1] >= 1 else pix.mean(axis=-1)

    # 2D grayscale -> normalize and stack to 3 channels
    if pix.ndim != 2:
        pix = np.asarray(pix).squeeze()
        if pix.ndim != 2:
            pix = pix[0] if pix.ndim == 3 else pix.mean(axis=0)

    pmin, pmax = pix.min(), pix.max()
    if pmax > pmin:
        pix = (pix.astype(np.float32) - pmin) / (pmax - pmin)
    else:
        pix = np.zeros_like(pix, dtype=np.float32)
    # (H, W) -> (H, W, 3)
    pix = np.stack([pix, pix, pix], axis=-1)

    # Resize to target_size
    from PIL import Image
    img = Image.fromarray((pix * 255).astype(np.uint8))
    img = img.resize((target_size[1], target_size[0]), Image.Resampling.BILINEAR)
    pix = np.asarray(img, dtype=np.float32) / 255.0

    if normalize:
        pix = np.clip(pix, 0.0, 1.0).astype(np.float32)
    batch = np.expand_dims(pix, axis=0)
    return batch, meta


def load_dicom_series_to_slice(
    paths: list,
    slice_index: Optional[int] = None,
    target_size: Tuple[int, int] = (224, 224),
    normalize: bool = True,
) -> Tuple[np.ndarray, Optional[dict]]:
    """
    Load a list of DICOM paths (one series), pick one slice (default middle),
    return (1, H, W, 3) and metadata from that slice.
    """
    if not paths:
        return np.zeros((1, *target_size, 3), dtype=np.float32), None
    # Use middle path as representative slice
    idx = slice_index if slice_index is not None else len(paths) // 2
    idx = max(0, min(idx, len(paths) - 1))
    return load_dicom_slice(paths[idx], frame_index=0, target_size=target_size, normalize=normalize)
