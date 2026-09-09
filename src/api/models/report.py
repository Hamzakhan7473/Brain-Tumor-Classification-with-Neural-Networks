"""Structured radiology report draft — JSON sections, provenance, audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SectionSource = Literal["template", "ai", "measured", "edited", "manual"]
ReportStatus = Literal["draft", "in_review", "signed", "rejected", "amended"]

DEFAULT_DISCLAIMER = (
    "NeuroSight is a research tool. AI-generated content must be "
    "verified by a qualified radiologist. The signing physician "
    "retains full clinical responsibility for the final report."
)


class Citation(BaseModel):
    id: int
    label: str
    source_type: Literal["paper", "guideline", "measurement", "template"]
    location: str | None = None
    snippet: str | None = None
    audit_ref: str | None = None


class Measurement(BaseModel):
    id: str
    label: str
    value: float | int | str
    unit: str | None = None
    severity: str | None = None
    audit_ref: str
    source: str


class FindingRow(BaseModel):
    region: str
    text: str
    measurements: list[str] = Field(default_factory=list)
    citations: list[int] = Field(default_factory=list)


class ImpressionItem(BaseModel):
    order: int
    text: str
    measurements: list[str] = Field(default_factory=list)
    citations: list[int] = Field(default_factory=list)


class ReportSection(BaseModel):
    name: Literal[
        "indication",
        "technique",
        "comparison",
        "findings",
        "impression",
        "recommendations",
    ]
    source: SectionSource
    text: str | None = None
    findings: list[FindingRow] | None = None
    impressions: list[ImpressionItem] | None = None
    last_edited: datetime | str | None = None
    edited_by: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    ai_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Immutable snapshot of first AI draft for diff/review.",
    )


class ReportDraft(BaseModel):
    report_id: str
    case_id: str
    study_uid: str
    template_id: str
    status: ReportStatus
    sections: list[ReportSection]
    measurements: list[Measurement]
    citations: list[Citation]

    model_run_id: str
    model_name: str
    model_version: str
    model_confidence: float

    created_at: datetime | str
    created_by: str = "system"
    assigned_to: str | None = None
    last_modified: datetime | str
    auto_saved_at: datetime | str | None = None

    signed_by: str | None = None
    signed_at: datetime | str | None = None
    signed_text_hash: str | None = None
    signature_audit_id: str | None = None

    disclaimer: str = DEFAULT_DISCLAIMER

    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="AI generation provenance (model slug, prompt version, validator status).",
    )
    attested_by: str | None = None
    attested_at: datetime | str | None = None
    attestation_text: str | None = None
    attestation_audit_id: str | None = None
    ingest_path: str = "clinical"
    export_allowed: bool = True
    research: dict[str, Any] | None = None
    payload_hash: str | None = None
    last_validated_payload_hash: str | None = None
    export_events: list[dict[str, Any]] = Field(default_factory=list)

    case_snapshot: dict[str, Any] = Field(default_factory=dict)
    model_run_snapshot: dict[str, Any] = Field(default_factory=dict)
