"""Radiologist feedback events (neurosight.feedback.v1). Persist and measure only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FEEDBACK_SCHEMA = "neurosight.feedback.v1"

FEEDBACK_CODES_V1 = frozenset(
    {
        "agree",
        "overcall",
        "undercall",
        "wrong_anatomy",
        "wrong_delta",
        "useless",
    }
)
# Coarse UI/API values mapped on write. Existing stored rows are left intact.
LEGACY_CODE_MAP = {
    "disagree": "undercall",
    "partial": "useless",
}
LEGACY_FEEDBACK_CODES = frozenset(LEGACY_CODE_MAP)


def normalize_feedback_code(verdict: str) -> str:
    return (verdict or "").lower().strip()


def map_feedback_code(verdict: str) -> tuple[str, str]:
    """Return (v1_code, raw). Legacy disagree→undercall, partial→useless."""
    raw = normalize_feedback_code(verdict)
    return LEGACY_CODE_MAP.get(raw, raw), raw


def is_allowed_feedback_code(verdict: str) -> bool:
    raw = normalize_feedback_code(verdict)
    return raw in FEEDBACK_CODES_V1 or raw in LEGACY_FEEDBACK_CODES


def _parse_iso(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def measurements_unedited(codes: list[str] | tuple[str, ...] | None = None, *, explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    if not codes:
        return True
    return map_feedback_code(str(codes[0]))[0] == "agree"


def _seconds_between(a: Any, b: Any) -> int | None:
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None or db is None:
        return None
    return max(0, int((db - da).total_seconds()))


def normalize_engine_versions(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for key in ("wmh", "llm", "validator", "triage"):
        if src.get(key) not in (None, ""):
            out[key] = src[key]
    if not out.get("wmh") and src.get("model") and "wmh" in str(src.get("model") or "").lower():
        out["wmh"] = src.get("model_version") or src.get("model")
    if not out.get("triage") and src.get("triage_model"):
        out["triage"] = src.get("triage_model")
    if not out.get("validator") and src.get("validator_status"):
        out["validator"] = src.get("validator_status")
    if not out.get("llm") and src.get("generated_by"):
        out["llm"] = src.get("generated_by")
    return out


def engine_versions_from_run(model_run: dict[str, Any] | None) -> dict[str, Any]:
    mr = model_run if isinstance(model_run, dict) else {}
    name = str(mr.get("model_name") or mr.get("model") or "")
    ver = str(mr.get("model_version") or "v1")
    blob: dict[str, Any] = {}
    if "wmh" in name.lower() or name == "unet_3d_wmh":
        blob["wmh"] = ver
    from src.ingest.path import is_triage_model

    if is_triage_model(name):
        blob["triage"] = ver
    prov = mr.get("provenance") if isinstance(mr.get("provenance"), dict) else {}
    blob["llm"] = prov.get("generated_by") or mr.get("llm")
    blob["validator"] = prov.get("validator_status") or mr.get("validator")
    return normalize_engine_versions(blob)


def build_feedback_event(
    *,
    feedback_id: str,
    audit_id: str,
    report_id: str | None = None,
    study_uid: str | None = None,
    codes: list[str],
    submitted_by: str,
    submitted_at: str,
    engine_versions: dict[str, Any] | None = None,
    optional_note: str | None = None,
    measurements_unedited: bool | None = None,
    ingest_at: str | None = None,
    draft_ready_at: str | None = None,
    time_to_draft_s: int | None = None,
    time_to_feedback_s: int | None = None,
) -> dict[str, Any]:
    mapped: list[str] = []
    raw_codes: list[str] = []
    for c in codes:
        if not c:
            continue
        v1, raw = map_feedback_code(c)
        mapped.append(v1)
        raw_codes.append(raw)
    if not mapped:
        mapped = ["agree"]
        raw_codes = ["agree"]
    primary = mapped[0]
    unedited = True if measurements_unedited is None else bool(measurements_unedited)
    if measurements_unedited is None:
        unedited = primary == "agree"
    draft_s = time_to_draft_s
    if draft_s is None:
        draft_s = _seconds_between(ingest_at, draft_ready_at)
    fb_s = time_to_feedback_s
    if fb_s is None:
        fb_s = _seconds_between(draft_ready_at or ingest_at, submitted_at)
    return {
        "schema": FEEDBACK_SCHEMA,
        "feedback_id": feedback_id,
        "audit_id": str(audit_id).strip(),
        "report_id": report_id,
        "study_uid": study_uid,
        "engine_versions": normalize_engine_versions(engine_versions),
        "submitted_by": submitted_by,
        "submitted_at": submitted_at,
        "timing": {
            "ingest_at": ingest_at,
            "draft_ready_at": draft_ready_at,
            "feedback_at": submitted_at,
            "time_to_draft_s": draft_s,
            "time_to_feedback_s": fb_s,
        },
        "codes": mapped,
        "codes_raw": raw_codes,
        "optional_note": (optional_note or "")[:500] or None,
        "measurements_unedited": unedited,
    }


def aggregate_feedback_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute time-to-draft, time-to-feedback, % unedited, codes by engine version."""
    drafts: list[float] = []
    feedbacks: list[float] = []
    unedited = 0
    by_engine: dict[str, dict[str, int]] = {}
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        ev = row.get("feedback_event") if isinstance(row.get("feedback_event"), dict) else row
        n += 1
        timing = ev.get("timing") if isinstance(ev.get("timing"), dict) else {}
        if not timing and isinstance(row.get("timing"), dict):
            timing = row["timing"]
        td = timing.get("time_to_draft_s")
        tf = timing.get("time_to_feedback_s")
        if tf is None and isinstance(row.get("timing"), dict):
            tf = row["timing"].get("time_spent_s")
        try:
            if td is not None:
                drafts.append(float(td))
        except (TypeError, ValueError):
            pass
        try:
            if tf is not None:
                feedbacks.append(float(tf))
        except (TypeError, ValueError):
            pass
        if ev.get("measurements_unedited") is True or row.get("measurements_unedited") is True:
            unedited += 1
        codes = ev.get("codes") if isinstance(ev.get("codes"), list) else [row.get("verdict")]
        primary = normalize_feedback_code(str(codes[0] if codes else ""))
        if primary and primary != "agree":
            evs = ev.get("engine_versions") if isinstance(ev.get("engine_versions"), dict) else {}
            key = "|".join(f"{k}={evs[k]}" for k in ("wmh", "llm", "validator", "triage") if evs.get(k))
            key = key or "unknown"
            bucket = by_engine.setdefault(key, {})
            bucket[primary] = int(bucket.get(primary) or 0) + 1
    return {
        "n": n,
        "time_to_draft_s_mean": round(sum(drafts) / len(drafts), 1) if drafts else None,
        "time_to_feedback_s_mean": round(sum(feedbacks) / len(feedbacks), 1) if feedbacks else None,
        "measurements_unedited_pct": round(unedited / n, 3) if n else 0.0,
        "disagreement_codes_by_engine": by_engine,
    }
