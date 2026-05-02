"""
Single TensorFlow/Keras registry: paths, preprocessing hints, warmup at startup.

Class order matches configs/data.yaml and image_dataset_from_directory(label mode categorical).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── Model definitions ───────────────────────────────────────────────────────
# normalization "div255": Rescaling(1/255) in src/data/dataset.py (all 2D training).
# WMH: per-modality normalization like src/data/dataset_3d_seg._normalize_modal (see preprocessing).

MRI_CLASSES_FOUR = ["glioma", "meningioma", "pituitary", "notumor"]

MODEL_DEFS: dict[str, dict] = {
    "custom_cnn": {
        "path": str(_PROJECT_ROOT / "models/saved/custom_cnn_final.keras"),
        "fallback": str(_PROJECT_ROOT / "models/saved/custom_cnn_best.keras"),
        "input_shape": (224, 224, 3),
        "dims": 2,
        "classes": MRI_CLASSES_FOUR,
        "normalization": "div255",
        "description": "Custom CNN — 4-class brain tumor classifier",
        "task": "classification",
    },
    "xception": {
        "path": str(_PROJECT_ROOT / "models/saved/xception_final.keras"),
        "fallback": str(_PROJECT_ROOT / "models/saved/xception_best.keras"),
        "input_shape": (299, 299, 3),
        "dims": 2,
        "classes": MRI_CLASSES_FOUR,
        "normalization": "div255",
        "description": "Xception — 4-class brain tumor classifier (/255 trained; backbone ImageNet-init only)",
        "task": "classification",
    },
    "transfer": {
        "path": str(_PROJECT_ROOT / "models/saved/transfer_final.keras"),
        "fallback": str(_PROJECT_ROOT / "models/saved/transfer_best.keras"),
        "input_shape": (224, 224, 3),
        "dims": 2,
        "classes": MRI_CLASSES_FOUR,
        "normalization": "div255",
        "description": "EfficientNetB0 transfer — 4-class brain tumor classifier",
        "task": "classification",
    },
    # Audit: INPUT (None, 96, 96, 96, 2) — TWO channels as trained (FLAIR + T1 in training).
    "unet_3d_wmh": {
        "path": str(_PROJECT_ROOT / "models/saved/unet_3d_wmh_final.keras"),
        "fallback": str(_PROJECT_ROOT / "models/saved/unet_3d_wmh_best.keras"),
        "input_shape": (96, 96, 96, 2),
        "dims": 3,
        "classes": ["background", "wmh_lesion"],
        "normalization": "wmh_modal",
        "task": "segmentation",
        "description": "3D U-Net — WMH segmentation (dual-channel checkpoint)",
    },
}


def resolve_weights(defn: dict) -> Optional[Path]:
    p = Path(defn["path"])
    if not p.exists() and defn.get("fallback"):
        p = Path(defn["fallback"])
    if not p.exists():
        return None
    return p


class ModelRegistry:
    _instance: Optional["ModelRegistry"] = None

    def __init__(self):
        import tensorflow as tf

        self._tf = tf
        self.models: dict[str, Any] = {}
        self.configs: dict[str, dict] = {}

    @classmethod
    def get(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_all(self) -> None:
        tf = self._tf
        self.models.clear()
        self.configs.clear()
        for name, defn in MODEL_DEFS.items():
            wp = resolve_weights(defn)
            if wp is None:
                logger.warning("Skipping %s — checkpoint missing (%s)", name, defn["path"])
                continue
            try:
                model = tf.keras.models.load_model(str(wp), compile=False)
                d, dims = defn["input_shape"], int(defn["dims"])
                if dims == 3:
                    dd, hh, ww, cc = d
                    dummy = np.zeros((1, dd, hh, ww, cc), dtype=np.float32)
                else:
                    hh, ww, cc = d
                    dummy = np.zeros((1, hh, ww, cc), dtype=np.float32)
                model.predict(dummy, verbose=0)
                self.models[name] = model
                self.configs[name] = {**defn, "_resolved_path": str(wp)}
                logger.info("Loaded + warmed: %s (%s)", name, wp.name)
            except Exception as e:
                logger.error("Failed to load %s: %s", name, e, exc_info=True)

        if not self.models:
            raise RuntimeError(
                "No Keras models loaded. Place .keras weights under models/saved/ "
                "(see MODEL_DEFS in src/inference/model_registry.py)."
            )

    def get_model(self, name: str):
        return self.models.get(name)

    def list_models(self) -> list[dict]:
        out = []
        for n in sorted(self.models.keys()):
            cfg = self.configs[n]
            row = {
                "name": n,
                "description": cfg["description"],
                "input_shape": list(cfg["input_shape"]),
                "dims": cfg["dims"],
                "classes": list(cfg["classes"]),
                "task": cfg.get("task", "classification"),
                "normalization": cfg.get("normalization"),
                "loaded": True,
            }
            rp = cfg.get("_resolved_path")
            if rp:
                row["weights_file"] = Path(rp).name
            out.append(row)
        return out


registry = ModelRegistry.get()


def predict_with_uncertainty(
    model,
    input_tensor: np.ndarray,
    n_samples: int = 10,
) -> dict:
    """
    Monte Carlo dropout: forward passes with ``training=True`` so stochastic layers vary.
    If the graph has no dropout, std may be negligible — entropy still summarizes class spread.
    """
    preds: list[np.ndarray] = []
    x = np.asarray(input_tensor, dtype=np.float32)
    for _ in range(max(3, min(48, int(n_samples)))):
        out = model(x, training=True)
        arr = np.asarray(out.numpy()) if hasattr(out, "numpy") else np.asarray(out)
        preds.append(arr)
    stack = np.stack(preds, axis=0).astype(np.float64)
    mean = stack.mean(axis=0)
    std = stack.std(axis=0)
    return {
        "mean": mean,
        "std": std,
        "ci_lower": np.percentile(stack, 2.5, axis=0),
        "ci_upper": np.percentile(stack, 97.5, axis=0),
        "n_samples": stack.shape[0],
        "samples_stack": stack,
    }


def classification_model_keys() -> list[str]:
    return [k for k, v in MODEL_DEFS.items() if v["dims"] == 2]


def segmentation_model_keys() -> list[str]:
    return [k for k, v in MODEL_DEFS.items() if v.get("task") == "segmentation"]
