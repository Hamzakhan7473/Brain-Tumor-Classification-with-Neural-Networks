"""Clinician attestation gate — distinct from viewing and from e-sign."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

# Must match frontend/src/components/ui/provenance.mjs DEFAULT_ATTESTATION_TEXT.
DEFAULT_ATTESTATION_TEXT = (
    "I have reviewed the AI-generated content against the source measurements "
    "and confirm its accuracy"
)


def normalize_attestation_text(text: str) -> str:
    return " ".join((text or "").split())


def attestation_text_is_valid(text: str) -> bool:
    return normalize_attestation_text(text) == normalize_attestation_text(DEFAULT_ATTESTATION_TEXT)


def report_is_attested(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    return bool(str(report.get("attested_by") or "").strip() and report.get("attested_at"))


def require_attested(report: dict[str, Any]) -> None:
    """Block finalize/export until a clinician has explicitly attested."""
    if not report_is_attested(report):
        raise HTTPException(
            status_code=400,
            detail=(
                "Clinician attestation is required before this report can be "
                "finalized or exported (PDF/FHIR). POST /report/{id}/attest first."
            ),
        )
