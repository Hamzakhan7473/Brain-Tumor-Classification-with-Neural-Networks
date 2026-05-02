"""
2D MRI classification inference — TensorFlow/Keras only (channels-last batch).

Exports ``MODEL_PATHS`` / ``MODEL_INPUT_SIZES`` / helpers for offline scripts such as evaluate_models.py.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from src.inference.distribution_shift import detect_distribution_shift
from src.inference.inference_exceptions import InputValidationFailed
from src.inference.input_validator import validate_for_model
from src.inference.model_registry import MODEL_DEFS, classification_model_keys, predict_with_uncertainty, registry, resolve_weights
from src.inference.preprocessing import load_2d

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DIST_STATS_PATH = Path(__file__).resolve().parent / "data" / "distribution_stats.json"

CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "custom_cnn": 0.55,
    "xception": 0.60,
    "transfer": 0.55,
}


def _load_distribution_stats() -> dict:
    if not _DIST_STATS_PATH.exists():
        return {}
    with open(_DIST_STATS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _softmax_entropy(p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=np.float64).ravel(), 1e-12, 1.0)
    p = p / p.sum()
    return float(-np.sum(p * np.log(p)))


# ── Legacy exports for scripts/evaluate_models.py & similar ─────────────────
MODEL_PATHS: dict[str, str] = {}
MODEL_INPUT_SIZES: dict[str, Tuple[int, int]] = {}
for _name, _def in MODEL_DEFS.items():
    if _def["dims"] != 2:
        continue
    _wp = resolve_weights(_def)
    if _wp is not None:
        try:
            MODEL_PATHS[_name] = str(_wp.relative_to(_PROJECT_ROOT))
        except ValueError:
            MODEL_PATHS[_name] = str(_wp)
    th, tw, _ = _def["input_shape"]
    MODEL_INPUT_SIZES[_name] = (int(th), int(tw))


def _project_root() -> Path:
    return _PROJECT_ROOT


def list_available_models(project_root: Optional[Path] = None) -> list[str]:
    """2D classifier names whose weights exist on disk AND are loaded into ``registry``."""
    out: list[str] = []
    for k in classification_model_keys():
        if k in registry.models:
            out.append(k)
    return sorted(out)


def get_model_path(model_name: str, project_root: Optional[Path] = None) -> Optional[Path]:
    root = project_root or _PROJECT_ROOT
    defn = MODEL_DEFS.get(model_name)
    if not defn or defn["dims"] != 2:
        return None
    wp = resolve_weights(defn)
    if wp is None:
        return None
    return wp if wp.is_absolute() else root / wp


def load_model(model_name: str, project_root: Optional[Path] = None):
    """Load classifier from disk (for notebooks / evaluate). Inference API uses registry instead."""
    p = get_model_path(model_name, project_root or _PROJECT_ROOT)
    if p is None:
        return None
    from tensorflow import keras

    return keras.models.load_model(str(p), compile=False)


def load_model_and_predict(
    model_name: str,
    image_batch: np.ndarray,
    class_names: Optional[list] = None,
    project_root: Optional[Path] = None,
    model: Optional[Any] = None,
) -> Tuple[Optional[list], Optional[np.ndarray]]:
    model = model or load_model(model_name, project_root)
    if model is None:
        return None, None
    probs = model.predict(image_batch, verbose=0)
    preds = np.argmax(probs, axis=-1)
    names = class_names or MODEL_DEFS.get(model_name, {}).get("classes")
    pred_labels = [names[int(i)] for i in preds] if names else [str(int(i)) for i in preds]
    return pred_labels, probs


def _validation_http_detail(v):
    """Map ValidationResult → API 422 payload."""
    return {
        "error": "input_validation_failed",
        "errors": v.errors,
        "warnings": v.warnings,
        "detected_sequence": v.sequence,
        "confidence": v.confidence,
        "metadata": v.metadata or {},
    }


def run_predict_2d(
    file_bytes: bytes,
    filename: str,
    model_name: str = "custom_cnn",
    content_type: Optional[str] = None,
    clinical_context: Optional[dict] = None,
    mc_samples: int = 10,
) -> dict:
    """Core inference for REST /predict. TensorFlow/Keras only."""
    t0 = time.perf_counter()

    vr = validate_for_model(file_bytes, filename, model_name)
    if not vr.accepted:
        raise InputValidationFailed(_validation_http_detail(vr))

    km = registry.get_model(model_name)
    if km is None:
        avail = classification_model_keys()
        raise ValueError(
            f"Model '{model_name}' not loaded or unknown. Loaded 2D: "
            f"{[k for k in avail if k in registry.models]}",
        )

    cfg = registry.configs[model_name]
    if cfg.get("task") != "classification":
        raise ValueError(f"Model '{model_name}' is not a 2D classifier (task={cfg.get('task')}).")

    th, tw, nc = cfg["input_shape"]

    tensor, dicom_meta = load_2d(
        file_bytes=file_bytes,
        filename=filename,
        target_h=int(th),
        target_w=int(tw),
        channels=int(nc),
        norm=str(cfg["normalization"]),
        content_type=content_type,
    )

    stats_blob = _load_distribution_stats().get("classifier_div255_patch", {})
    ood_pack = detect_distribution_shift(tensor[0], stats_blob)

    eval_probs = np.asarray(km.predict(tensor, verbose=0)[0], dtype=np.float64)
    if abs(eval_probs.sum() - 1.0) > 0.05:
        e_ev = np.exp(eval_probs - eval_probs.max())
        eval_probs = e_ev / e_ev.sum()

    cls_list = list(cfg["classes"])
    pred_idx = int(np.argmax(eval_probs))
    confidence = float(eval_probs[pred_idx])
    prediction = cls_list[pred_idx]
    class_probs = {cls_list[i]: round(float(eval_probs[i]), 4) for i in range(len(cls_list))}

    uq = predict_with_uncertainty(km, tensor, n_samples=int(mc_samples))

    probs = eval_probs.astype(np.float64)

    stack = np.asarray(uq["samples_stack"])[:, 0, :]
    pred_col = stack[:, pred_idx]
    ci_l = round(float(np.percentile(pred_col, 2.5)), 5)
    ci_u = round(float(np.percentile(pred_col, 97.5)), 5)

    entropy = round(_softmax_entropy(eval_probs), 5)

    threshold = CONFIDENCE_THRESHOLDS.get(model_name, 0.6)
    if confidence < threshold:
        disposition = "indeterminate"
        display_prediction = None
        radiologist_action_required = (
            f"Model confidence ({confidence:.0%}) is below acceptance threshold ({threshold:.0%}). "
            "Manual review required."
        )
    else:
        disposition = "predicted"
        display_prediction = prediction
        radiologist_action_required = None

    warnings: list[str] = []
    warnings.extend(vr.warnings)
    warnings.extend(ood_pack.get("warnings") or [])
    mean_z = float(ood_pack.get("distribution_z_score") or 0.0)

    sal_b64 = None
    if disposition == "predicted":
        try:
            from src.api.gradcam import keras_gradcam_base64

            batch_np = tensor.astype(np.float32)
            sal_b64 = keras_gradcam_base64(km, batch_np, pred_idx, (int(tw), int(th)))
        except Exception:
            pass

    voxel_meta = vr.metadata if vr.metadata else {}

    return {
        "prediction": prediction,
        "confidence": round(confidence, 5),
        "class_probabilities": class_probs,
        "probabilities_vec": probs.astype(np.float32),
        "model_name": model_name,
        "input_shape": list(tensor.shape),
        "batch_np": tensor,
        "preprocessing_applied": [f"keras_infer:{cfg['normalization']}", f"resize_{th}x{tw}"],
        "dicom_meta": dicom_meta,
        "inference_time_s": round(time.perf_counter() - t0, 3),
        "saliency_map_b64": sal_b64,
        "classes_order": cls_list,
        "warnings": warnings,
        "validation": {
            "detected_sequence": vr.sequence,
            "sequence_confidence": round(float(vr.confidence), 4),
            "metadata": voxel_meta,
            "distribution_z_score": round(mean_z, 3),
            "distribution_is_ood": bool(ood_pack.get("is_ood")),
        },
        "disposition": disposition,
        "display_prediction": display_prediction,
        "radiologist_action_required": radiologist_action_required,
        "uncertainty": {
            "method": "mc_dropout",
            "n_samples": int(uq["n_samples"]),
            "confidence_ci_95": [ci_l, ci_u],
            "prediction_entropy": entropy,
        },
        "clinical_context": clinical_context or {},
    }


def predict_from_bytes(
    model_name: str,
    image_bytes: bytes,
    class_names: Optional[list] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[float], Optional[np.ndarray]]:
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
    Compatibility API for Streamlit / scripts.
    ``class_names`` is ignored — order follows ``MODEL_DEFS`` / checkpoint.
    """
    try:
        out = run_predict_2d(file_bytes, filename, model_name, content_type=None)
    except (ValueError, InputValidationFailed):
        return None, None, None, None

    vec = np.array([out["class_probabilities"][c] for c in out["classes_order"]], dtype=np.float32)
    label = str(out["display_prediction"] if out["display_prediction"] else out["prediction"])
    return label, float(out["confidence"]), vec, out.get("dicom_meta")


def predict_legacy_tuple(
    file_bytes: bytes,
    filename: str,
    model_name: str,
    content_type: Optional[str],
) -> Tuple[Any, Any, Any, Any, Dict[str, Any], np.ndarray]:
    """
    Normalize output for callers that unpacked six values from `_run_predict`.
    Returns (label, conf, probs_dict, dicom_meta, infer_meta, batch_np).
    """
    try:
        out = run_predict_2d(file_bytes, filename, model_name, content_type)
    except InputValidationFailed:
        raise
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    probs_dict = dict(out["class_probabilities"])
    label = str(out["display_prediction"] if out["display_prediction"] else out["prediction"])
    infer_meta = {
        "input_shape": out["input_shape"],
        "preprocessing_applied": out.get("preprocessing_applied"),
    }
    return (
        label,
        out["confidence"],
        probs_dict,
        out["dicom_meta"],
        infer_meta,
        np.asarray(out["batch_np"]),
    )

