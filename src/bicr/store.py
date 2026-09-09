"""BICR persistence — MongoDB with in-memory fallback."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.db.mongo_client import get_motor_database
from src.db.settings import load_mongo_settings

_BICR_MEMORY: Dict[str, Dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _case_key(case_id: str) -> str:
    return case_id.strip()


async def get_bicr_case(case_id: str) -> Optional[Dict[str, Any]]:
    key = _case_key(case_id)
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        doc = _BICR_MEMORY.get(key)
        return copy.deepcopy(doc) if doc else None
    coll = db[settings.bicr_cases_collection]
    doc = await coll.find_one({"case_id": key})
    return dict(doc) if doc else None


async def upsert_bicr_case(doc: Dict[str, Any]) -> None:
    key = _case_key(str(doc.get("case_id") or ""))
    doc = dict(doc)
    doc["case_id"] = key
    doc["updated_at"] = _utc_now_iso()
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        _BICR_MEMORY[key] = doc
        return
    coll = db[settings.bicr_cases_collection]
    await coll.replace_one({"case_id": key}, doc, upsert=True)


async def list_bicr_cases(
    *,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_motor_database()
    settings = load_mongo_settings()
    lim = max(1, min(int(limit), 200))
    if db is None or not settings.enable:
        rows = list(_BICR_MEMORY.values())
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
        return [copy.deepcopy(r) for r in rows[:lim]]
    coll = db[settings.bicr_cases_collection]
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    cursor = coll.find(q).sort("updated_at", -1).limit(lim)
    return [dict(doc) async for doc in cursor]
