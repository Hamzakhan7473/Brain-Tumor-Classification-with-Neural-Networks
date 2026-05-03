"""Normalize GET /cases/{uid} into a radiologist review payload (classification vs segmentation)."""

from __future__ import annotations

import hashlib
from typing import Any, Literal, Optional

LabelClass = Literal["ok", "warn", "danger"]


def _synthetic_audit_id(study_uid: str, model: str, ts: str | None) -> str:
    raw = f"{ts or ''}{study_uid}{model}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _label_class(conf: float, disposition: str | None) -> LabelClass:
    d = (disposition or "").lower()
    if d == "indeterminate":
        return "warn"
    if conf >= 0.9:
        return "danger"
    if conf >= 0.7:
        return "warn"
    return "ok"


def _norm_probs(raw: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not raw:
        return out
    for k, v in raw.items():
        try:
            out[str(k).lower()] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def infer_task(inf: dict[str, Any], shadow_mr: dict[str, Any] | None) -> Literal["classification", "segmentation"]:
    if shadow_mr and isinstance(shadow_mr.get("metrics"), dict):
        m = shadow_mr["metrics"]
        if any(k in m for k in ("wmh_volume_cc", "volume_cc", "lesion_voxels", "severity_grade")):
            return "segmentation"
    if isinstance(inf.get("wmh"), dict) or inf.get("task") == "segmentation":
        return "segmentation"
    mname = str(inf.get("model") or "").lower()
    if "wmh" in mname or "3d" in mname:
        return "segmentation"
    return "classification"


def build_model_run_for_review(
    *,
    study_uid: str,
    inf: dict[str, Any],
    shadow_mr: dict[str, Any] | None,
) -> dict[str, Any]:
    mr = shadow_mr if shadow_mr else {}
    model_name = str(mr.get("model_name") or inf.get("model") or "unknown")
    label = str(mr.get("label") or inf.get("label") or "—")
    conf = float(mr.get("confidence") if mr.get("confidence") is not None else inf.get("confidence") or 0.0)
    probs = _norm_probs((mr.get("class_probabilities") or mr.get("probabilities") or inf.get("probabilities")) or {})
    disp = inf.get("disposition")
    audit_id = str(inf.get("audit_id") or mr.get("audit_id") or _synthetic_audit_id(study_uid, model_name, str(inf.get("timestamp"))))
    inf_ms = inf.get("inference_time_s")
    try:
        inference_time_ms = int(float(inf_ms) * 1000) if inf_ms is not None else 0
    except (TypeError, ValueError):
        inference_time_ms = 0
    shape = inf.get("input_shape") or mr.get("input_shape")
    if not isinstance(shape, list):
        shape = []
    sal = inf.get("saliency_map_b64") or mr.get("saliency_map_b64")
    out: dict[str, Any] = {
        "audit_id": audit_id,
        "model_name": model_name,
        "model_version": str(inf.get("model_version") or mr.get("model_version") or "v1"),
        "label": label,
        "label_class": _label_class(conf, disp if isinstance(disp, str) else None),
        "confidence": conf,
        "class_probabilities": probs,
        "saliency_b64": sal,
        "inference_time_ms": inference_time_ms,
        "input_shape": shape,
    }
    if isinstance(mr.get("metrics"), dict):
        out["wmh_metrics"] = mr["metrics"]
    elif isinstance(inf.get("wmh"), dict):
        out["wmh_metrics"] = inf["wmh"]
    return out


def build_case_review(
    *,
    case_id: str,
    study_uid: str,
    received_at: str | None,
    site_id: str | None,
    patient: dict[str, Any] | None,
    inf: dict[str, Any],
    shadow_mr: dict[str, Any] | None,
    prior_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    task = infer_task(inf, shadow_mr)
    model_run = build_model_run_for_review(study_uid=study_uid, inf=inf, shadow_mr=shadow_mr)

    fb_out: dict[str, Any] | None = None
    if prior_feedback and isinstance(prior_feedback, dict):
        if prior_feedback.get("schema_version") == "1.0":
            fb_out = {
                "status": "submitted",
                "verdict": prior_feedback.get("verdict"),
                "feedback_id": prior_feedback.get("feedback_id"),
                "submitted_at": (prior_feedback.get("timing") or {}).get("submitted_at") or prior_feedback.get("timestamp"),
                "error_categories": prior_feedback.get("error_categories") or [],
                "ground_truth": prior_feedback.get("ground_truth"),
                "clinical_notes": prior_feedback.get("clinical_notes"),
            }
        elif prior_feedback.get("feedback") in ("agree", "wrong_class", "unclear"):
            fb_out = {
                "status": "submitted",
                "verdict": "agree" if prior_feedback["feedback"] == "agree" else "disagree",
                "feedback_id": None,
                "submitted_at": prior_feedback.get("timestamp"),
                "legacy": True,
            }

    return {
        "case_id": case_id,
        "study_uid": study_uid,
        "received_at": received_at,
        "model_run": model_run,
        "patient": patient or {},
        "site_id": site_id,
        "task": task,
        "feedback": fb_out,
    }
