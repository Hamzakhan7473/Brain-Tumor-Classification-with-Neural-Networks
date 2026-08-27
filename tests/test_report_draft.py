"""Structured report draft API — provenance, edits, sign-off, FHIR, hallucination guard."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def _ensure_dummy_keras_weights() -> None:
    from pathlib import Path as P

    root = P(__file__).resolve().parents[1]
    target = root / "models" / "saved" / "custom_cnn_best.keras"
    if target.exists():
        return
    import tensorflow as tf
    from tensorflow import keras

    tf.keras.backend.clear_session()
    inp = keras.layers.Input(shape=(224, 224, 3))
    x = keras.layers.Conv2D(8, 3, padding="same", activation="relu")(inp)
    x = keras.layers.GlobalAveragePooling2D()(x)
    out = keras.layers.Dense(4, activation="softmax")(x)
    model = keras.Model(inp, out)
    model.compile(optimizer="adam", loss="categorical_crossentropy")
    target.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(target))


_ensure_dummy_keras_weights()

from src.api.main import app  # noqa: E402
from src.llm.report_builder import ReportBuilder  # noqa: E402

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def wmh_model_run():
    return {
        "audit_id": "abcd1234efgh5678",
        "model_name": "unet_3d_wmh",
        "model_version": "v1",
        "confidence": 0.42,
        "wmh": {
            "volume_cc": 10.9,
            "lesion_voxels": 1200,
            "age_matched_percentile": "75th percentile",
            "volume_cc_periventricular": 4.2,
            "volume_cc_deep_subcortical": 5.1,
            "volume_cc_infratentorial": 1.6,
        },
    }


@pytest.fixture
def fresh_draft_id(client, wmh_model_run):
    r = client.post(
        "/report/draft",
        json={"case_id": "1.2.3.4.5", "template_id": "brain_mri_wmh_svd", "model_run": wmh_model_run},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    return r.json()["report_id"]


@pytest.fixture
def signed_draft_id(client, wmh_model_run):
    r = client.post(
        "/report/draft",
        json={"case_id": "1.2.3.4.6", "template_id": "brain_mri_wmh_svd", "model_run": wmh_model_run},
        headers=HEADERS,
    )
    rid = r.json()["report_id"]
    rs = client.post(
        f"/report/{rid}/sign",
        json={
            "signer_name": "Dr. Test",
            "signer_role": "neuroradiologist",
            "acknowledged_disclaimer": True,
        },
        headers=HEADERS,
    )
    assert rs.status_code == 200, rs.text
    return rid


def test_create_draft_uses_correct_template(client, wmh_model_run):
    r = client.post(
        "/report/draft",
        json={"case_id": "1.2.3.4.7", "template_id": "brain_mri_wmh_svd", "model_run": wmh_model_run},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["template_id"] == "brain_mri_wmh_svd"


def test_draft_measurements_match_model_output(client, wmh_model_run):
    r = client.post(
        "/report/draft",
        json={"case_id": "1.2.3.4.8", "template_id": "brain_mri_wmh_svd", "model_run": wmh_model_run},
        headers=HEADERS,
    )
    measurements = r.json()["measurements"]
    wmh = next(m for m in measurements if m["id"] == "wmh_volume_cc")
    assert wmh["value"] == 10.9
    assert wmh["audit_ref"] is not None
    pv = next(m for m in measurements if m["id"] == "wmh_volume_periventricular_cc")
    assert pv["value"] == 4.2
    deep = next(m for m in measurements if m["id"] == "wmh_volume_deep_subcortical_cc")
    assert deep["value"] == 5.1
    infra = next(m for m in measurements if m["id"] == "wmh_volume_infratentorial_cc")
    assert infra["value"] == 1.6


def test_section_edit_creates_history(client, fresh_draft_id):
    r = client.patch(
        f"/report/{fresh_draft_id}/section/findings",
        json={"text": "edited"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["version"] == 1
    rep = client.get(f"/report/{fresh_draft_id}", headers=HEADERS).json()
    findings = next(s for s in rep["sections"] if s["name"] == "findings")
    assert len(findings["history"]) == 1
    assert findings["source"] == "edited"


def test_signed_report_is_immutable(client, signed_draft_id):
    r = client.patch(
        f"/report/{signed_draft_id}/section/findings",
        json={"text": "trying to edit"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "signed" in str(r.json().get("detail", "")).lower()


def test_sign_off_creates_audit_with_hash(client, fresh_draft_id):
    r = client.post(
        f"/report/{fresh_draft_id}/sign",
        json={
            "signer_name": "Dr. Test",
            "signer_role": "neuroradiologist",
            "acknowledged_disclaimer": True,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["audit_id"]
    assert data["text_hash"]
    assert len(data["text_hash"]) == 64


def test_llm_hallucination_blocked():
    builder = ReportBuilder("brain_mri_wmh_svd")
    measurements = [{"id": "wmh_volume_cc", "value": 10.9, "audit_ref": "x", "label": "WMH volume"}]
    fake_text = "WMH volume 99.5 cc detected"
    cleaned = builder._validate_no_invented_numbers(fake_text, measurements)
    assert cleaned is None


def test_fhir_export_validates(client, signed_draft_id):
    r = client.get(f"/report/{signed_draft_id}/fhir", headers=HEADERS)
    assert r.status_code == 200
    fhir = r.json()
    assert fhir["resourceType"] == "DiagnosticReport"
    assert fhir["status"] == "final"
    assert "audit-id" in str(fhir.get("extension", [])).lower()


def test_pdf_export(client, signed_draft_id):
    r = client.get(f"/report/{signed_draft_id}/pdf", headers=HEADERS)
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert r.content[:4] == b"%PDF"
