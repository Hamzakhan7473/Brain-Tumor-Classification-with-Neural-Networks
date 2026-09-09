"""FastAPI handlers for BICR dual-read workflow."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from src.bicr.workflow import (
    ReaderRole,
    ReaderSlot,
    bicr_queue_for_role,
    enroll_bicr_case,
    get_bicr_review,
    lock_bicr_timepoint,
    submit_bicr_adjudication,
    submit_bicr_read,
)


class BicrElectronicSignature(BaseModel):
    signer_name: str = Field(..., min_length=1, max_length=200)
    signer_role: str = Field(..., min_length=1, max_length=120)
    credentials: Optional[str] = Field(None, max_length=64)
    npi_or_license: Optional[str] = Field(None, max_length=64)
    meaning_acknowledged: bool = Field(..., description="Must be true — Part 11 e-signature attestation")


class BicrEnrollBody(BaseModel):
    case_id: str = Field(..., min_length=4)
    subject_id: Optional[str] = Field(None, max_length=64)
    visit: Optional[str] = Field(None, max_length=64)
    timepoint: Optional[str] = Field(None, max_length=64)
    blind_model: bool = True


class BicrReadSubmitBody(BaseModel):
    reader_slot: Literal[1, 2]
    verdict: Literal["agree", "partial", "disagree"]
    ground_truth: Optional[dict] = None
    error_categories: list[str] = Field(default_factory=list)
    clinical_notes: Optional[str] = Field(None, max_length=500)
    time_spent_s: int = Field(..., ge=0, le=86400)
    e_signature: BicrElectronicSignature


class BicrAdjudicateBody(BaseModel):
    verdict: Literal["agree", "partial", "disagree"]
    ground_truth: Optional[dict] = None
    clinical_notes: Optional[str] = Field(None, max_length=500)
    time_spent_s: int = Field(..., ge=0, le=86400)
    e_signature: BicrElectronicSignature


class BicrLockBody(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


async def handle_bicr_enroll(body: BicrEnrollBody, user_id: str, case_review: dict) -> dict:
    doc = await enroll_bicr_case(
        case_id=body.case_id.strip(),
        user_id=user_id,
        case_review=case_review,
        subject_id=body.subject_id,
        visit=body.visit,
        timepoint=body.timepoint,
        blind_model=body.blind_model,
    )
    return {"ok": True, "bicr": doc}


async def handle_bicr_get(case_id: str, role: ReaderRole) -> dict:
    payload, err = await get_bicr_review(case_id, role)
    if err:
        raise HTTPException(status_code=404, detail=err)
    return payload  # type: ignore[return-value]


async def handle_bicr_read(case_id: str, body: BicrReadSubmitBody, user_id: str) -> dict:
    if body.verdict in ("partial", "disagree") and not body.ground_truth:
        raise HTTPException(status_code=400, detail="Ground truth required for partial/disagree")
    if not body.e_signature.meaning_acknowledged:
        raise HTTPException(status_code=400, detail="Part 11 meaning must be acknowledged")

    doc, err = await submit_bicr_read(
        case_id=case_id,
        user_id=user_id,
        reader_slot=body.reader_slot,  # type: ignore[arg-type]
        verdict=body.verdict,
        ground_truth=body.ground_truth,
        error_categories=body.error_categories,
        clinical_notes=body.clinical_notes,
        time_spent_s=body.time_spent_s,
        signature=body.e_signature.model_dump(),
    )
    if err:
        raise HTTPException(status_code=409 if "already" in err.lower() else 400, detail=err)
    return {"ok": True, "bicr": doc}


async def handle_bicr_adjudicate(case_id: str, body: BicrAdjudicateBody, user_id: str) -> dict:
    if body.verdict in ("partial", "disagree") and not body.ground_truth:
        raise HTTPException(status_code=400, detail="Ground truth required for partial/disagree")
    if not body.e_signature.meaning_acknowledged:
        raise HTTPException(status_code=400, detail="Part 11 meaning must be acknowledged")

    doc, err = await submit_bicr_adjudication(
        case_id=case_id,
        user_id=user_id,
        verdict=body.verdict,
        ground_truth=body.ground_truth,
        clinical_notes=body.clinical_notes,
        time_spent_s=body.time_spent_s,
        signature=body.e_signature.model_dump(),
    )
    if err:
        raise HTTPException(status_code=409 if "already" in err.lower() else 400, detail=err)
    return {"ok": True, "bicr": doc}


async def handle_bicr_lock(case_id: str, body: BicrLockBody, user_id: str) -> dict:
    doc, err = await lock_bicr_timepoint(case_id, user_id, body.reason)
    if err:
        raise HTTPException(status_code=404, detail=err)
    return {"ok": True, "bicr": doc}


async def handle_bicr_queue(role: ReaderRole, limit: int) -> dict:
    items = await bicr_queue_for_role(role, limit=limit)
    return {"role": role, "items": items, "count": len(items)}
