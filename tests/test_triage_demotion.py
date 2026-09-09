"""2D 4-class CNN is research triage — not a signed finding or exportable engine."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from src.api.attestation import attestation_text_for, require_exportable  # noqa: E402
from src.api.main import app  # noqa: E402
from src.ingest.path import (  # noqa: E402
    TRIAGE_BANNER,
    export_allowed_for,
    is_triage_only,
    triage_suggested_line,
)
from src.llm.report_builder import ReportBuilder  # noqa: E402

HEADERS = {"X-API-Key": "test-key"}
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"

ALLOWED_LINE_RE = re.compile(
    r"Slice-wise research classifier suggested class \S+; not used for measurement or signature\."
)
FORBIDDEN_DIAGNOSIS = (
    "classifier favors",
    "leading class",
    "glial neoplasm",
    "no discrete mass identified",
    "tumor detected",
    "no tumor detected",
    "pituitary adenoma",
    "prediction:",
)

_UI_FILES = (
    "components/scan/FindingsCard.tsx",
    "pages/ReadingMode.tsx",
    "pages/CaseDetail.tsx",
    "pages/Dashboard.tsx",
    "pages/GenerateReport.tsx",
    "pages/UploadPredict.tsx",
    "pages/ClinicalFeedback.tsx",
)


def _triage_run(**extra):
    run = {
        "audit_id": "triageaud12345678",
        "model_name": "custom_cnn",
        "model_version": "v1",
        "confidence": 0.92,
        "label": "glioma",
        "probabilities": {
            "glioma": 0.92,
            "meningioma": 0.04,
            "pituitary": 0.03,
            "notumor": 0.01,
        },
        "ingest_path": "clinical",
    }
    run.update(extra)
    return run


def _signed_prose(draft: dict) -> str:
    parts: list[str] = []
    for section in draft.get("sections") or []:
        if section.get("name") not in {"findings", "impression"}:
            continue
        for row in section.get("findings") or []:
            parts.append(str(row.get("text") or ""))
        for item in section.get("impressions") or []:
            parts.append(str(item.get("text") or ""))
    return "\n".join(parts)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_builder_emits_research_triage_not_signed_findings():
    builder = ReportBuilder("brain_mri_tumor")
    draft = builder.build_draft({"study_uid": "1.2.3.triage"}, _triage_run())
    triage = (draft.get("research") or {}).get("triage") or {}
    assert triage.get("class") == "glioma"
    assert abs(float(triage.get("confidence")) - 0.92) < 1e-6

    mids = {m["id"] for m in draft.get("measurements") or []}
    assert "predicted_label" not in mids
    assert "dominant_class_probability" not in mids
    assert "model_confidence" not in mids

    prose = _signed_prose(draft).lower()
    for phrase in FORBIDDEN_DIAGNOSIS:
        assert phrase not in prose, phrase
    assert "not used for measurement or signature" in prose
    assert ALLOWED_LINE_RE.search(_signed_prose(draft))
    for line in _signed_prose(draft).splitlines():
        if "glioma" in line.lower():
            assert ALLOWED_LINE_RE.search(line.strip())

    assert draft["export_allowed"] is False
    assert is_triage_only(draft)
    assert export_allowed_for(draft) is False


def test_triage_class_is_not_a_signed_finding():
    """Triage class lives on research.triage only — not a signed finding row."""
    builder = ReportBuilder("brain_mri_tumor")
    draft = builder.build_draft({"study_uid": "1.2.3.triage.signed"}, _triage_run())
    expected = triage_suggested_line("glioma")
    findings = next(s for s in draft["sections"] if s["name"] == "findings")
    mass = next(r for r in findings["findings"] if "parenchyma" in r["region"].lower() or r["text"] == expected)
    assert mass["text"] == expected
    assert mass.get("measurements") == []
    impression = next(s for s in draft["sections"] if s["name"] == "impression")
    assert impression["impressions"][0]["text"] == expected
    assert impression["impressions"][0].get("measurements") == []


def test_2d_only_clinical_path_cannot_sign_or_export(client):
    r = client.post(
        "/report/draft",
        json={
            "case_id": "1.2.3.triage.export",
            "template_id": "brain_mri_tumor",
            "model_run": _triage_run(),
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["ingest_path"] == "clinical"
    assert draft["export_allowed"] is False
    rid = draft["report_id"]
    at = client.post(
        f"/report/{rid}/attest",
        json={
            "attested_by": "Dr. Test",
            "attestation_text": attestation_text_for(draft["model_run_id"]),
        },
        headers=HEADERS,
    )
    assert at.status_code == 200, at.text
    signed = client.post(
        f"/report/{rid}/sign",
        json={
            "signer_name": "Dr. Test",
            "signer_role": "neuroradiologist",
            "acknowledged_disclaimer": True,
        },
        headers=HEADERS,
    )
    assert signed.status_code == 403
    pdf = client.get(f"/report/{rid}/pdf", headers=HEADERS)
    assert pdf.status_code == 403
    fhir = client.get(f"/report/{rid}/fhir", headers=HEADERS)
    assert fhir.status_code == 403


def test_require_exportable_blocks_signed_2d_only():
    report = {
        "status": "signed",
        "ingest_path": "clinical",
        "model_name": "custom_cnn",
        "measurements": [],
        "attested_by": "Dr. Test",
        "attested_at": "t",
    }
    with pytest.raises(HTTPException) as ei:
        require_exportable(report)
    assert ei.value.status_code == 403


def test_ui_copy_banner_not_diagnosis():
    assert TRIAGE_BANNER == "Research / protocol-check triage — not a signed finding"
    copy = (FRONTEND / "lib/triageCopy.ts").read_text(encoding="utf-8")
    assert TRIAGE_BANNER in copy
    forbidden_ui = (
        "Tumor detected — research result only",
        "No tumor detected",
        "Glioma imaging guideline",
        "AI prediction",
        "AI summary",
        "AI: glioma",
        "glial neoplasm",
    )
    for rel in _UI_FILES:
        text = (FRONTEND / rel).read_text(encoding="utf-8")
        assert "TRIAGE_BANNER" in text or TRIAGE_BANNER in text, rel
        for phrase in forbidden_ui:
            assert phrase not in text, f"{rel}: {phrase}"
