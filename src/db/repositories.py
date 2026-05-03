from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.db.mongo_client import get_motor_database
from src.db.settings import load_mongo_settings


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _parse_iso(ts: str | None) -> datetime:
    if not ts:
        return datetime.min
    try:
        # accept "...Z"
        if ts.endswith("Z"):
            ts = ts[:-1]
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.min


async def insert_audit_log_event(payload: Dict[str, Any]) -> None:
    """
    Insert one clinical audit record (docs assistant, etc.) into MongoDB.
    Recommended Atlas index: { timestamp: -1, user_id: 1 } (no TTL for clinical retention).
    """
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return

    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    coll = db[settings.audit_log_collection]
    await coll.insert_one(payload)


async def insert_inference_event(payload: Dict[str, Any]) -> None:
    """
    Insert one inference event into MongoDB.
    If Mongo is disabled/misconfigured, this is a no-op.
    """
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return

    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    payload.setdefault("kind", "inference")

    coll = db[settings.inference_collection]
    await coll.insert_one(payload)


async def insert_clinical_feedback(payload: Dict[str, Any]) -> None:
    """Insert one clinician feedback record into MongoDB (no-op when disabled)."""
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return

    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    payload.setdefault("kind", "clinical_feedback")

    coll = db[settings.feedback_collection]
    await coll.insert_one(payload)


async def get_recent_inference_events(limit: int = 25) -> List[Dict[str, Any]]:
    """Return latest inference/report events sorted by timestamp desc."""
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    coll = db[settings.inference_collection]
    cursor = coll.find({}, sort=[("timestamp", -1)], limit=int(limit))
    return [doc async for doc in cursor]


