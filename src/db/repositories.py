from __future__ import annotations

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

