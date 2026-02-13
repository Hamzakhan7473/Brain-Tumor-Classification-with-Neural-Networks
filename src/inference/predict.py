"""
Load saved models and run prediction on single or batch images.
Supports different input sizes per model (224 for custom_cnn/transfer, 299 for Xception).
"""
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
from tensorflow import keras


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


def get_model_path(model_name: str, project_root: Optional[Path] = None) -> Optional[Path]:
    """Resolve path to saved model; returns None if not found."""
    root = project_root or _project_root()
    rel = MODEL_PATHS.get(model_name)
    if not rel:
        return None
    path = root / rel
    return path if path.exists() else None


def load_model(model_name: str, project_root: Optional[Path] = None):
    """Load a saved Keras model by name. Returns None if file not found."""
    path = get_model_path(model_name, project_root)
    if path is None:
        return None
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
    from src.data.dataset import load_image_from_bytes

    size = MODEL_INPUT_SIZES.get(model_name, (224, 224))
    batch = load_image_from_bytes(image_bytes, target_size=size, normalize=True)
    labels, probs = load_model_and_predict(model_name, batch, class_names, project_root)
    if labels is None or probs is None:
        return None, None, None
    idx = np.argmax(probs[0])
    return labels[0], float(probs[0][idx]), probs[0]
