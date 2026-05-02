"""
Inference-time preprocessing — delegates to the same helpers as training-time inference
(`load_image_from_bytes`, `load_dicom_slice`) so shapes and scaling match `src/inference/predict.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np


def build_inference_batch(
    *,
    bytes_data: bytes,
    filename: str,
    content_type: str,
    model_name: str,
    project_root: Path,
    input_sizes: Dict[str, Tuple[int, int]],
) -> Tuple[np.ndarray, Optional[dict], Dict[str, Any]]:
    """
    Build a single batch (N,H,W,C) float32 in [0,1] for the named model.

    Returns:
        batch: ndarray shape (1, H, W, 3)
        dicom_meta: dict or None
        infer_meta: input_shape list, preprocessing_applied strings
    """
    size = input_sizes.get(model_name, (224, 224))
    h, w = int(size[0]), int(size[1])
    shape_list = [1, h, w, 3]

    fn = (filename or "image.jpg").lower()
    is_dicom = fn.endswith(".dcm") or fn.endswith(".dicom") or (content_type or "").lower() in (
        "application/dicom",
        "application/dicom+xml",
    )

    if is_dicom:
        pre_list = ["dicom_decode", f"resize_{h}x{w}", "minmax_unit_interval", "stack_rgb"]
        from src.data.dicom_loader import load_dicom_slice

        batch, dicom_meta = load_dicom_slice(bytes_data, target_size=(h, w), normalize=True)
    else:
        pre_list = ["pil_rgb_decode", f"resize_{h}x{w}", "div_255"]
        dicom_meta = None
        from src.data.dataset import load_image_from_bytes

        batch = load_image_from_bytes(bytes_data, target_size=(h, w), normalize=True)

    infer_meta: Dict[str, Any] = {
        "input_shape": shape_list,
        "preprocessing_applied": pre_list,
    }
    return batch, dicom_meta, infer_meta
