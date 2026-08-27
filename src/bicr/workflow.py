"""BICR workflow — dual read, adjudication, time-point lock, e-signature hashing."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Tuple

from src.bicr.store import get_bicr_case, list_bicr_cases, upsert_bicr_case

ReaderRole = Literal["reader1", "reader2", "adjudicator"]
ReaderSlot = Literal[1, 2]

SCHEMA_VERSION = "1.0"
PART11_MEANING = (
    "I attest that this electronic signature is the legally binding equivalent of my "
    "handwritten signature and that this read represents my independent blinded assessment."
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _append_audit(doc: Dict[str, Any], event: str, user_id: str, detail: Dict[str, Any]) -> None:
    trail = list(doc.get("audit_trail") or [])
    prior = {
        "status": doc.get("status"),
        "timepoint_locked": doc.get("timepoint_locked"),
        "read_1": bool(doc.get("read_1")),
        "read_2": bool(doc.get("read_2")),
        "adjudication": bool(doc.get("adjudication")),
    }
    trail.append(
        {
            "event": event,
            "user_id": user_id,
            "timestamp": _utc_now_iso(),
            "prior_state": prior,
            "detail": detail,
            "state_hash": _sha256_obj(prior),
        }
    )
    doc["audit_trail"] = trail[-200:]


def _normalize_gt(gt: Optional[dict]) -> dict:
    return dict(gt or {})


def _reads_agree(r1: dict, r2: dict) -> bool:
    if str(r1.get("verdict")) != str(r2.get("verdict")):
        return False
    return _normalize_gt(r1.get("ground_truth")) == _normalize_gt(r2.get("ground_truth"))


def _effective_outcome(read: dict) -> dict:
    return {
        "verdict": read.get("verdict"),
        "ground_truth": _normalize_gt(read.get("ground_truth")),
    }


def _compute_status(doc: Dict[str, Any]) -> str:
    if doc.get("timepoint_locked"):
        return "locked"
    r1, r2 = doc.get("read_1"), doc.get("read_2")
    if doc.get("adjudication"):
        return "complete"
    if r1 and r2:
        if _reads_agree(r1, r2):
            return "complete"
        return "pending_adjudication"
    return "pending_reads"


def _consensus_from_reads(doc: Dict[str, Any]) -> Optional[dict]:
    r1, r2 = doc.get("read_1"), doc.get("read_2")
    if r1 and r2 and _reads_agree(r1, r2):
        return _effective_outcome(r1)
    if doc.get("adjudication"):
        return _effective_outcome(doc["adjudication"])
    return None


async def enroll_bicr_case(
    *,
    case_id: str,
    user_id: str,
    case_review: dict,
    subject_id: Optional[str] = None,
    visit: Optional[str] = None,
    timepoint: Optional[str] = None,
    blind_model: bool = True,
) -> Dict[str, Any]:
    key = case_id.strip()
    existing = await get_bicr_case(key)
    if existing:
        return existing

    bicr_id = f"bicr_{secrets.token_hex(8)}"
    doc: Dict[str, Any] = {
        "bicr_id": bicr_id,
        "case_id": key,
        "study_uid": key,
        "schema_version": SCHEMA_VERSION,
        "subject_id": (subject_id or "").strip() or None,
        "visit": (visit or "").strip() or None,
        "timepoint": (timepoint or "baseline").strip(),
        "timepoint_locked": False,
        "locked_at": None,
        "locked_by": None,
        "blind_model": bool(blind_model),
        "status": "pending_reads",
        "task": case_review.get("task") or "classification",
        "case_review_snapshot": case_review,
        "read_1": None,
        "read_2": None,
        "adjudication": None,
        "consensus": None,
        "audit_trail": [],
        "created_at": _utc_now_iso(),
        "created_by": user_id,
        "updated_at": _utc_now_iso(),
    }
    _append_audit(doc, "enrolled", user_id, {"bicr_id": bicr_id, "timepoint": doc["timepoint"]})
    await upsert_bicr_case(doc)
    return doc


def _blind_case_review(doc: Dict[str, Any], role: ReaderRole) -> dict:
    snap = dict(doc.get("case_review_snapshot") or {})
    mr = dict(snap.get("model_run") or {})
    if doc.get("blind_model") and role in ("reader1", "reader2"):
        mr = dict(mr)
        mr["label"] = "—"
        mr["label_class"] = "warn"
        mr["confidence"] = 0.0
        mr["class_probabilities"] = {}
        if mr.get("wmh_metrics"):
            wm = dict(mr["wmh_metrics"])
            wm.pop("severity_grade", None)
            mr["wmh_metrics"] = wm
        snap["model_run"] = mr
    snap["feedback"] = None
    return snap


def _public_bicr_state(doc: Dict[str, Any], role: ReaderRole) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "bicr_id": doc.get("bicr_id"),
        "case_id": doc.get("case_id"),
        "subject_id": doc.get("subject_id"),
        "visit": doc.get("visit"),
        "timepoint": doc.get("timepoint"),
        "timepoint_locked": bool(doc.get("timepoint_locked")),
        "status": doc.get("status"),
        "blind_model": bool(doc.get("blind_model")),
        "task": doc.get("task"),
        "consensus": doc.get("consensus"),
        "part11_meaning": PART11_MEANING,
        "reader_slots": {
            "read_1_submitted": bool(doc.get("read_1")),
            "read_2_submitted": bool(doc.get("read_2")),
            "adjudication_submitted": bool(doc.get("adjudication")),
        },
    }
    if role == "reader1":
        out["my_slot"] = 1
        out["can_submit"] = not doc.get("read_1") and not doc.get("timepoint_locked") and doc.get("status") == "pending_reads"
    elif role == "reader2":
        out["my_slot"] = 2
        out["can_submit"] = not doc.get("read_2") and not doc.get("timepoint_locked") and doc.get("status") == "pending_reads"
    else:
        out["my_slot"] = None
        out["can_submit"] = doc.get("status") == "pending_adjudication" and not doc.get("adjudication")
        if doc.get("read_1"):
            out["read_1_summary"] = {
                "verdict": doc["read_1"].get("verdict"),
                "ground_truth": doc["read_1"].get("ground_truth"),
                "submitted_at": (doc["read_1"].get("timing") or {}).get("submitted_at"),
            }
        if doc.get("read_2"):
            out["read_2_summary"] = {
                "verdict": doc["read_2"].get("verdict"),
                "ground_truth": doc["read_2"].get("ground_truth"),
                "submitted_at": (doc["read_2"].get("timing") or {}).get("submitted_at"),
            }
    return out


async def get_bicr_review(case_id: str, role: ReaderRole) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    doc = await get_bicr_case(case_id)
    if not doc:
        return None, "BICR case not enrolled"
    return {
        "bicr": _public_bicr_state(doc, role),
        "case_review": _blind_case_review(doc, role),
    }, None


def _build_read_record(
    *,
    user_id: str,
    slot: ReaderSlot,
    verdict: str,
    ground_truth: Optional[dict],
    error_categories: list[str],
    clinical_notes: Optional[str],
    time_spent_s: int,
    signature: dict,
) -> dict:
    if not signature.get("meaning_acknowledged"):
        raise ValueError("Part 11 meaning must be acknowledged")
    payload = {
        "reader_slot": slot,
        "verdict": verdict,
        "ground_truth": _normalize_gt(ground_truth),
        "error_categories": list(error_categories or []),
        "clinical_notes": (clinical_notes or "")[:500] or None,
        "time_spent_s": int(time_spent_s),
    }
    sig_hash = _sha256_obj({**payload, "signer": signature.get("signer_name")})
    return {
        **payload,
        "reviewer": {
            "user_id": user_id,
            "display_name": signature.get("signer_name") or user_id,
            "role": signature.get("signer_role") or f"reader_{slot}",
            "credentials": signature.get("credentials"),
            "npi_or_license": signature.get("npi_or_license"),
        },
        "timing": {"submitted_at": _utc_now_iso()},
        "electronic_signature": {
            "meaning": PART11_MEANING,
            "meaning_acknowledged": True,
            "content_hash_sha256": sig_hash,
            "signed_at": _utc_now_iso(),
        },
    }


async def submit_bicr_read(
    *,
    case_id: str,
    user_id: str,
    reader_slot: ReaderSlot,
    verdict: str,
    ground_truth: Optional[dict],
    error_categories: list[str],
    clinical_notes: Optional[str],
    time_spent_s: int,
    signature: dict,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    doc = await get_bicr_case(case_id)
    if not doc:
        return None, "BICR case not enrolled"
    if doc.get("timepoint_locked"):
        return None, "Timepoint is locked — no further reads permitted"
    if doc.get("status") not in ("pending_reads",):
        return None, f"Case not accepting reads (status={doc.get('status')})"

    slot_key = "read_1" if reader_slot == 1 else "read_2"
    if doc.get(slot_key):
        return None, f"Reader {reader_slot} read already submitted"

    other_key = "read_2" if reader_slot == 1 else "read_1"
    other = doc.get(other_key)
    if other and (other.get("reviewer") or {}).get("user_id") == user_id:
        return None, "Same user cannot submit both independent reads"

    read = _build_read_record(
        user_id=user_id,
        slot=reader_slot,
        verdict=verdict,
        ground_truth=ground_truth,
        error_categories=error_categories,
        clinical_notes=clinical_notes,
        time_spent_s=time_spent_s,
        signature=signature,
    )
    doc[slot_key] = read
    doc["status"] = _compute_status(doc)
    if doc["status"] == "complete" and doc.get("read_1") and doc.get("read_2"):
        doc["consensus"] = _consensus_from_reads(doc)
    _append_audit(doc, f"read_{reader_slot}_submitted", user_id, {"content_hash": read["electronic_signature"]["content_hash_sha256"]})
    await upsert_bicr_case(doc)
    return doc, None


async def submit_bicr_adjudication(
    *,
    case_id: str,
    user_id: str,
    verdict: str,
    ground_truth: Optional[dict],
    clinical_notes: Optional[str],
    time_spent_s: int,
    signature: dict,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    doc = await get_bicr_case(case_id)
    if not doc:
        return None, "BICR case not enrolled"
    if doc.get("timepoint_locked"):
        return None, "Timepoint is locked"
    if doc.get("status") != "pending_adjudication":
        return None, "Case does not require adjudication"
    if doc.get("adjudication"):
        return None, "Adjudication already submitted"

    payload = {
        "verdict": verdict,
        "ground_truth": _normalize_gt(ground_truth),
        "clinical_notes": (clinical_notes or "")[:500] or None,
        "time_spent_s": int(time_spent_s),
    }
    if not signature.get("meaning_acknowledged"):
        return None, "Part 11 meaning must be acknowledged"
    sig_hash = _sha256_obj({**payload, "signer": signature.get("signer_name")})
    doc["adjudication"] = {
        **payload,
        "reviewer": {
            "user_id": user_id,
            "display_name": signature.get("signer_name") or user_id,
            "role": signature.get("signer_role") or "adjudicator",
            "credentials": signature.get("credentials"),
            "npi_or_license": signature.get("npi_or_license"),
        },
        "timing": {"submitted_at": _utc_now_iso()},
        "electronic_signature": {
            "meaning": PART11_MEANING,
            "meaning_acknowledged": True,
            "content_hash_sha256": sig_hash,
            "signed_at": _utc_now_iso(),
        },
    }
    doc["status"] = "complete"
    doc["consensus"] = _effective_outcome(doc["adjudication"])
    _append_audit(doc, "adjudication_submitted", user_id, {"content_hash": sig_hash})
    await upsert_bicr_case(doc)
    return doc, None


async def lock_bicr_timepoint(case_id: str, user_id: str, reason: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    doc = await get_bicr_case(case_id)
    if not doc:
        return None, "BICR case not enrolled"
    doc["timepoint_locked"] = True
    doc["locked_at"] = _utc_now_iso()
    doc["locked_by"] = user_id
    doc["lock_reason"] = (reason or "").strip() or None
    doc["status"] = "locked"
    _append_audit(doc, "timepoint_locked", user_id, {"reason": doc.get("lock_reason")})
    await upsert_bicr_case(doc)
    return doc, None


async def bicr_queue_for_role(role: ReaderRole, limit: int = 50) -> list[dict]:
    if role == "adjudicator":
        rows = await list_bicr_cases(status="pending_adjudication", limit=limit)
    else:
        rows = await list_bicr_cases(status="pending_reads", limit=limit * 2)
        slot = 1 if role == "reader1" else 2
        key = "read_1" if slot == 1 else "read_2"
        rows = [r for r in rows if not r.get(key) and not r.get("timepoint_locked")]
    out = []
    for r in rows[:limit]:
        out.append(
            {
                "case_id": r.get("case_id"),
                "bicr_id": r.get("bicr_id"),
                "subject_id": r.get("subject_id"),
                "timepoint": r.get("timepoint"),
                "status": r.get("status"),
                "task": r.get("task"),
                "updated_at": r.get("updated_at"),
            }
        )
    return out
