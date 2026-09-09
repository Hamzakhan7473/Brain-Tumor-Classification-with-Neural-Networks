"""Structured clinical feedback API (v1.0) — verdicts, ground truth, audit trail."""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

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

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def classification_case(monkeypatch):
    uid = f"1.2.3.classify-{uuid.uuid4().hex[:10]}"

    async def fake_shadow(_: str) -> Optional[Dict[str, Any]]:
        return None

    async def fake_inf(study_uid: str) -> Optional[Dict[str, Any]]:
        if study_uid != uid:
            return None
        return {
            "study_instance_uid": uid,
            "site_id": "site-001",
            "model": "custom_cnn",
            "label": "glioma",
            "confidence": 0.9,
            "probabilities": {"glioma": 0.9, "meningioma": 0.05, "notumor": 0.03, "pituitary": 0.02},
            "timestamp": "2026-05-03T12:00:00Z",
            "audit_id": "abcd1234efgh5678",
        }

    monkeypatch.setattr("src.shadow.db.get_shadow_case", fake_shadow)
    monkeypatch.setattr("src.db.repositories.get_latest_inference_for_study", fake_inf)
    return uid


@pytest.fixture
def shadow_case_pending(monkeypatch):
    uid = f"1.2.3.shadow-{uuid.uuid4().hex[:10]}"
    submitted: list[Dict[str, Any]] = []

    async def fake_shadow(study_uid: str) -> Optional[Dict[str, Any]]:
        if study_uid != uid:
            return None
        return {
            "study_uid": uid,
            "shadow_mode": True,
            "site_id": "site-001",
            "patient": {"age": 62, "sex": "M"},
            "model_run": {
                "audit_id": "shadowauditid0001",
                "model_name": "xception",
                "label": "glioma",
                "confidence": 0.91,
                "class_probabilities": {"glioma": 0.91, "meningioma": 0.05, "notumor": 0.03, "pituitary": 0.01},
            },
            "feedback": {"status": "pending"},
        }

    async def fake_submit(*_a, **kw):
        submitted.append(dict(kw))
        return True, {}

    monkeypatch.setattr("src.shadow.db.get_shadow_case", fake_shadow)
    monkeypatch.setattr("src.shadow.db.submit_shadow_feedback", fake_submit)
    return uid, submitted


def test_feedback_requires_auth(client):
    r = client.post(
        "/clinical/feedback",
        json={"case_id": "x", "verdict": "agree", "time_spent_s": 1},
    )
    assert r.status_code in (401, 403)


JOIN_AUDIT = "abcd1234efgh5678"


def test_agree_verdict_no_ground_truth_required(client, classification_case):
    r = client.post(
        "/clinical/feedback",
        json={
            "case_id": classification_case,
            "audit_id": JOIN_AUDIT,
            "verdict": "agree",
            "time_spent_s": 30,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("feedback_id", "").startswith("fb_")
    assert body.get("audit_id") == JOIN_AUDIT
    blob = str(body).lower()
    assert "retrain" not in blob
    assert "used_for_retraining" not in blob


def test_legacy_disagree_maps_to_undercall(client, classification_case, monkeypatch):
    stored: list[Dict[str, Any]] = []

    async def cap(payload: Dict[str, Any]) -> None:
        stored.append(payload)

    monkeypatch.setattr("src.db.repositories.insert_structured_clinical_feedback", cap)
    r = client.post(
        "/clinical/feedback",
        json={"case_id": classification_case, "audit_id": JOIN_AUDIT, "verdict": "disagree", "time_spent_s": 60},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["audit_id"] == JOIN_AUDIT
    assert stored
    assert stored[0]["audit_id"] == JOIN_AUDIT
    assert stored[0]["verdict"] == "undercall"
    assert stored[0]["verdict_raw"] == "disagree"
    ev = stored[0]["feedback_event"]
    assert ev["audit_id"] == JOIN_AUDIT
    assert ev["codes"] == ["undercall"]
    assert ev["codes_raw"] == ["disagree"]


def test_v1_overcall_persisted_with_audit_id_join(client, classification_case, monkeypatch):
    stored: list[Dict[str, Any]] = []

    async def cap(payload: Dict[str, Any]) -> None:
        stored.append(payload)

    monkeypatch.setattr("src.db.repositories.insert_structured_clinical_feedback", cap)
    r = client.post(
        "/clinical/feedback",
        json={
            "case_id": classification_case,
            "audit_id": JOIN_AUDIT,
            "verdict": "overcall",
            "measurements_unedited": True,
            "time_spent_s": 45,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["audit_id"] == JOIN_AUDIT
    ev = stored[0]["feedback_event"]
    assert ev["schema"] == "neurosight.feedback.v1"
    assert ev["audit_id"] == JOIN_AUDIT
    assert ev["codes"] == ["overcall"]
    assert stored[0]["measurements_unedited"] is True


def test_feedback_requires_audit_id(client, classification_case):
    r = client.post(
        "/clinical/feedback",
        json={"case_id": classification_case, "verdict": "agree", "time_spent_s": 30},
        headers=HEADERS,
    )
    assert r.status_code in (400, 422)


def test_disagree_with_invalid_class_rejected(client, classification_case):
    r = client.post(
        "/clinical/feedback",
        json={
            "case_id": classification_case,
            "audit_id": JOIN_AUDIT,
            "verdict": "undercall",
            "ground_truth": {"class": "not_a_real_class"},
            "time_spent_s": 60,
        },
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_feedback_creates_audit_log(client, classification_case, monkeypatch):
    captured: list[Dict[str, Any]] = []

    async def cap(payload: Dict[str, Any]) -> None:
        captured.append(payload)

    monkeypatch.setattr("src.db.repositories.insert_audit_log_event", cap)
    r = client.post(
        "/clinical/feedback",
        json={"case_id": classification_case, "audit_id": JOIN_AUDIT, "verdict": "agree", "time_spent_s": 30},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert any(x.get("event_type") == "clinical_feedback" for x in captured)
    assert captured[0]["payload"]["verdict"] == "agree"
    assert captured[0]["payload"]["audit_id"] == JOIN_AUDIT


def test_handler_docstring_has_no_retrain_language():
    from src.api.main import StructuredClinicalFeedbackSubmit, clinical_feedback

    blob = f"{clinical_feedback.__doc__} {StructuredClinicalFeedbackSubmit.__doc__}".lower()
    assert "retrain" not in blob
    assert "irb" not in blob
    assert "fine-tune" not in blob
    assert "training data" in blob or "persist" in blob


def test_feedback_updates_shadow_case(client, shadow_case_pending, monkeypatch):
    uid, submitted = shadow_case_pending
    r = client.post(
        "/clinical/feedback",
        json={
            "case_id": uid,
            "audit_id": "shadowauditid0001",
            "verdict": "disagree",
            "ground_truth": {"class": "meningioma"},
            "error_categories": ["wrong_class"],
            "time_spent_s": 90,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert submitted and submitted[0].get("verdict") == "undercall"


def test_stats_endpoint(client, monkeypatch):
    async def fake_stats(_user: str):
        return {"reviewed_this_month": 3, "agreement_rate": 0.667, "avg_time_s": 40}

    monkeypatch.setattr("src.db.repositories.aggregate_clinical_feedback_stats", fake_stats)
    r = client.get("/clinical/feedback/stats", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "reviewed_this_month" in data
    assert "agreement_rate" in data
    assert 0 <= data["agreement_rate"] <= 1
