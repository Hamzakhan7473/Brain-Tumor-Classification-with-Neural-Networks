"""Export lock: unsigned PDF/FHIR and demo (JPG-as-MRI) cannot leave the building."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from src.api.attestation import attestation_text_for, require_exportable, require_signed  # noqa: E402
from src.api.main import app  # noqa: E402
from src.ingest.path import classify_upload, resolve_ingest_path  # noqa: E402

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _wmh_run(**extra):
    run = {
        "audit_id": "abcd1234efgh5678",
        "model_name": "unet_3d_wmh",
        "model_version": "v1",
        "confidence": 0.42,
        "wmh": {"volume_cc": 10.9},
        "ingest_path": "clinical",
    }
    run.update(extra)
    return run


def _create_draft(client, case_id: str, model_run: dict) -> dict:
    r = client.post(
        "/report/draft",
        json={"case_id": case_id, "template_id": "brain_mri_wmh_svd", "model_run": model_run},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _attest(client, report: dict):
    rid = report["report_id"]
    return client.post(
        f"/report/{rid}/attest",
        json={
            "attested_by": "Dr. Test",
            "attestation_text": attestation_text_for(report["model_run_id"]),
        },
        headers=HEADERS,
    )


def _sign(client, report_id: str, role: str = "neuroradiologist"):
    return client.post(
        f"/report/{report_id}/sign",
        json={
            "signer_name": "Dr. Test",
            "signer_role": role,
            "acknowledged_disclaimer": True,
        },
        headers=HEADERS,
    )


def test_classify_jpg_is_demo():
    assert classify_upload("scan.jpg", "image/jpeg") == "demo"
    assert classify_upload("scan.PNG", "image/png") == "demo"
    assert classify_upload("study.dcm", "application/dicom") == "clinical"


def test_resolve_2d_classifier_is_demo():
    assert resolve_ingest_path({"model_name": "custom_cnn", "filename": "x.jpg"}) == "demo"
    assert resolve_ingest_path({"model_name": "unet_3d_wmh"}) == "clinical"


def test_require_signed_is_403():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        require_signed({"status": "draft", "attested_by": "A", "attested_at": "t"})
    assert ei.value.status_code == 403
    with pytest.raises(HTTPException) as ei:
        require_exportable({"status": "signed", "ingest_path": "demo"})
    assert ei.value.status_code == 403


def test_unsigned_pdf_fhir_are_403(client):
    draft = _create_draft(client, "1.2.3.export.unsigned", _wmh_run())
    rid = draft["report_id"]
    pdf = client.get(f"/report/{rid}/pdf", headers=HEADERS)
    assert pdf.status_code == 403
    fhir = client.get(f"/report/{rid}/fhir", headers=HEADERS)
    assert fhir.status_code == 403


def test_attested_but_unsigned_cannot_export(client):
    draft = _create_draft(client, "1.2.3.export.attested", _wmh_run())
    at = _attest(client, draft)
    assert at.status_code == 200, at.text
    pdf = client.get(f"/report/{draft['report_id']}/pdf", headers=HEADERS)
    assert pdf.status_code == 403
    assert "signed" in str(pdf.json().get("detail", "")).lower()
    fhir = client.get(f"/report/{draft['report_id']}/fhir", headers=HEADERS)
    assert fhir.status_code == 403


def test_demo_jpg_path_cannot_sign_or_export(client):
    draft = _create_draft(
        client,
        "1.2.3.export.demo",
        _wmh_run(ingest_path="demo", filename="slice.jpg"),
    )
    assert draft["ingest_path"] == "demo"
    at = _attest(client, draft)
    assert at.status_code == 200, at.text
    signed = _sign(client, draft["report_id"])
    assert signed.status_code == 403
    assert "demo" in str(signed.json().get("detail", "")).lower()
    pdf = client.get(f"/report/{draft['report_id']}/pdf", headers=HEADERS)
    assert pdf.status_code == 403
    fhir = client.get(f"/report/{draft['report_id']}/fhir", headers=HEADERS)
    assert fhir.status_code == 403


def test_hash_mismatch_blocks_sign(client):
    draft = _create_draft(client, "1.2.3.export.hash", _wmh_run())
    assert _attest(client, draft).status_code == 200
    from src.db.repositories import _REPORT_DRAFT_MEMORY

    doc = _REPORT_DRAFT_MEMORY[draft["report_id"]]
    ms = list(doc.get("measurements") or [])
    assert ms, "expected measurements to tamper"
    ms[0] = dict(ms[0])
    ms[0]["value"] = 99.9
    doc["measurements"] = ms
    signed = _sign(client, draft["report_id"])
    assert signed.status_code == 403
    assert "payload_hash" in str(signed.json().get("detail", "")).lower()


def test_disallowed_role_cannot_sign(client):
    draft = _create_draft(client, "1.2.3.export.role", _wmh_run())
    assert _attest(client, draft).status_code == 200
    signed = _sign(client, draft["report_id"], role="intern")
    assert signed.status_code == 403
