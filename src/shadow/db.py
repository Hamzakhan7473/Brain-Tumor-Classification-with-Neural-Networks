"""MongoDB operations for ``shadow_cases`` (Phase B shadow queue)."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from src.db.mongo_client import get_motor_database
from src.db.settings import load_mongo_settings

_shadow_indexes_checked = False


async def shadow_mongo_available() -> bool:
    coll, _ = await _coll()
    return coll is not None


async def _coll() -> Tuple[Any, Any]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None, None
    return db[settings.shadow_cases_collection], settings


async def ensure_shadow_indexes() -> None:
    """Create recommended indexes once per process (idempotent)."""
    global _shadow_indexes_checked
    if _shadow_indexes_checked:
        return
    coll, _ = await _coll()
    if coll is None:
        return
    specs = [
        ([("received_at", DESCENDING)], {}),
        ([("site_id", ASCENDING), ("status", ASCENDING)], {}),
        ([("feedback.status", ASCENDING), ("received_at", DESCENDING)], {}),
        ([("assignment.radiologist_id", ASCENDING), ("feedback.status", ASCENDING)], {}),
        ([("study_uid", ASCENDING)], {"unique": True}),
    ]
    for keys, kw in specs:
        try:
            await coll.create_index(keys, **kw)
        except Exception:
            pass
    _shadow_indexes_checked = True


def _iso(dt: Any) -> Any:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return dt


def _conv(v: Any) -> Any:
    if isinstance(v, datetime):
        return _iso(v)
    if isinstance(v, dict):
        return {k: _conv(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_conv(x) for x in v]
    return v


def serialize_case(doc: Dict[str, Any]) -> Dict[str, Any]:
    raw = dict(doc)
    oid = raw.pop("_id", None)
    out = {k: _conv(v) for k, v in raw.items()}
    out["id"] = str(oid) if oid is not None else None
    return out


def verdict_to_feedback_status(verdict: str) -> str:
    v = (verdict or "").lower().strip()
    if v == "agree":
        return "confirmed"
    if v == "disagree":
        return "disagreed"
    if v == "partial":
        return "needs_more_info"
    return "pending"


def build_queue_filter(
    *,
    status: Optional[List[str]],
    site_id: Optional[str],
    feedback: Optional[str],
    assigned_to: Optional[str],
    flagged: Optional[bool],
    search: Optional[str],
) -> Dict[str, Any]:
    q: Dict[str, Any] = {"shadow_mode": True}
    if status:
        q["status"] = {"$in": status}
    if site_id:
        q["site_id"] = site_id
    if feedback:
        q["feedback.status"] = feedback
    if assigned_to:
        q["assignment.radiologist_id"] = assigned_to
    if flagged is True:
        q["flags.0"] = {"$exists": True}
    if search and str(search).strip():
        esc = re.escape(str(search).strip())
        q["$or"] = [
            {"study_uid": {"$regex": f"^{esc}", "$options": "i"}},
            {"site_id": {"$regex": esc, "$options": "i"}},
        ]
    return q


def _sort_field(sort: str) -> str:
    allowed = {"received_at": "received_at", "finished_at": "model_run.finished_at"}
    return allowed.get((sort or "").strip(), "received_at")


async def list_shadow_queue(
    *,
    status: Optional[List[str]] = None,
    site_id: Optional[str] = None,
    feedback: Optional[str] = None,
    assigned_to: Optional[str] = None,
    flagged: Optional[bool] = None,
    search: Optional[str] = None,
    sort: str = "received_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    coll, _ = await _coll()
    if coll is None:
        return [], 0
    await ensure_shadow_indexes()
    q = build_queue_filter(
        status=status,
        site_id=site_id,
        feedback=feedback,
        assigned_to=assigned_to,
        flagged=flagged,
        search=search,
    )
    sort_dir = DESCENDING if (order or "desc").lower() == "desc" else ASCENDING
    sk = _sort_field(sort)
    total = await coll.count_documents(q)
    cur = coll.find(q).sort([(sk, sort_dir)]).skip(int(offset)).limit(int(limit))
    items = [serialize_case(d) async for d in cur]
    return items, int(total)


async def compute_shadow_kpis() -> Dict[str, Any]:
    coll, _ = await _coll()
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    yesterday_start = today_start - timedelta(days=1)
    week_start = now - timedelta(days=7)
    sla_cutoff = now - timedelta(hours=24)
    listen_cutoff = now - timedelta(minutes=5)
    last24 = now - timedelta(hours=24)
    base = {"shadow_mode": True}

    if coll is None:
        return {
            "total_today": 0,
            "total_yesterday": 0,
            "delta_vs_yesterday": 0,
            "pending_feedback": 0,
            "sla_breach_count": 0,
            "agreement_rate_7d": 0.0,
            "mean_inference_ms_24h": 0.0,
            "listener_status": "stale",
            "last_received": None,
            "mongo_enabled": False,
        }

    await ensure_shadow_indexes()

    total_today = await coll.count_documents({**base, "received_at": {"$gte": today_start}})
    total_yesterday = await coll.count_documents(
        {**base, "received_at": {"$gte": yesterday_start, "$lt": today_start}}
    )
    pending_feedback = await coll.count_documents({**base, "feedback.status": "pending"})
    sla_breach_count = await coll.count_documents(
        {**base, "feedback.status": "pending", "received_at": {"$lte": sla_cutoff}}
    )

    reviewed = await coll.count_documents(
        {
            **base,
            "feedback.submitted_at": {"$gte": week_start},
            "feedback.status": {"$in": ["confirmed", "disagreed", "skipped", "needs_more_info"]},
        }
    )
    confirmed = await coll.count_documents(
        {**base, "feedback.submitted_at": {"$gte": week_start}, "feedback.status": "confirmed"}
    )
    agreement_rate_7d = (confirmed / reviewed) if reviewed else 0.0

    pipeline = [
        {"$match": {**base, "model_run.finished_at": {"$gte": last24}, "model_run.duration_ms": {"$exists": True}}},
        {"$group": {"_id": None, "avg_ms": {"$avg": "$model_run.duration_ms"}}},
    ]
    mean_inference_ms_24h = 0.0
    async for row in coll.aggregate(pipeline):
        v = row.get("avg_ms")
        if isinstance(v, (int, float)):
            mean_inference_ms_24h = float(v)

    last_doc = await coll.find_one(base, sort=[("received_at", DESCENDING)])
    last_received = last_doc.get("received_at") if last_doc else None
    listener_status = "stale"
    if isinstance(last_received, datetime):
        lr = last_received if last_received.tzinfo else last_received.replace(tzinfo=timezone.utc)
        if lr >= listen_cutoff:
            listener_status = "live"

    last_iso = _iso(last_received) if last_received else None

    return {
        "total_today": int(total_today),
        "total_yesterday": int(total_yesterday),
        "delta_vs_yesterday": int(total_today - total_yesterday),
        "pending_feedback": int(pending_feedback),
        "sla_breach_count": int(sla_breach_count),
        "agreement_rate_7d": round(float(agreement_rate_7d), 4),
        "mean_inference_ms_24h": round(mean_inference_ms_24h, 1),
        "listener_status": listener_status,
        "last_received": last_iso,
        "mongo_enabled": True,
    }


async def get_shadow_case(study_uid: str) -> Optional[Dict[str, Any]]:
    coll, _ = await _coll()
    if coll is None:
        return None
    doc = await coll.find_one({"study_uid": study_uid})
    return doc


async def is_shadow_study(study_uid: str) -> bool:
    doc = await get_shadow_case(study_uid)
    return bool(doc and doc.get("shadow_mode") is True)


async def insert_shadow_case(doc: Dict[str, Any]) -> None:
    coll, _ = await _coll()
    if coll is None:
        raise RuntimeError("MongoDB is not configured")
    await ensure_shadow_indexes()
    doc = dict(doc)
    doc["shadow_mode"] = True
    if "received_at" not in doc:
        doc["received_at"] = datetime.now(timezone.utc)
    try:
        await coll.insert_one(doc)
    except DuplicateKeyError:
        raise


async def update_shadow_assignment(study_uid: str, radiologist_id: str, radiologist_name: str) -> int:
    coll, _ = await _coll()
    if coll is None:
        return 0
    res = await coll.update_one(
        {"study_uid": study_uid, "shadow_mode": True},
        {
            "$set": {
                "assignment.radiologist_id": radiologist_id,
                "assignment.radiologist_name": radiologist_name,
                "assignment.assigned_at": datetime.now(timezone.utc),
            }
        },
    )
    return int(res.modified_count)


async def submit_shadow_feedback(
    study_uid: str,
    *,
    verdict: str,
    ground_truth: Optional[dict],
    notes: Optional[str],
    submitted_by: str,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    coll, _ = await _coll()
    if coll is None:
        return False, None
    case = await coll.find_one({"study_uid": study_uid})
    if not case:
        return False, None
    if not case.get("shadow_mode"):
        return False, case
    v = (verdict or "").lower().strip()
    received_at = case.get("received_at")
    if isinstance(received_at, datetime):
        ra = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
        ttr = (datetime.now(timezone.utc) - ra).total_seconds()
    else:
        ttr = 0.0
    fb_status = verdict_to_feedback_status(v)
    await coll.update_one(
        {"study_uid": study_uid, "shadow_mode": True},
        {
            "$set": {
                "feedback.status": fb_status,
                "feedback.verdict": v,
                "feedback.ground_truth": ground_truth,
                "feedback.notes": (notes or "")[:500] if notes else None,
                "feedback.submitted_by": submitted_by,
                "feedback.submitted_at": datetime.now(timezone.utc),
                "feedback.time_to_review_s": int(ttr),
                "status": "complete",
            }
        },
    )
    return True, case


async def flag_shadow_case(study_uid: str, reason: str, raised_by: str) -> int:
    coll, _ = await _coll()
    if coll is None:
        return 0
    res = await coll.update_one(
        {"study_uid": study_uid, "shadow_mode": True},
        {
            "$set": {"status": "flagged"},
            "$push": {
                "flags": {
                    "type": "manual_flag",
                    "raised_at": datetime.now(timezone.utc),
                    "details": reason[:2000],
                    "raised_by": raised_by,
                }
            },
        },
    )
    return int(res.modified_count)


async def retry_shadow_case(study_uid: str) -> int:
    coll, _ = await _coll()
    if coll is None:
        return 0
    res = await coll.update_one(
        {"study_uid": study_uid, "shadow_mode": True},
        {"$set": {"status": "queued", "model_run": {}}},
    )
    return int(res.modified_count)


async def export_shadow_cases(
    *,
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    coll, _ = await _coll()
    if coll is None:
        return []
    q = {
        "shadow_mode": True,
        "received_at": {"$gte": start, "$lte": end},
    }
    cur = coll.find(q).sort("received_at", ASCENDING)
    return [serialize_case(d) async for d in cur]


async def shadow_analytics() -> Dict[str, Any]:
    """Rolling QA stats for hospital-facing dashboards."""
    coll, _ = await _coll()
    if coll is None:
        return {"mongo_enabled": False}
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    base = {"shadow_mode": True, "feedback.submitted_at": {"$gte": since}}

    by_label: Dict[str, Dict[str, int]] = {}
    cur = coll.find({**base, "feedback.verdict": {"$exists": True}})
    async for doc in cur:
        label = str((doc.get("model_run") or {}).get("label") or "unknown")
        verdict = str((doc.get("feedback") or {}).get("verdict") or "")
        by_label.setdefault(label, {"confirmed": 0, "disagreed": 0, "partial": 0})
        if verdict == "agree":
            by_label[label]["confirmed"] += 1
        elif verdict == "disagree":
            by_label[label]["disagreed"] += 1
        elif verdict == "partial":
            by_label[label]["partial"] += 1

    conf_vals: List[float] = []
    ttr_vals: List[float] = []
    notes_sample: List[str] = []
    c2 = coll.find({**base}).limit(400)
    async for doc in c2:
        mr = doc.get("model_run") or {}
        c = mr.get("confidence")
        if isinstance(c, (int, float)):
            conf_vals.append(float(c))
        fb = doc.get("feedback") or {}
        t = fb.get("time_to_review_s")
        if isinstance(t, (int, float)):
            ttr_vals.append(float(t))
        if fb.get("verdict") == "disagree" and fb.get("notes"):
            notes_sample.append(str(fb.get("notes"))[:200])
            if len(notes_sample) >= 25:
                break

    def _hist(vals: List[float], bins: List[float]) -> Dict[str, int]:
        out = {f"<{bins[0]}": 0}
        for i in range(len(bins) - 1):
            out[f"{bins[i]}-{bins[i + 1]}"] = 0
        out[f">{bins[-1]}"] = 0
        for v in vals:
            if v < bins[0]:
                out[f"<{bins[0]}"] += 1
            elif v >= bins[-1]:
                out[f">{bins[-1]}"] += 1
            else:
                for i in range(len(bins) - 1):
                    if bins[i] <= v < bins[i + 1]:
                        key = f"{bins[i]}-{bins[i + 1]}"
                        out[key] += 1
                        break
        return out

    conf_bins = [0.0, 0.5, 0.65, 0.8, 0.9, 1.01]
    ttr_bins = [0, 300, 900, 3600, 86400, 1e12]

    return {
        "mongo_enabled": True,
        "window_days": 30,
        "agreement_by_label": by_label,
        "confidence_distribution": _hist(conf_vals, conf_bins),
        "time_to_feedback_seconds": _hist(ttr_vals, ttr_bins),
        "disagreement_notes_sample": notes_sample[:20],
    }
