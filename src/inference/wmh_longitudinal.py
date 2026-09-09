"""This-study vs last WMH volumes.

Δcc is emitted only after ``run_registration_job`` writes
``registration.status=passed``. Caller-supplied registration is ignored.
No prior / incompatible protocol → no comparison object.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from src.inference.registration import job_wrote_passed, run_registration_job, same_sequence_family


def _wmh_block(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("wmh"), dict):
        return payload["wmh"]
    return payload


def _vol(wmh: dict[str, Any], key: str = "volume_cc") -> float | None:
    raw = wmh.get(key)
    if raw is None and isinstance(wmh.get("regional"), dict):
        raw = wmh["regional"].get(key)
    if raw is None:
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _present(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str) and val == "":
        return False
    return True


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and _present(payload[key]):
            return payload[key]
        wmh = payload.get("wmh")
        if isinstance(wmh, dict) and _present(wmh.get(key)):
            return wmh[key]
    return None


def _has_prior(prior: dict[str, Any] | None) -> bool:
    if not isinstance(prior, dict) or not prior:
        return False
    block = _wmh_block(prior)
    if _vol(block) is not None:
        return True
    if _nested(prior, "flair_volume", "assembled_flair", "flair_volume_path"):
        return True
    return False


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    s = str(raw).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt, n in (("%Y%m%d", 8), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    return None


def _days_between(current: dict[str, Any], prior: dict[str, Any]) -> int | None:
    explicit = _nested(current, "days_between") or _nested(prior, "days_between")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    cur_t = _parse_ts(_nested(current, "acquired_at", "timestamp", "study_date"))
    pri_t = _parse_ts(_nested(prior, "acquired_at", "timestamp", "study_date"))
    if cur_t is None or pri_t is None:
        return None
    return max(0, int((cur_t - pri_t).total_seconds() // 86400))


def _direction(delta: float, pct: float | None) -> str:
    if pct is not None and abs(pct) < 5.0:
        return "stable"
    if abs(delta) < 0.1:
        return "stable"
    return "increased" if delta > 0 else "decreased"


def _incomparable(
    *,
    label: str,
    reason: str,
    job: dict[str, Any] | None,
    current_cc: float | None,
    prior_cc: float | None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "prior_label": label,
        "status": "incomparable",
        "reason_code": reason,
        "qc": {"registration": dict(job) if job else {"status": "not_run", "source": None}},
    }
    if current_cc is not None:
        out["current_volume_cc"] = current_cc
    if prior_cc is not None:
        out["prior_volume_cc"] = prior_cc
    return out


def compare_wmh_timepoints(
    current: dict[str, Any] | None,
    prior: dict[str, Any] | None,
    *,
    prior_label: Optional[str] = None,
    registration: Optional[dict[str, Any]] = None,
    current_volume: Any = None,
    prior_volume: Any = None,
    use_affine: bool = False,
) -> Dict[str, Any] | None:
    """
    Compare WMH volumes only after this repo's registration job passes.

    ``registration`` from the caller is ignored. No raw cc subtraction.
    Returns None when there is no prior or the protocol is incompatible.
    """
    del registration  # never treat caller status as passed
    if not isinstance(current, dict) or not _has_prior(prior):
        return None
    assert isinstance(prior, dict)

    cur = _wmh_block(current)
    prv = _wmh_block(prior)
    cur_cc = _vol(cur)
    prv_cc = _vol(prv)
    label = (prior_label or "prior study").strip()

    cur_key = _nested(current, "patient_key")
    pri_key = _nested(prior, "patient_key")
    if cur_key and pri_key and str(cur_key) != str(pri_key):
        return None

    cur_seq = _nested(current, "sequence", "likely_seq") or "FLAIR"
    pri_seq = _nested(prior, "sequence", "likely_seq") or "FLAIR"
    if not same_sequence_family(cur_seq, pri_seq):
        return None

    vol_c = current_volume if current_volume is not None else _nested(current, "flair_volume", "assembled_flair", "flair_volume_path")
    vol_p = prior_volume if prior_volume is not None else _nested(prior, "flair_volume", "assembled_flair", "flair_volume_path")

    job = run_registration_job(
        current_volume=vol_c,
        prior_volume=vol_p,
        current_audit_id=str(_nested(current, "audit_id") or "") or None,
        prior_audit_id=str(_nested(prior, "audit_id") or "") or None,
        current_study_uid=str(_nested(current, "study_uid", "study_instance_uid") or "") or None,
        prior_study_uid=str(_nested(prior, "study_uid", "study_instance_uid") or "") or None,
        patient_key=str(cur_key) if cur_key else (str(pri_key) if pri_key else None),
        prior_patient_key=str(pri_key) if pri_key else None,
        current_sequence=cur_seq,
        prior_sequence=pri_seq,
        current_spacing_mm=_nested(current, "spacing_mm", "voxel_dims_mm"),
        prior_spacing_mm=_nested(prior, "spacing_mm", "voxel_dims_mm"),
        use_affine=use_affine,
    )
    if job.get("status") == "skipped":
        return None
    if not job_wrote_passed(job):
        reason = str(job.get("reason_code") or "QC_NO_REGISTRATION")
        return _incomparable(
            label=label,
            reason=reason,
            job=job,
            current_cc=cur_cc if cur_cc is not None else 0.0,
            prior_cc=prv_cc if prv_cc is not None else 0.0,
        )

    if cur_cc is None or prv_cc is None:
        return _incomparable(
            label=label,
            reason="QC_REGISTRATION",
            job={**job, "status": "failed", "reason_code": "QC_REGISTRATION"},
            current_cc=cur_cc,
            prior_cc=prv_cc,
        )

    delta = round(cur_cc - prv_cc, 4)
    pct = None if prv_cc == 0 else round(100.0 * delta / prv_cc, 2)
    direction = _direction(delta, pct)
    days = _days_between(current, prior)
    summary = (
        f"WMH volume {direction} vs prior "
        f"({prv_cc} → {cur_cc} cc, Δ {delta} cc)."
    )
    return {
        "prior_label": label,
        "status": "comparable",
        "prior_cc": prv_cc,
        "current_cc": cur_cc,
        "delta_cc": delta,
        "pct_change": pct,
        "days_between": days,
        "direction": direction,
        "prior_volume_cc": prv_cc,
        "current_volume_cc": cur_cc,
        "volume_delta_cc": delta,
        "volume_pct_change": pct,
        "comparison_summary": summary,
        "qc": {"registration": dict(job)},
    }
