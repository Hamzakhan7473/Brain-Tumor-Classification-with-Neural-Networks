"""WMH volume → normative percentile (placeholder tables; not for clinical use)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent / "data" / "percentile_tables.json"


def _load_bins() -> list[dict[str, Any]]:
    if not _DATA.exists():
        return []
    with open(_DATA, encoding="utf-8") as f:
        raw = json.load(f)
    return list(raw.get("bins") or [])


def _interp_percentile(vol_cc: float, p25: float, p50: float, p75: float, p90: float) -> int:
    """Piecewise linear map volume → 1–99 percentile band."""
    if vol_cc <= p25:
        t = vol_cc / max(p25, 1e-6)
        return max(1, min(24, int(25 * t)))
    if vol_cc <= p50:
        t = (vol_cc - p25) / max(p50 - p25, 1e-6)
        return int(25 + 25 * t)
    if vol_cc <= p75:
        t = (vol_cc - p50) / max(p75 - p50, 1e-6)
        return int(50 + 25 * t)
    if vol_cc <= p90:
        t = (vol_cc - p75) / max(p90 - p75, 1e-6)
        return int(75 + 15 * t)
    t = min(1.0, (vol_cc - p90) / max(p90, 1e-3))
    return min(99, int(90 + 9 * t))


def volume_percentile_for_age(vol_cc: float, age: int, sex: str | None) -> tuple[int, str]:
    """
    Returns (estimated_percentile, note). Sex currently unused in placeholder bins.
    """
    _ = (sex or "").strip().upper()
    bins = _load_bins()
    if not bins:
        return 50, "Normative table missing; percentile defaulted."
    chosen = None
    for b in bins:
        lo = int(b.get("age_min", 0))
        hi = int(b.get("age_max", 120))
        if lo <= age <= hi:
            chosen = b
            break
    if chosen is None:
        chosen = bins[-1]
    p25 = float(chosen["p25_cc"])
    p50 = float(chosen["p50_cc"])
    p75 = float(chosen["p75_cc"])
    p90 = float(chosen["p90_cc"])
    pct = _interp_percentile(float(vol_cc), p25, p50, p75, p90)
    note = (
        f"Age-stratified WMH volume vs placeholder normative bin [{chosen.get('age_min')}-{chosen.get('age_max')}y]. "
        "Not validated for patient care."
    )
    return pct, note

