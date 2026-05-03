"""HTTP handler logic for shadow queue routes (keeps src/api/main.py smaller)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from src.inference.audit_log import log_shadow_workflow_event


async def require_shadow_mongo() -> None:
    from src.shadow.db import shadow_mongo_available

    if not await shadow_mongo_available():
        raise HTTPException(
            status_code=503,
            detail="Shadow queue requires MongoDB. Set MONGODB_URI (optional: MONGODB_COLLECTION_SHADOW_CASES).",
        )


def parse_export_range(start: str, end: str) -> tuple[datetime, datetime]:
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid start/end ISO datetime") from exc
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return a, b


async def handle_shadow_queue(
    *,
    status: Optional[List[str]],
    site_id: Optional[str],
    feedback: Optional[str],
    assigned_to: Optional[str],
    flagged: Optional[bool],
    search: Optional[str],
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    from src.shadow.db import compute_shadow_kpis, list_shadow_queue

    await require_shadow_mongo()
    items, total = await list_shadow_queue(
        status=status,
        site_id=site_id,
        feedback=feedback,
        assigned_to=assigned_to,
        flagged=flagged,
        search=search,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    kpis = await compute_shadow_kpis()
    return {"items": items, "total": total, "kpis": kpis}


async def handle_shadow_feedback(
    *,
    study_uid: str,
    verdict: str,
    ground_truth: Optional[dict],
    notes: Optional[str],
    user_id: str,
) -> Dict[str, str]:
    from src.db.repositories import insert_audit_log_event
    from src.shadow.db import get_shadow_case, submit_shadow_feedback

    await require_shadow_mongo()
    v = verdict.lower().strip()
    if v not in {"agree", "disagree", "partial"}:
        raise HTTPException(status_code=400, detail="verdict must be agree | disagree | partial")

    ok, case = await submit_shadow_feedback(
        study_uid, verdict=v, ground_truth=ground_truth, notes=notes, submitted_by=user_id
    )
    if not ok:
        if case is None:
            raise HTTPException(status_code=404, detail="Study not found")
        raise HTTPException(status_code=400, detail="Cannot submit feedback on non-shadow case")

    mr = (case or {}).get("model_run") or {}
    audit_id = log_shadow_workflow_event(
        event_type="shadow_feedback_submitted",
        user_id=user_id,
        payload={
            "study_uid": study_uid,
            "verdict": v,
            "model_label": mr.get("label"),
            "model_confidence": mr.get("confidence"),
        },
    )
    try:
        await insert_audit_log_event(
            {
                "audit_id": audit_id,
                "event_type": "shadow_feedback_submitted",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {
                    "study_uid": study_uid,
                    "verdict": v,
                    "model_label": mr.get("label"),
                    "model_confidence": mr.get("confidence"),
                },
            }
        )
    except Exception:
        pass
    return {"ok": True, "audit_id": audit_id}


async def handle_shadow_assign(*, study_uid: str, rad_id: str, rad_name: str, user_id: str) -> Dict[str, bool]:
    from src.db.repositories import insert_audit_log_event
    from src.shadow.db import get_shadow_case, update_shadow_assignment

    await require_shadow_mongo()
    case = await get_shadow_case(study_uid)
    if not case:
        raise HTTPException(status_code=404, detail="Study not found")
    if not case.get("shadow_mode"):
        raise HTTPException(status_code=400, detail="Cannot assign non-shadow case")
    n = await update_shadow_assignment(study_uid, rad_id, rad_name)
    if not n:
        raise HTTPException(status_code=404, detail="Study not found")
    aid = log_shadow_workflow_event(
        event_type="shadow_case_assigned",
        user_id=user_id,
        payload={"study_uid": study_uid, "radiologist_id": rad_id},
    )
    try:
        await insert_audit_log_event(
            {
                "audit_id": aid,
                "event_type": "shadow_case_assigned",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {"study_uid": study_uid, "radiologist_id": rad_id},
            }
        )
    except Exception:
        pass
    return {"ok": True}


async def handle_shadow_flag(*, study_uid: str, reason: str, user_id: str) -> Dict[str, bool]:
    from src.db.repositories import insert_audit_log_event
    from src.shadow.db import flag_shadow_case, get_shadow_case

    await require_shadow_mongo()
    case = await get_shadow_case(study_uid)
    if not case or not case.get("shadow_mode"):
        raise HTTPException(status_code=404, detail="Shadow case not found")
    await flag_shadow_case(study_uid, reason, user_id)
    aid = log_shadow_workflow_event(
        event_type="shadow_case_flagged",
        user_id=user_id,
        payload={"study_uid": study_uid},
    )
    try:
        await insert_audit_log_event(
            {
                "audit_id": aid,
                "event_type": "shadow_case_flagged",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {"study_uid": study_uid, "reason": reason[:500]},
            }
        )
    except Exception:
        pass
    return {"ok": True}


async def handle_shadow_retry(*, study_uid: str, user_id: str) -> Dict[str, bool]:
    from src.db.repositories import insert_audit_log_event
    from src.shadow.db import get_shadow_case, retry_shadow_case

    await require_shadow_mongo()
    case = await get_shadow_case(study_uid)
    if not case or not case.get("shadow_mode"):
        raise HTTPException(status_code=404, detail="Shadow case not found")
    await retry_shadow_case(study_uid)
    aid = log_shadow_workflow_event(
        event_type="shadow_case_retried",
        user_id=user_id,
        payload={"study_uid": study_uid},
    )
    try:
        await insert_audit_log_event(
            {
                "audit_id": aid,
                "event_type": "shadow_case_retried",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {"study_uid": study_uid},
            }
        )
    except Exception:
        pass
    return {"ok": True}


async def handle_shadow_ingest(body: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    from pymongo.errors import DuplicateKeyError

    from src.db.repositories import insert_audit_log_event
    from src.shadow.db import insert_shadow_case

    await require_shadow_mongo()
    study_uid = body["study_uid"]
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        "study_uid": study_uid,
        "received_at": now,
        "site_id": body.get("site_id") or "site-001",
        "site_name": body.get("site_name"),
        "modality": body.get("modality") or "MR",
        "sequence": body.get("sequence") or "FLAIR",
        "slice_count": int(body.get("slice_count") or 0),
        "patient": body.get("patient") or {},
        "ingest_source": body.get("ingest_source") or "api",
        "status": "complete" if body.get("model_run") else "queued",
        "model_run": body.get("model_run"),
        "assignment": {},
        "feedback": {
            "status": "pending",
            "submitted_by": None,
            "submitted_at": None,
            "verdict": None,
            "ground_truth": None,
            "notes": None,
            "time_to_review_s": None,
        },
        "flags": list(body.get("flags") or []),
        "shadow_mode": True,
        "exported": False,
    }
    try:
        await insert_shadow_case(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="study_uid already ingested") from None
    aid = log_shadow_workflow_event(
        event_type="shadow_case_received",
        user_id=user_id,
        payload={"study_uid": study_uid, "ingest_source": doc["ingest_source"]},
    )
    try:
        await insert_audit_log_event(
            {
                "audit_id": aid,
                "event_type": "shadow_case_received",
                "user_id": user_id,
                "timestamp": now,
                "payload": {"study_uid": study_uid},
            }
        )
    except Exception:
        pass
    return {"ok": True, "study_uid": study_uid, "audit_id": aid}


async def handle_shadow_export(
    *,
    start: str,
    end: str,
    fmt: str,
    user_id: str,
) -> StreamingResponse:
    from src.db.repositories import insert_audit_log_event
    from src.shadow.db import export_shadow_cases

    await require_shadow_mongo()
    a, b = parse_export_range(start, end)
    rows = await export_shadow_cases(start=a, end=b)
    aid = log_shadow_workflow_event(
        event_type="shadow_export_requested",
        user_id=user_id,
        payload={"start": start, "end": end, "format": fmt, "row_count": len(rows)},
    )
    try:
        await insert_audit_log_event(
            {
                "audit_id": aid,
                "event_type": "shadow_export_requested",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {"start": start, "end": end, "format": fmt},
            }
        )
    except Exception:
        pass

    if (fmt or "csv").lower() == "json":
        return JSONResponse(content={"audit_id": aid, "rows": rows})

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "audit_export_id",
            "study_uid",
            "site_id",
            "status",
            "received_at",
            "model_name",
            "label",
            "confidence",
            "feedback_status",
            "verdict",
        ]
    )
    for r in rows:
        mr = r.get("model_run") or {}
        fb = r.get("feedback") or {}
        w.writerow(
            [
                aid,
                r.get("study_uid"),
                r.get("site_id"),
                r.get("status"),
                r.get("received_at"),
                mr.get("model_name"),
                mr.get("label"),
                mr.get("confidence"),
                fb.get("status"),
                fb.get("verdict"),
            ]
        )

    data = buf.getvalue()

    async def _csv() -> Any:
        yield data

    headers = {"Content-Disposition": f'attachment; filename="shadow_export_{aid}.csv"'}
    return StreamingResponse(_csv(), media_type="text/csv", headers=headers)


async def shadow_stream_body():
    """SSE: periodic KPI snapshot for queue freshness."""
    from src.shadow.db import compute_shadow_kpis

    while True:
        try:
            await require_shadow_mongo()
            kpis = await compute_shadow_kpis()
            yield f"data: {json.dumps({'kpis': kpis}, default=str)}\n\n"
        except HTTPException as exc:
            yield f"data: {json.dumps({'error': exc.detail}, default=str)}\n\n"
        await asyncio.sleep(4)


async def handle_shadow_get_case(study_uid: str) -> Dict[str, Any]:
    from src.shadow.db import get_shadow_case, serialize_case

    await require_shadow_mongo()
    doc = await get_shadow_case(study_uid)
    if not doc or not doc.get("shadow_mode"):
        raise HTTPException(status_code=404, detail="Shadow case not found")
    return serialize_case(doc)


async def handle_shadow_analytics() -> Dict[str, Any]:
    from src.shadow.db import shadow_analytics

    await require_shadow_mongo()
    return await shadow_analytics()
