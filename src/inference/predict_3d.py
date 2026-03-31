"""
3D volume inference for brain MRI (NIfTI).
Loads a saved Keras 3D CNN and predicts on a single volume.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _models_dir(project_root: Optional[Path] = None) -> Path:
    root = project_root or _project_root()
    override = (os.environ.get("MODEL_DIR_3D") or os.environ.get("MODEL_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    return root / "models" / "saved"


MODEL_PATHS_3D = {
    "cnn_3d_best": "models/saved/cnn_3d_best.keras",
    "cnn_3d_final": "models/saved/cnn_3d_final.keras",
}


def get_model_path_3d(model_name: str, project_root: Optional[Path] = None) -> Optional[Path]:
    root = project_root or _project_root()
    rel = MODEL_PATHS_3D.get(model_name)
    if rel:
        p = root / rel
        return p if p.exists() else None

    # allow by-stem discovery in models dir
    models_dir = _models_dir(root)
    for ext in (".keras", ".h5"):
        candidate = models_dir / f"{model_name}{ext}"
        if candidate.exists():
            return candidate
    return None


def list_available_models_3d(project_root: Optional[Path] = None) -> list[str]:
    root = project_root or _project_root()
    available: set[str] = set()
    for k in MODEL_PATHS_3D.keys():
        if get_model_path_3d(k, root) is not None:
            available.add(k)

    models_dir = _models_dir(root)
    if models_dir.exists():
        for p in models_dir.iterdir():
            if p.is_file() and p.suffix.lower() in (".keras", ".h5") and "3d" in p.stem.lower():
                available.add(p.stem)
    return sorted(available)


def _load_model_3d(model_name: str, project_root: Optional[Path] = None):
    path = get_model_path_3d(model_name, project_root)
    if path is None:
        return None
    from tensorflow import keras

    return keras.models.load_model(str(path))


def predict_volume_from_bytes(
    *,
    model_name: str,
    volume_bytes: bytes,
    filename: str,
    class_names: list[str],
    target_shape: Tuple[int, int, int] = (96, 96, 96),
    project_root: Optional[Path] = None,
) -> tuple[Optional[str], Optional[float], Optional[dict]]:
    """
    Predict on a single NIfTI volume.
    Returns (label, confidence, probabilities_dict) or (None,None,None) if model missing.
    """
    model = _load_model_3d(model_name, project_root)
    if model is None:
        return None, None, None

    # Reuse dataset 3D loader (expects file path), so write to a temp file.
    import tempfile

    suffix = ".nii.gz" if filename.lower().endswith(".nii.gz") else ".nii"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(volume_bytes)
        tmp.flush()
        from src.data.dataset_3d import _load_nifti_volume

        vol = _load_nifti_volume(tmp.name, target_shape=target_shape, normalize=True)  # (D,H,W,1)

    batch = np.expand_dims(vol, axis=0)
    probs = model.predict(batch, verbose=0)[0]
    idx = int(np.argmax(probs))
    label = class_names[idx] if class_names else str(idx)
    conf = float(probs[idx])
    prob_dict = {class_names[i]: float(probs[i]) for i in range(len(class_names))}
    return label, conf, prob_dict

