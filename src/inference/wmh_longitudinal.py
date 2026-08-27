"""Longitudinal WMH volume comparison between two timepoints (Stage-1 MVP)."""

from __future__ import annotations

from typing import Any, Dict, Optional


STABLE_ABS_CC = 0.5
STABLE_ABS_PCT = 5.0


def _wmh_block(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("wmh"), dict):
        return payload["wmh"]
    return payload


def _vol(wmh: dict[str, Any], key: str = "volume_cc") -> float:
    raw = wmh.get(key)
    if raw is None and isinstance(wmh.get("regional"), dict):
        raw = wmh["regional"].get(key)
    try:
        return round(float(raw or 0.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _pct_change(current: float, prior: float) -> Optional[float]:
    if prior <= 0:
        return None if current <= 0 else 100.0
    return round(((current - prior) / prior) * 100.0, 2)


def _direction(delta: float, pct: Optional[float]) -> str:
    if abs(delta) < STABLE_ABS_CC:
        return "stable"
    if pct is not None and abs(pct) < STABLE_ABS_PCT:
        return "stable"
    return "increased" if delta > 0 else "decreased"


def compare_wmh_timepoints(
    current: dict[str, Any],
    prior: dict[str, Any],
    *,
    prior_label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compare current vs prior WMH metrics.

    Accepts full model_run dicts or bare ``wmh`` metric objects.
    """
    cur = _wmh_block(current)
    prv = _wmh_block(prior)

    cur_total = _vol(cur)
    prv_total = _vol(prv)
    delta = round(cur_total - prv_total, 4)
    pct = _pct_change(cur_total, prv_total)
    direction = _direction(delta, pct)

    regional_keys = (
        ("volume_cc_periventricular", "periventricular"),
        ("volume_cc_deep_subcortical", "deep_subcortical"),
        ("volume_cc_infratentorial", "infratentorial"),
    )
    regional: dict[str, dict[str, float | None]] = {}
    for key, short in regional_keys:
        c = _vol(cur, key)
        p = _vol(prv, key)
        d = round(c - p, 4)
        regional[short] = {
            "current_cc": c,
            "prior_cc": p,
            "delta_cc": d,
            "pct_change": _pct_change(c, p),
        }

    label = (prior_label or "prior study").strip()
    if direction == "stable":
        summary = (
            f"Compared to {label}: total WMH volume {cur_total} cc vs prior {prv_total} cc "
            f"(Δ {delta:+.2f} cc) — stable within research thresholds."
        )
    elif pct is not None:
        summary = (
            f"Compared to {label}: total WMH volume {direction} from {prv_total} cc to "
            f"{cur_total} cc (Δ {delta:+.2f} cc, {pct:+.1f}% change)."
        )
    else:
        summary = (
            f"Compared to {label}: total WMH volume {direction} from {prv_total} cc to "
            f"{cur_total} cc (Δ {delta:+.2f} cc)."
        )

    return {
        "prior_label": label,
        "current_volume_cc": cur_total,
        "prior_volume_cc": prv_total,
        "volume_delta_cc": delta,
        "volume_pct_change": pct,
        "direction": direction,
        "regional": regional,
        "comparison_summary": summary,
        "note": "Longitudinal comparison uses total/regional volumes only; no co-registration.",
    }
