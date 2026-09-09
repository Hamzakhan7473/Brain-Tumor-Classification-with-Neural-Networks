"""Ingest QC object — modality / ImageType / description hint / thickness only.

Phase-1: no sequence classifier. Description is a hint, not truth.
"""

from __future__ import annotations

from typing import Any

LIMITED_EXAM_SENTENCE = "Limited exam; measurement not applied."

_MR = frozenset({"MR", "MRI"})
_WRONG_2D = frozenset({"T2", "DWI", "FLAIR"})


def _flag(code: str, severity: str, engine: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "engine": engine}


def _is_raster(filename: str | None) -> bool:
    fn = (filename or "").lower()
    return fn.endswith((".jpg", ".jpeg", ".png"))


def build_qc(
    *,
    model_name: str,
    filename: str,
    vr: Any,
    ran_inference: bool,
) -> dict[str, Any]:
    """Attach to audit / case_snapshot. overall is pass | degraded | fail."""
    is_3d = str(model_name or "").strip().lower() == "unet_3d_wmh"
    meta = vr.metadata if isinstance(getattr(vr, "metadata", None), dict) else {}
    flags: list[dict[str, str]] = []
    seq = str(getattr(vr, "sequence", "") or "")
    accepted = bool(getattr(vr, "accepted", False))
    trusted = bool(getattr(vr, "trusted", False))
    warnings = list(getattr(vr, "warnings", None) or [])

    if is_3d:
        if not accepted or not trusted:
            if seq and seq != "FLAIR":
                flags.append(_flag("WRONG_SEQUENCE", "fail", "wmh_3d"))
                flags.append(_flag("MISSING_FLAIR", "fail", "wmh_3d"))
            else:
                flags.append(_flag("QC_FAIL", "fail", "wmh_3d"))
            engines = {
                "wmh_3d": {"run": False, "reason": "QC_FAIL"},
                "research.triage": {"run": False, "reason": "NOT_APPLICABLE"},
            }
            overall = "fail"
        else:
            engines = {
                "wmh_3d": {"run": True, "trusted": True},
                "research.triage": {"run": False, "reason": "NOT_APPLICABLE"},
            }
            overall = "degraded" if warnings else "pass"
            if any("coarse" in str(w).lower() for w in warnings):
                flags.append(_flag("COARSE_VOXELS", "warn", "wmh_3d"))
        return {"overall": overall, "flags": flags, "engines": engines}

    raster = _is_raster(filename)
    engines = {
        "wmh_3d": {"run": False, "reason": "QC_FAIL"},
        "research.triage": {"run": False, "trusted": False, "reason": "QC_FAIL"},
    }
    mod = str(meta.get("modality") or "").upper().strip()
    if mod and mod not in _MR:
        flags.append(_flag("NOT_MR", "fail", "research.triage"))
    if seq in _WRONG_2D:
        flags.append(_flag("WRONG_SEQUENCE", "fail", "research.triage"))
    image_type = [str(x).upper() for x in (meta.get("image_type") or [])]
    if any("LOCALIZER" in x for x in image_type):
        flags.append(_flag("SERIES_CHECK_FAIL", "fail", "research.triage"))
    if raster:
        flags.append(_flag("RASTER_DEMO", "warn", "research.triage"))
        flags.append(_flag("MOTION_INDETERMINATE", "warn", "research.triage"))
    elif seq in {"unknown", ""} or (seq not in {"T1"} and seq not in _WRONG_2D):
        if seq == "image":
            flags.append(_flag("RASTER_DEMO", "warn", "research.triage"))
            flags.append(_flag("MOTION_INDETERMINATE", "warn", "research.triage"))
        else:
            flags.append(_flag("UNKNOWN_SEQUENCE", "warn", "research.triage"))
    st = meta.get("slice_thickness_mm")
    if st is not None:
        try:
            if float(st) > 5.0:
                flags.append(_flag("SLICE_THICKNESS", "warn", "research.triage"))
        except (TypeError, ValueError):
            pass

    fail = (not accepted) or any(f["severity"] == "fail" for f in flags)
    if fail:
        overall = "fail"
        if accepted and ran_inference:
            engines["research.triage"] = {"run": True, "trusted": False}
        else:
            engines["research.triage"] = {"run": False, "reason": "QC_FAIL", "trusted": False}
    else:
        overall = "degraded"
        engines["research.triage"] = {
            "run": bool(ran_inference and accepted),
            "trusted": False,
        }
    return {"overall": overall, "flags": flags, "engines": engines}
