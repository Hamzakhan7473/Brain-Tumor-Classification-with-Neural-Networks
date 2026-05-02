"""
3D WMH segmentation inference via ``unet_3d_wmh`` — Keras only, channels-last (D,H,W,C).
"""

from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.inference.distribution_shift import detect_distribution_shift
from src.inference.inference_exceptions import ClinicalContextRequired, InputValidationFailed
from src.inference.input_validator import validate_for_model
from src.inference.model_registry import MODEL_DEFS, predict_with_uncertainty, registry, segmentation_model_keys
from src.inference.percentile_wm import volume_percentile_for_age
from src.inference.preprocessing import load_wmh_nifti_dual_channel

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DIST_STATS_PATH = Path(__file__).resolve().parent / "data" / "distribution_stats.json"

MODEL_PATHS_3D = {
    "unet_3d_wmh": "models/saved/unet_3d_wmh_final.keras",
}


def _load_distribution_stats() -> dict:
    if not _DIST_STATS_PATH.exists():
        return {}
    with open(_DIST_STATS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _validation_http_detail(v):
    return {
        "error": "input_validation_failed",
        "errors": v.errors,
        "warnings": v.warnings,
        "detected_sequence": v.sequence,
        "confidence": v.confidence,
        "metadata": v.metadata or {},
    }


def _project_root() -> Path:
    return _PROJECT_ROOT


def get_model_path_3d(model_name: str, project_root: Optional[Path] = None) -> Optional[Path]:
    from src.inference.model_registry import resolve_weights

    d = MODEL_DEFS.get(model_name)
    if not d or int(d["dims"]) != 3:
        return None
    wp = resolve_weights(d)
    return wp


def list_available_models_3d(project_root: Optional[Path] = None) -> list[str]:
    return sorted(k for k in segmentation_model_keys() if k in registry.models)


def _require_age_context(ctx: Optional[dict]) -> dict:
    if not ctx:
        raise ClinicalContextRequired("Patient age is required for WMH percentile grading and audit trail.")
    raw_age = ctx.get("age")
    if raw_age is None or raw_age == "":
        raise ClinicalContextRequired("Patient age required for risk stratification.", {"field": "age"})
    try:
        age_int = int(raw_age)
    except (TypeError, ValueError) as exc:
        raise ClinicalContextRequired("Patient age must be an integer (0–120).", {"field": "age"}) from exc
    if age_int < 0 or age_int > 120:
        raise ClinicalContextRequired("Patient age out of bounds (expected 0–120).", {"field": "age"})
    ctx = dict(ctx)
    ctx["age"] = age_int
    return ctx


def run_predict_3d(
    file_bytes: bytes,
    filename: str,
    model_name: str = "unet_3d_wmh",
    clinical_context: Optional[dict] = None,
    mc_samples: int = 10,
) -> dict:
    t0 = time.perf_counter()

    ctx = _require_age_context(clinical_context)

    vr = validate_for_model(file_bytes, filename, model_name)
    if not vr.accepted:
        raise InputValidationFailed(_validation_http_detail(vr))

    model = registry.get_model(model_name)
    if model is None:
        av = [n for n in segmentation_model_keys() if n in registry.models]
        raise ValueError(f"3D model '{model_name}' not loaded. Available: {av}")

    cfg = registry.configs[model_name]
    fn = filename or "volume.nii.gz"
    if not (fn.lower().endswith(".nii") or fn.lower().endswith(".nii.gz")):
        raise ValueError("WMH segmentation expects NIfTI (.nii / .nii.gz).")

    d, h, w, _ = cfg["input_shape"]
    volume = load_wmh_nifti_dual_channel(file_bytes, fn, int(d), int(h), int(w))

    stats_blob = _load_distribution_stats().get("wmh_unet_dual_preproc_channel0", {})
    chan0 = np.asarray(volume[0, ..., 0], dtype=np.float32)
    ood_pack = detect_distribution_shift(chan0, stats_blob)

    uq = predict_with_uncertainty(model, volume.astype(np.float32), n_samples=int(mc_samples))

    raw_stack = np.asarray(uq["samples_stack"]).astype(np.float64)
    n_s = raw_stack.shape[0]

    lesion_planes: list[np.ndarray] = []
    for si in range(n_s):
        o = np.asarray(raw_stack[si])
        if o.ndim == 6 and o.shape[0] == 1:
            o = o[0]
        while o.ndim == 5 and o.shape[0] == 1:
            o = o[0]
        if o.ndim != 4:
            raise ValueError(f"Unexpected 3D segmentation output shape after squeeze: {o.shape}")
        lesion_planes.append(o[..., 1])

    lesion_stack = np.stack(lesion_planes, axis=0)
    mean_les = lesion_stack.mean(axis=0)

    threshold = 0.5
    voxel_vol_mm3 = float(vr.metadata.get("voxel_volume_mm3", 1.0))
    if voxel_vol_mm3 <= 0:
        voxel_vol_mm3 = 1.0

    vol_samples_cc: list[float] = []
    for si in range(n_s):
        m = lesion_stack[si] > threshold
        vol_samples_cc.append(float(m.sum() * voxel_vol_mm3 / 1000.0))

    vol_arr = np.array(vol_samples_cc, dtype=np.float64)
    wmh_vol_mean = round(float(vol_arr.mean()), 4)
    vol_std = round(float(vol_arr.std()), 4)
    ci_lo = round(float(np.percentile(vol_arr, 2.5)), 4)
    ci_hi = round(float(np.percentile(vol_arr, 97.5)), 4)

    lesion_mask = mean_les > threshold
    lesion_voxels = int(lesion_mask.sum())
    total_voxels = int(lesion_mask.size)
    wmh_volume_cc = round(float(lesion_voxels * voxel_vol_mm3 / 1000.0), 4)
    lesion_fraction = round(lesion_voxels / max(total_voxels, 1), 6)
    mean_lesion_prob = round(float(mean_les.mean()), 4)
    peak_lesion_prob = round(float(mean_les.max()), 4)

    if wmh_volume_cc < 1.0:
        severity = "Normal"
        risk = "Low"
    elif wmh_volume_cc < 5.0:
        severity = "Mild"
        risk = "Moderate"
    elif wmh_volume_cc < 15.0:
        severity = "Moderate"
        risk = "High"
    else:
        severity = "Severe"
        risk = "Very High"

    pct, pct_note = volume_percentile_for_age(wmh_volume_cc, int(ctx["age"]), str(ctx.get("sex") or ""))

    warnings: list[str] = []
    warnings.extend(vr.warnings or [])
    warnings.extend(ood_pack.get("warnings") or [])
    if mean_lesion_prob > 0.3 and peak_lesion_prob < 0.6:
        warnings.append(
            "Lesion probabilities occupy an ambiguous band — corroborate with manual lesion review.",
        )

    sal_b64 = None
    try:
        sal_b64 = _wmh_slice_overlay(mean_les, volume[0, ..., 0])
    except Exception:
        pass

    probs_ui = {
        "mean_lesion_probability": float(mean_lesion_prob),
        "lesion_voxel_fraction": float(lesion_fraction),
        "background_voxel_fraction": float(round(1.0 - lesion_fraction, 6)),
        "severity_grade": severity,
        "risk_level": risk,
    }

    elapsed = round(time.perf_counter() - t0, 3)

    return {
        "prediction": "wmh_segmentation",
        "label": severity,
        "confidence": mean_lesion_prob,
        "risk_level": risk,
        "model": model_name,
        "probabilities": probs_ui,
        "task": "segmentation",
        "input_shape": list(volume.shape),
        "inference_time_s": elapsed,
        "warnings": warnings,
        "clinical_context": ctx,
        "validation": {
            "detected_sequence": vr.sequence,
            "sequence_confidence": round(float(vr.confidence), 4),
            "metadata": vr.metadata or {},
            "distribution_z_score": round(float(ood_pack.get("distribution_z_score") or 0), 3),
            "distribution_is_ood": bool(ood_pack.get("is_ood")),
        },
        "uncertainty": {
            "method": "mc_dropout",
            "n_samples": int(uq["n_samples"]),
            "volume_cc_mean_over_samples": wmh_vol_mean,
            "volume_uncertainty_std_cc": vol_std,
            "volume_cc_ci_95": [ci_lo, ci_hi],
        },
        "wmh": {
            "volume_cc": wmh_volume_cc,
            "volume_cc_ci_95": [ci_lo, ci_hi],
            "volume_uncertainty_cc": vol_std,
            "lesion_voxels": lesion_voxels,
            "lesion_fraction": lesion_fraction,
            "mean_lesion_prob": mean_lesion_prob,
            "peak_lesion_prob": peak_lesion_prob,
            "severity_grade": severity,
            "risk_level": risk,
            "threshold_used": threshold,
            "age_matched_percentile": pct,
            "percentile_note": pct_note,
            "note": (
                "Single-series upload duplicated for both encoder channels vs training FLAIR+T1; "
                "paired FLAIR/T1 MICCAI-style uploads preferred."
            ),
        },
        "saliency_map_b64": sal_b64,
    }


def _wmh_slice_overlay(lesion_prob: np.ndarray, flair_vol: np.ndarray) -> str:
    per_slice = lesion_prob.sum(axis=(1, 2))
    best_slice = int(np.argmax(per_slice))

    flair_slice = flair_vol[best_slice]
    lesion_slice = lesion_prob[best_slice]

    fig, axes = plt.subplots(1, 2, figsize=(8, 4), facecolor="black")
    axes[0].imshow(flair_slice, cmap="gray", aspect="equal", vmin=float(flair_slice.min()), vmax=float(flair_slice.max()))
    axes[0].set_title("Input slice", color="white", fontsize=10)
    axes[0].axis("off")

    axes[1].imshow(flair_slice, cmap="gray", aspect="equal", vmin=float(flair_slice.min()), vmax=float(flair_slice.max()))
    axes[1].imshow(lesion_slice, cmap="hot", alpha=0.5, vmin=0, vmax=1, aspect="equal")
    axes[1].set_title("WMH prob overlay", color="white", fontsize=10)
    axes[1].axis("off")

    plt.tight_layout(pad=0.2)

    buf = io.BytesIO()
    plt.savefig(buf, format="PNG", dpi=100, bbox_inches="tight", facecolor="black")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def predict_volume_from_bytes(
    *,
    model_name: str,
    volume_bytes: bytes,
    filename: str,
    class_names: list[str],
    target_shape: tuple[int, int, int],
    project_root: Optional[Path] = None,
    clinical_context: Optional[dict] = None,
) -> tuple[Optional[str], Optional[float], Optional[dict]]:
    """Legacy shim for callers still importing this symbol."""
    if model_name not in segmentation_model_keys() or model_name not in registry.models:
        return None, None, None
    try:
        ctx = clinical_context if clinical_context is not None else {"age": 55}
        out = run_predict_3d(volume_bytes, filename, model_name, clinical_context=ctx)
    except Exception:
        return None, None, None

    probs = dict(out["probabilities"])
    return (
        str(out["prediction"]),
        float(out["confidence"]),
        probs,
    )
