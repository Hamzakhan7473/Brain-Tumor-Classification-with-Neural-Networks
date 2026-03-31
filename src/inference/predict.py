"""
Load saved models and run prediction on single or batch images.
Supports different input sizes per model (224 for custom_cnn/transfer, 299 for Xception).
TensorFlow is imported lazily to avoid protobuf version errors at app startup.
"""
import os
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _models_dir(project_root: Optional[Path] = None) -> Path:
    root = project_root or _project_root()
    # Allow overriding location for deployments / experiments
    override = (os.environ.get("MODEL_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    return root / "models" / "saved"


MODEL_PATHS = {
    "custom_cnn": "models/saved/custom_cnn_best.keras",
    "xception": "models/saved/xception_best.keras",
    "transfer": "models/saved/transfer_best.keras",
}

# Input shape (height, width) per model for preprocessing
MODEL_INPUT_SIZES = {
    "custom_cnn": (224, 224),
    "xception": (299, 299),
    "transfer": (224, 224),
}

def list_available_models(project_root: Optional[Path] = None) -> list[str]:
    """
    Return model keys that are actually loadable based on file presence.
    Also discovers additional .keras/.h5 files in MODEL_DIR and exposes them by stem name.
    """
    root = project_root or _project_root()
    available: set[str] = set()

    # 1) known keys from MODEL_PATHS (only if file exists)
    for key in MODEL_PATHS.keys():
        if get_model_path(key, root) is not None:
            available.add(key)

    # 2) discover any saved models on disk
    try:
        models_dir = _models_dir(root)
        if models_dir.exists():
            for p in models_dir.iterdir():
                if not p.is_file():
                    continue
                if p.suffix.lower() not in (".keras", ".h5"):
                    continue
                # expose as stem; users can use MODEL_PATHS to map pretty names later
                available.add(p.stem)
    except Exception:
        pass

    return sorted(available)


def get_model_path(model_name: str, project_root: Optional[Path] = None) -> Optional[Path]:
    """Resolve path to saved model; returns None if not found."""
    root = project_root or _project_root()
    rel = MODEL_PATHS.get(model_name)
    if not rel:
        # Allow loading by direct filename stem in models dir
        try:
            models_dir = _models_dir(root)
            for ext in (".keras", ".h5"):
                candidate = models_dir / f"{model_name}{ext}"
                if candidate.exists():
                    return candidate
        except Exception:
            return None
        return None
    path = root / rel
    return path if path.exists() else None


def load_model(model_name: str, project_root: Optional[Path] = None):
    """Load a saved Keras model by name. Returns None if file not found."""
    path = get_model_path(model_name, project_root)
    if path is None:
        return None
    from tensorflow import keras
    return keras.models.load_model(str(path))


def load_model_and_predict(
    model_name: str,
    image_batch: np.ndarray,
    class_names: Optional[list] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[list], Optional[np.ndarray]]:
    """
    Load model by name and return predicted class labels and probabilities.
    image_batch: (N, H, W, C) already normalized and with correct size for this model.
    """
    model = load_model(model_name, project_root)
    if model is None:
        return None, None
    probs = model.predict(image_batch, verbose=0)
    preds = np.argmax(probs, axis=-1)
    if class_names and len(class_names) > 0:
        pred_labels = [class_names[i] for i in preds]
    else:
        pred_labels = [str(i) for i in preds]
    return pred_labels, probs


def predict_from_bytes(
    model_name: str,
    image_bytes: bytes,
    class_names: Optional[list] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[float], Optional[np.ndarray]]:
    """
    Preprocess image from bytes, run prediction for one model.
    Returns (predicted_label, confidence, full_probabilities) or (None, None, None) if model missing.
    """
    label, conf, probs, _ = predict_from_file_bytes(
        model_name, image_bytes, "image.jpg", class_names, project_root
    )
    return label, conf, probs


def predict_from_file_bytes(
    model_name: str,
    file_bytes: bytes,
    filename: str,
    class_names: Optional[list] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[float], Optional[np.ndarray], Optional[dict]]:
    """
    Preprocess from bytes using filename to detect DICOM vs raster image.
    Returns (label, confidence, probs, dicom_meta_or_none).
    """
    root = project_root or _project_root()
    size = MODEL_INPUT_SIZES.get(model_name, (224, 224))
    fn = (filename or "image.jpg").lower()
    is_dicom = fn.endswith(".dcm") or fn.endswith(".dicom")

    if is_dicom:
        from src.data.dicom_loader import load_dicom_slice

        batch, dicom_meta = load_dicom_slice(file_bytes, target_size=size, normalize=True)
    else:
        from src.data.dataset import load_image_from_bytes

        dicom_meta = None
        batch = load_image_from_bytes(file_bytes, target_size=size, normalize=True)

    labels, probs = load_model_and_predict(model_name, batch, class_names, root)
    if labels is None or probs is None:
        return None, None, None, dicom_meta
    idx = int(np.argmax(probs[0]))
    return labels[0], float(probs[0][idx]), probs[0], dicom_meta
