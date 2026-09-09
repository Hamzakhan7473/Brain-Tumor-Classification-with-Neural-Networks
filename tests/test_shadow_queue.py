"""Shadow queue (Phase B) API tests — Mongo paths mocked for CI without Atlas."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def _ensure_dummy_keras_weights() -> None:
    from pathlib import Path as P

    root = P(__file__).resolve().parents[1]
    saved = root / "models" / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    target = saved / "custom_cnn_best.keras"
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
    model.save(str(target))


_ensure_dummy_keras_weights()

from src.api.main import app  # noqa: E402

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def shadow_mongo_ok(monkeypatch):
    async def _ok() -> None:
        return None

    monkeypatch.setattr("src.shadow.http_handlers.require_shadow_mongo", _ok)


def test_shadow_queue_requires_auth(client):
    r = client.get("/shadow/queue")
    assert r.status_code in (401, 403)


def test_shadow_queue_returns_kpis(client, shadow_mongo_ok, monkeypatch):
    async def _list(**kwargs) -> Tuple[List[Dict[str, Any]], int]:
        assert kwargs.get("limit") == 50
        return [{"study_uid": "1.2.3", "status": "complete", "shadow_mode": True}], 1

    async def _kpis() -> Dict[str, Any]:
        return {
            "total_today": 3,
            "total_yesterday": 2,
            "delta_vs_yesterday": 1,
            "pending_feedback": 1,
            "sla_breach_count": 0,
            "agreement_rate_7d": 0.873,
            "mean_inference_ms_24h": 120.0,
            "listener_status": "live",
            "last_received": "2026-01-01T00:00:00Z",
            "mongo_enabled": True,
        }

    monkeypatch.setattr("src.shadow.db.list_shadow_queue", _list)
    monkeypatch.setattr("src.shadow.db.compute_shadow_kpis", _kpis)

    r = client.get("/shadow/queue", headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    assert "kpis" in data
    assert "agreement_rate_7d" in data["kpis"]
    assert "listener_status" in data["kpis"]


def test_shadow_filter_by_status(client, shadow_mongo_ok, monkeypatch):
    captured: Dict[str, Any] = {}

    async def _list(**kwargs) -> Tuple[List[Dict[str, Any]], int]:
        captured.update(kwargs)
        return [], 0

    monkeypatch.setattr("src.shadow.db.list_shadow_queue", _list)
    r = client.get("/shadow/queue", params=[("status", "flagged"), ("status", "failed")], headers=HEADERS)
    assert r.status_code == 200
    assert captured.get("status") == ["flagged", "failed"]


def test_shadow_feedback_creates_audit_log(client, shadow_mongo_ok, monkeypatch):
    logs: List[Dict[str, Any]] = []

    async def _submit(*a, **k):
        return True, {"study_uid": "u1", "shadow_mode": True, "model_run": {"label": "A", "confidence": 0.9}}

    def _log(**kwargs):
        logs.append(kwargs)
        return "audit123456789ab"

    async def _mongo_insert(_payload):
        return None

    stored: List[Dict[str, Any]] = []

    async def _insert(payload: Dict[str, Any]) -> None:
        stored.append(payload)

    monkeypatch.setattr("src.shadow.db.submit_shadow_feedback", _submit)
    monkeypatch.setattr("src.shadow.http_handlers.log_shadow_workflow_event", _log)
    monkeypatch.setattr("src.db.repositories.insert_audit_log_event", _mongo_insert)
    monkeypatch.setattr("src.db.repositories.insert_structured_clinical_feedback", _insert)

    r = client.post(
        "/shadow/cases/test_uid_001/feedback",
        json={"audit_id": "studyresultjoin01", "verdict": "disagree", "notes": "actually severe"},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("audit_id") == "studyresultjoin01"
    assert r.json().get("feedback_id", "").startswith("fb_")
    assert "retrain" not in str(r.json()).lower()
    assert logs and logs[0]["event_type"] == "shadow_feedback_submitted"
    assert logs[0]["payload"]["verdict"] == "undercall"
    assert logs[0]["payload"]["verdict_raw"] == "disagree"
    assert stored and stored[0]["audit_id"] == "studyresultjoin01"
    assert stored[0]["feedback_event"]["codes"] == ["undercall"]


def test_shadow_feedback_blocked_on_non_shadow_case(client, shadow_mongo_ok, monkeypatch):
    async def _submit(*a, **k):
        return False, {"study_uid": "x", "shadow_mode": False}

    monkeypatch.setattr("src.shadow.db.submit_shadow_feedback", _submit)

    r = client.post(
        "/shadow/cases/x/feedback",
        json={"audit_id": "studyresultjoin01", "verdict": "agree"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "non-shadow" in str(detail).lower()


def test_report_rejects_shadow_mode_form(client):
    """/report must not run when shadow_mode form indicates shadow QA upload."""
    r = client.post(
        "/report",
        files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
        data={"model": "custom_cnn", "shadow_mode": "true"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "shadow" in r.text.lower()


def test_shadow_assign_ok(client, shadow_mongo_ok, monkeypatch):
    async def _get(uid: str):
        return {"study_uid": uid, "shadow_mode": True}

    async def _upd(uid, rid, name):
        return 1

    monkeypatch.setattr("src.shadow.db.get_shadow_case", _get)
    monkeypatch.setattr("src.shadow.db.update_shadow_assignment", _upd)
    monkeypatch.setattr("src.shadow.http_handlers.log_shadow_workflow_event", lambda **k: "a" * 16)

    async def _noop_audit(*_a, **_k):
        return None

    monkeypatch.setattr("src.db.repositories.insert_audit_log_event", _noop_audit)

    r = client.post(
        "/shadow/cases/s1/assign",
        json={"radiologist_id": "rad_1", "radiologist_name": "Dr. Test"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_shadow_ingest_duplicate_returns_409(client, shadow_mongo_ok, monkeypatch):
    from pymongo.errors import DuplicateKeyError

    async def _ins(_doc):
        raise DuplicateKeyError("dup")

    monkeypatch.setattr("src.shadow.db.insert_shadow_case", _ins)
    monkeypatch.setattr("src.inference.audit_log.log_shadow_workflow_event", lambda **k: "b" * 16)
    monkeypatch.setattr("src.db.repositories.insert_audit_log_event", lambda *_a, **_k: None)

    r = client.post(
        "/shadow/ingest",
        json={"study_uid": "dup-uid", "site_id": "site-001"},
        headers=HEADERS,
    )
    assert r.status_code == 409


def test_shadow_export_requires_range(client, shadow_mongo_ok):
    r = client.get("/shadow/export", headers=HEADERS)
    assert r.status_code == 422
