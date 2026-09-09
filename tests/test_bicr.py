"""BICR dual-read + adjudication workflow tests."""

from __future__ import annotations

import asyncio
import os
import uuid

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
from src.bicr.workflow import enroll_bicr_case, get_bicr_review, submit_bicr_adjudication, submit_bicr_read  # noqa: E402

HEADERS = {"X-API-Key": "test-key", "X-User-Id": "reader-a"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def case_review():
    uid = f"1.2.3.bicr-{uuid.uuid4().hex[:8]}"
    return uid, {
        "case_id": uid,
        "study_uid": uid,
        "task": "classification",
        "model_run": {
            "audit_id": "aud-test",
            "model_name": "custom_cnn",
            "label": "glioma",
            "confidence": 0.9,
            "class_probabilities": {"glioma": 0.9, "meningioma": 0.05, "notumor": 0.03, "pituitary": 0.02},
        },
    }


def _sig(name: str, role: str) -> dict:
    return {
        "signer_name": name,
        "signer_role": role,
        "credentials": "MD",
        "meaning_acknowledged": True,
    }


def test_dual_read_consensus(case_review):
    uid, review = case_review

    async def _run() -> None:
        await enroll_bicr_case(case_id=uid, user_id="admin", case_review=review, timepoint="baseline")
        payload, err = await get_bicr_review(uid, "reader1")
        assert err is None
        assert payload["case_review"]["model_run"]["label"] == "—"
        await submit_bicr_read(
            case_id=uid,
            user_id="reader-a",
            reader_slot=1,
            verdict="agree",
            ground_truth=None,
            error_categories=[],
            clinical_notes=None,
            time_spent_s=30,
            signature=_sig("Dr A", "reader_1"),
        )
        doc, err = await submit_bicr_read(
            case_id=uid,
            user_id="reader-b",
            reader_slot=2,
            verdict="agree",
            ground_truth=None,
            error_categories=[],
            clinical_notes=None,
            time_spent_s=40,
            signature=_sig("Dr B", "reader_2"),
        )
        assert err is None
        assert doc["status"] == "complete"
        assert doc["consensus"]["verdict"] == "agree"

    asyncio.run(_run())


def test_disagreement_requires_adjudication(case_review):
    uid, review = case_review

    async def _run() -> None:
        await enroll_bicr_case(case_id=uid, user_id="admin", case_review=review)
        await submit_bicr_read(
            case_id=uid,
            user_id="reader-a",
            reader_slot=1,
            verdict="disagree",
            ground_truth={"class": "meningioma"},
            error_categories=[],
            clinical_notes=None,
            time_spent_s=30,
            signature=_sig("Dr A", "reader_1"),
        )
        doc, err = await submit_bicr_read(
            case_id=uid,
            user_id="reader-b",
            reader_slot=2,
            verdict="disagree",
            ground_truth={"class": "glioma"},
            error_categories=[],
            clinical_notes=None,
            time_spent_s=40,
            signature=_sig("Dr B", "reader_2"),
        )
        assert err is None
        assert doc["status"] == "pending_adjudication"
        adj, err = await submit_bicr_adjudication(
            case_id=uid,
            user_id="adjudicator-1",
            verdict="disagree",
            ground_truth={"class": "meningioma"},
            clinical_notes="Reader 1 correct",
            time_spent_s=50,
            signature=_sig("Dr Adj", "adjudicator"),
        )
        assert err is None
        assert adj["status"] == "complete"
        assert adj["consensus"]["ground_truth"]["class"] == "meningioma"

    asyncio.run(_run())


def test_bicr_enroll_api(client, case_review, monkeypatch):
    uid, review = case_review

    async def fake_get_case(*_a, **_kw):
        return {"case_review": review}

    monkeypatch.setattr("src.api.main.get_case", fake_get_case)

    r = client.post(
        "/bicr/cases/enroll",
        json={"case_id": uid, "subject_id": "SUBJ-001", "timepoint": "week12"},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["bicr"]["case_id"] == uid

    r2 = client.get(f"/bicr/cases/{uid}?role=reader1", headers=HEADERS)
    assert r2.status_code == 200
    assert r2.json()["bicr"]["status"] == "pending_reads"