async def get_latest_inference_for_study(study_instance_uid: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    coll = db[settings.inference_collection]
    return await coll.find_one({"study_instance_uid": study_instance_uid}, sort=[("timestamp", -1)])


async def get_latest_feedback_for_study(study_instance_uid: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    coll = db[settings.feedback_collection]
    return await coll.find_one({"study_instance_uid": study_instance_uid}, sort=[("timestamp", -1)])


async def get_feedback_map_for_studies(study_uids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Return latest feedback per study UID for a set of UIDs."""
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable or not study_uids:
        return {}
    coll = db[settings.feedback_collection]

    # Fetch all feedback records for these studies, then pick latest in Python.
    cursor = coll.find({"study_instance_uid": {"$in": study_uids}})
    latest: Dict[str, Dict[str, Any]] = {}
    async for doc in cursor:
        uid = doc.get("study_instance_uid")
        if not uid:
            continue
        prev = latest.get(uid)
        if prev is None or _parse_iso(doc.get("timestamp")) > _parse_iso(prev.get("timestamp")):
            latest[uid] = doc
    return latest


async def get_basic_metrics() -> Dict[str, Any]:
    """Simple counters for dashboard; expand later with proper time windows."""
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return {"mongo_enabled": False}
    inf = db[settings.inference_collection]
    fb = db[settings.feedback_collection]
    total_cases = await inf.count_documents({})
    total_feedback = await fb.count_documents({})
    corrected = await fb.count_documents({"feedback": "wrong_class"})
    unclear = await fb.count_documents({"feedback": "unclear"})
    agree = await fb.count_documents({"feedback": "agree"})
    return {
        "mongo_enabled": True,
        "total_cases": total_cases,
        "total_feedback": total_feedback,
        "agree": agree,
        "corrected": corrected,
        "unclear": unclear,
    }


# ----------------------------
# Product workflows (Auths / Inbox / Traces)
# ----------------------------


async def insert_prior_auth(payload: Dict[str, Any]) -> str | None:
    """
    Insert a prior authorization work item.
    Returns inserted id as string when enabled, otherwise None.
    """
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    coll = db[settings.auths_collection]
    res = await coll.insert_one(payload)
    return str(res.inserted_id)


async def list_prior_auths(limit: int = 50) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    coll = db[settings.auths_collection]
    cursor = coll.find({}, sort=[("timestamp", -1)], limit=int(limit))
    return [doc async for doc in cursor]


async def get_prior_auth(auth_id: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    try:
        from bson import ObjectId

        oid = ObjectId(auth_id)
    except Exception:
        return None
    coll = db[settings.auths_collection]
    return await coll.find_one({"_id": oid})


async def insert_inbox_message(payload: Dict[str, Any]) -> str | None:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    coll = db[settings.inbox_collection]
    res = await coll.insert_one(payload)
    return str(res.inserted_id)


async def list_inbox_messages(limit: int = 50) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    coll = db[settings.inbox_collection]
    cursor = coll.find({}, sort=[("timestamp", -1)], limit=int(limit))
    return [doc async for doc in cursor]


async def get_inbox_message(message_id: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    try:
        from bson import ObjectId

        oid = ObjectId(message_id)
    except Exception:
        return None
    coll = db[settings.inbox_collection]
    return await coll.find_one({"_id": oid})


async def insert_agent_trace(payload: Dict[str, Any]) -> str | None:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    coll = db[settings.traces_collection]
    res = await coll.insert_one(payload)
    return str(res.inserted_id)


async def list_agent_traces(limit: int = 50) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    coll = db[settings.traces_collection]
    cursor = coll.find({}, sort=[("timestamp", -1)], limit=int(limit))
    return [doc async for doc in cursor]


async def get_agent_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    try:
        from bson import ObjectId

        oid = ObjectId(trace_id)
    except Exception:
        return None
    coll = db[settings.traces_collection]
    return await coll.find_one({"_id": oid})


# ----------------------------
# Clinical trials (trial + candidate tracker)
# ----------------------------


async def insert_trial(payload: Dict[str, Any]) -> str | None:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    payload.setdefault("status", "active")  # active|paused|closed
    coll = db[settings.trials_collection]
    res = await coll.insert_one(payload)
    return str(res.inserted_id)


async def list_trials(limit: int = 50) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    coll = db[settings.trials_collection]
    cursor = coll.find({}, sort=[("timestamp", -1)], limit=int(limit))
    return [doc async for doc in cursor]


async def get_trial(trial_id: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    try:
        from bson import ObjectId

        oid = ObjectId(trial_id)
    except Exception:
        return None
    coll = db[settings.trials_collection]
    return await coll.find_one({"_id": oid})


async def insert_trial_candidate(payload: Dict[str, Any]) -> str | None:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    payload = dict(payload)
    payload.setdefault("timestamp", _utc_now_iso())
    payload.setdefault("status", "screened")  # screened|eligible|ineligible|contacted|consented|enrolled|declined
    coll = db[settings.trial_candidates_collection]
    res = await coll.insert_one(payload)
    return str(res.inserted_id)


async def list_trial_candidates(limit: int = 50, trial_id: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    coll = db[settings.trial_candidates_collection]
    q: Dict[str, Any] = {}
    if trial_id:
        q["trial_id"] = trial_id
    cursor = coll.find(q, sort=[("timestamp", -1)], limit=int(limit))
    return [doc async for doc in cursor]


async def get_trial_candidate(candidate_id: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return None
    try:
        from bson import ObjectId

        oid = ObjectId(candidate_id)
    except Exception:
        return None
    coll = db[settings.trial_candidates_collection]
    return await coll.find_one({"_id": oid})


_REPORT_DRAFT_MEMORY: Dict[str, Dict[str, Any]] = {}


async def insert_report_draft(doc: Dict[str, Any]) -> None:
    """Persist structured report draft (Mongo when enabled, else in-process store for dev/tests)."""
    db = get_motor_database()
    settings = load_mongo_settings()
    payload = copy.deepcopy(doc)
    if db is None or not settings.enable:
        rid = str(payload.get("report_id") or "")
        if rid:
            _REPORT_DRAFT_MEMORY[rid] = json.loads(json.dumps(payload, default=str))
        return
    payload.setdefault("timestamp", _utc_now_iso())
    coll = db[settings.reports_collection]
    await coll.insert_one(payload)


async def get_report_draft(report_id: str) -> Optional[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        doc = _REPORT_DRAFT_MEMORY.get(report_id)
        return copy.deepcopy(doc) if doc else None
    coll = db[settings.reports_collection]
    doc = await coll.find_one({"report_id": report_id})
    if doc and "_id" in doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


async def replace_report_draft(report_id: str, doc: Dict[str, Any]) -> bool:
    db = get_motor_database()
    settings = load_mongo_settings()
    payload = copy.deepcopy(doc)
    if db is None or not settings.enable:
        if report_id not in _REPORT_DRAFT_MEMORY:
            return False
        _REPORT_DRAFT_MEMORY[report_id] = json.loads(json.dumps(payload, default=str))
        return True
    coll = db[settings.reports_collection]
    res = await coll.replace_one({"report_id": report_id}, payload, upsert=False)
    return res.matched_count > 0


async def update_report_draft_fields(report_id: str, fields: Dict[str, Any]) -> bool:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        cur = _REPORT_DRAFT_MEMORY.get(report_id)
        if not cur:
            return False
        cur = json.loads(json.dumps(cur, default=str))
        cur.update(fields)
        _REPORT_DRAFT_MEMORY[report_id] = cur
        return True
    coll = db[settings.reports_collection]
    res = await coll.update_one({"report_id": report_id}, {"$set": fields})
    return res.matched_count > 0


_STRUCTURED_CLINICAL_FB_MEMORY: List[Dict[str, Any]] = []
_CLINICAL_FB_INDEXES_ENSURED = False


async def _ensure_clinical_feedback_indexes(coll: Any) -> None:
    global _CLINICAL_FB_INDEXES_ENSURED
    if _CLINICAL_FB_INDEXES_ENSURED:
        return
    try:
        await coll.create_index([("feedback_id", 1)], unique=True, sparse=True)
        await coll.create_index([("case_id", 1)])
        await coll.create_index([("study_instance_uid", 1)])
        await coll.create_index([("reviewer.user_id", 1), ("timing.submitted_at", -1)])
        await coll.create_index([("verdict", 1), ("timing.submitted_at", -1)])
        await coll.create_index([("used_for_retraining", 1)])
    except Exception:
        pass
    _CLINICAL_FB_INDEXES_ENSURED = True


async def insert_structured_clinical_feedback(payload: Dict[str, Any]) -> None:
    """Insert schema v1.0 structured radiologist feedback (same collection as legacy rows when Mongo on)."""
    db = get_motor_database()
    settings = load_mongo_settings()
    doc = dict(payload)
    doc.setdefault("timestamp", _utc_now_iso())
    doc.setdefault("kind", "clinical_feedback_structured")

    if db is None or not settings.enable:
        _STRUCTURED_CLINICAL_FB_MEMORY.append(json.loads(json.dumps(doc, default=str)))
        return

    coll = db[settings.feedback_collection]
    await _ensure_clinical_feedback_indexes(coll)
    await coll.insert_one(doc)


async def get_latest_structured_feedback_for_case(case_id: str) -> Optional[Dict[str, Any]]:
    """Latest v1.0 structured feedback for a study / case id."""
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        cand = [
            x
            for x in _STRUCTURED_CLINICAL_FB_MEMORY
            if x.get("schema_version") == "1.0"
            and (x.get("case_id") == case_id or x.get("study_instance_uid") == case_id)
        ]
        if not cand:
            return None
        return max(cand, key=lambda x: _parse_iso(x.get("timestamp")))

    coll = db[settings.feedback_collection]
    q = {
        "schema_version": "1.0",
        "$or": [{"case_id": case_id}, {"study_instance_uid": case_id}],
    }
    return await coll.find_one(q, sort=[("timestamp", -1)])


async def aggregate_clinical_feedback_stats(user_id: str) -> Dict[str, Any]:
    """Rolling monthly stats for GET /clinical/feedback/stats."""
    from datetime import date, datetime, time, timezone

    month_start = datetime.combine(date.today().replace(day=1), time.min, tzinfo=timezone.utc)

    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        rows = [
            x
            for x in _STRUCTURED_CLINICAL_FB_MEMORY
            if x.get("schema_version") == "1.0" and (x.get("reviewer") or {}).get("user_id") == user_id
        ]
        month_iso = month_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows_m = [x for x in rows if str(x.get("timestamp") or "") >= month_iso]
        if not rows_m:
            return {"reviewed_this_month": 0, "agreement_rate": 0.0, "avg_time_s": 0}
        total = len(rows_m)
        agree = sum(1 for x in rows_m if x.get("verdict") == "agree")
        times = [int((x.get("timing") or {}).get("time_spent_s") or 0) for x in rows_m]
        avg_t = sum(times) / max(len(times), 1)
        return {
            "reviewed_this_month": total,
            "agreement_rate": round(agree / total, 3) if total else 0.0,
            "avg_time_s": int(round(avg_t)),
        }

    coll = db[settings.feedback_collection]
    month_iso = month_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    pipeline = [
        {
            "$match": {
                "schema_version": "1.0",
                "reviewer.user_id": user_id,
                "timestamp": {"$gte": month_iso},
            }
        },
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "agreements": {"$sum": {"$cond": [{"$eq": ["$verdict", "agree"]}, 1, 0]}},
                "avg_time_s": {"$avg": "$timing.time_spent_s"},
            }
        },
    ]
    cur = coll.aggregate(pipeline)
    result = await cur.to_list(1)
    if not result:
        return {"reviewed_this_month": 0, "agreement_rate": 0.0, "avg_time_s": 0}
    r = result[0]
    total = int(r.get("total") or 0)
    agr = int(r.get("agreements") or 0)
    return {
        "reviewed_this_month": total,
        "agreement_rate": round(agr / total, 3) if total else 0.0,
        "avg_time_s": int(round(float(r.get("avg_time_s") or 0))),
    }


async def list_recent_structured_feedback(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        rows = [
            x
            for x in _STRUCTURED_CLINICAL_FB_MEMORY
            if x.get("schema_version") == "1.0" and (x.get("reviewer") or {}).get("user_id") == user_id
        ]
        rows.sort(key=lambda x: _parse_iso(x.get("timestamp")), reverse=True)
        return rows[: int(limit)]

    coll = db[settings.feedback_collection]
    cursor = coll.find({"schema_version": "1.0", "reviewer.user_id": user_id}).sort("timestamp", -1).limit(int(limit))
    return [doc async for doc in cursor]


async def search_rag_chunks(query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Placeholder for MongoDB Atlas Vector Search retrieval.
    Full implementation is added in the RAG todo.
    """
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []

    # Atlas Vector Search is configured via an aggregation pipeline.
    # We'll implement the real pipeline in `src/rag/` later.
    return []

