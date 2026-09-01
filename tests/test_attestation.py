"""Clinician attestation gate — independent of Prompt 1/2/4 validators."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.api.attestation import (
    DEFAULT_ATTESTATION_TEXT,
    attestation_text_is_valid,
    report_is_attested,
    require_attested,
)
from src.llm.content_provenance import build_content_provenance, generated_by_slug
from src.llm.validation import ValidationResult


def test_generated_by_slug_from_manifest_id():
    assert generated_by_slug("us.anthropic.claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_provenance_status_from_gate():
    passed = ValidationResult(passed=True)
    p = build_content_provenance(prompt_template_name="report", gate=passed)
    assert p["generated_by"]
    assert p["prompt_template_version"] == "v1.0"
    assert p["validator_status"] == "passed"
    assert p["validator_warnings"] == []

    warn = ValidationResult(passed=True, unaddressed_claims=["follow-up advice"])
    w = build_content_provenance(prompt_template_name="report", gate=warn)
    assert w["validator_status"] == "warnings"

    failed = ValidationResult(passed=False, invented_numbers=["99.5"])
    f = build_content_provenance(prompt_template_name="explanation", gate=failed)
    assert f["validator_status"] == "failed"


def test_attestation_text_must_match():
    assert attestation_text_is_valid(DEFAULT_ATTESTATION_TEXT)
    assert attestation_text_is_valid("  " + DEFAULT_ATTESTATION_TEXT + "  ")
    assert not attestation_text_is_valid("")
    assert not attestation_text_is_valid("looks good to me")


def test_require_attested_blocks_unattested():
    with pytest.raises(HTTPException) as ei:
        require_attested({"status": "draft"})
    assert ei.value.status_code == 400
    assert "attest" in str(ei.value.detail).lower()
    require_attested({"attested_by": "Dr. A", "attested_at": "2026-09-01T00:00:00Z"})
    assert report_is_attested({"attested_by": "Dr. A", "attested_at": "2026-09-01T00:00:00Z"})


def test_attestation_does_not_replace_clinical_gate():
    """Clinician attestation is an additional HITL gate, not a Prompt 1 bypass."""
    from src.llm.validation import enforce_clinical_gate, grounding_from_prediction

    payload = grounding_from_prediction("glioma", 0.91, {"glioma": 0.91})
    invented = "There is a 99.5 mm left frontal hemorrhage."
    text, gate = enforce_clinical_gate(invented, payload, fallback_text="Prediction: glioma.")
    assert gate.passed is False or gate.used_fallback is True
    attested_doc = {
        "attested_by": "Dr. A",
        "attested_at": "2026-09-01T00:00:00Z",
        "status": "draft",
    }
    require_attested(attested_doc)
    assert gate.passed is False or gate.used_fallback is True
