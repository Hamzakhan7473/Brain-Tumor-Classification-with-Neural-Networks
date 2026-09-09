"""Clinician attestation gate — distinct from viewing and from e-sign."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException

from src.ingest.path import DEMO, is_triage_only, report_is_demo

# Must match frontend/src/components/ui/provenance.mjs ATTESTATION_TEXT_TEMPLATE.
ATTESTATION_TEXT_TEMPLATE = (
    "I reviewed these statements against the source measurements for audit_id {id}."
)

# Display/fallback when no audit_id is bound (free-text content attest).
DEFAULT_ATTESTATION_TEXT = ATTESTATION_TEXT_TEMPLATE.format(id="unbound")

ALLOWED_SIGN_ROLES = frozenset(
    {
        "attending",
        "fellow",
        "neuroradiologist",
        "radiologist",
    }
)


def normalize_attestation_text(text: str) -> str:
    return " ".join((text or "").split())


def attestation_text_for(audit_id: str) -> str:
    aid = str(audit_id or "").strip() or "unbound"
    return ATTESTATION_TEXT_TEMPLATE.format(id=aid)


def measurement_audit_id(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return "unbound"
    return str(report.get("model_run_id") or report.get("report_id") or "unbound").strip() or "unbound"


def attestation_text_is_valid(text: str, audit_id: str | None = None) -> bool:
    expected = attestation_text_for(audit_id or "unbound")
    return normalize_attestation_text(text) == normalize_attestation_text(expected)


def report_is_attested(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    return bool(str(report.get("attested_by") or "").strip() and report.get("attested_at"))


def compute_payload_hash(report: dict[str, Any] | None) -> str:
    doc = report if isinstance(report, dict) else {}
    blob = {
        "measurements": doc.get("measurements"),
        "model_run_id": doc.get("model_run_id"),
        "ingest_path": doc.get("ingest_path"),
    }
    canonical = json.dumps(blob, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stamp_payload_hashes(report: dict[str, Any]) -> dict[str, Any]:
    digest = compute_payload_hash(report)
    report["payload_hash"] = digest
    report["last_validated_payload_hash"] = digest
    return report


def engine_versions(report: dict[str, Any] | None) -> dict[str, Any]:
    doc = report if isinstance(report, dict) else {}
    prov = doc.get("provenance") if isinstance(doc.get("provenance"), dict) else {}
    return {
        "model": doc.get("model_name"),
        "model_version": doc.get("model_version"),
        "llm": prov.get("generated_by"),
        "validator_status": prov.get("validator_status"),
    }


def require_attested(report: dict[str, Any]) -> None:
    """Block finalize until a clinician has explicitly attested."""
    if not report_is_attested(report):
        raise HTTPException(
            status_code=400,
            detail=(
                "Clinician attestation is required before this report can be "
                "finalized or exported (PDF/FHIR). POST /report/{id}/attest first."
            ),
        )


def require_signed(report: dict[str, Any]) -> None:
    if not isinstance(report, dict) or report.get("status") != "signed":
        raise HTTPException(
            status_code=403,
            detail="Report must be signed before PDF/FHIR export.",
        )


def require_clinical_path(report: dict[str, Any]) -> None:
    if report_is_demo(report) or str(report.get("ingest_path") or "") == DEMO:
        raise HTTPException(
            status_code=403,
            detail="Demo / non-clinical path cannot be signed or exported.",
        )


def require_sign_role(role: str) -> None:
    key = " ".join((role or "").lower().split())
    if key not in ALLOWED_SIGN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="signer_role is not allowed to sign.",
        )


def require_payload_hash_unchanged(report: dict[str, Any]) -> None:
    expected = str(report.get("last_validated_payload_hash") or "").strip()
    current = compute_payload_hash(report)
    if not expected or current != expected:
        raise HTTPException(
            status_code=403,
            detail="payload_hash changed since last validation; re-attest after review.",
        )


def require_trusted_engine(report: dict[str, Any]) -> None:
    """2D triage alone is not a signed/exportable engine, even if ingest_path=clinical."""
    if is_triage_only(report):
        raise HTTPException(
            status_code=403,
            detail="2D research triage without a trusted 3D volume cannot be signed or exported.",
        )


def require_exportable(report: dict[str, Any]) -> None:
    """API lock: clinical + signed + trusted engine. UI disable is not sufficient."""
    require_clinical_path(report)
    require_signed(report)
    require_trusted_engine(report)
