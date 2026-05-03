"""Tests for NeuroSight Docs Assistant (PageIndex primary, vector RAG fallback)."""

from __future__ import annotations

import json
import os
from pathlib import Path

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


def test_docs_endpoint_requires_auth(client):
    r = client.post("/docs/ask", json={"question": "test"})
    assert r.status_code in (401, 403)


def test_docs_rejects_empty_question(client):
    r = client.post("/docs/ask", json={"question": ""}, headers=HEADERS)
    assert r.status_code == 400


def test_docs_rejects_long_question(client):
    r = client.post("/docs/ask", json={"question": "x" * 501}, headers=HEADERS)
    assert r.status_code == 400


def test_docs_manifest_endpoint(client, tmp_path, monkeypatch):
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps({"documents": [], "indexed": False, "total": 0}), encoding="utf-8")
    monkeypatch.setattr("src.api.main._docs_manifest_path", lambda: mf)
    r = client.get("/docs/manifest", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "documents" in data


def test_docs_503_when_manifest_missing(client, monkeypatch):
    monkeypatch.setattr("src.api.main._docs_manifest_path", lambda: Path("/__nonexistent__/manifest.json"))
    r = client.post("/docs/ask", json={"question": "What is shadow mode?"}, headers=HEADERS)
    assert r.status_code == 503


def test_docs_404_when_filter_matches_nothing(client, tmp_path, monkeypatch):
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps({"documents": [{"doc_id": "pi-abc", "name": "a.pdf", "sections": 1}], "total": 1, "indexed": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.api.main._docs_manifest_path", lambda: mf)

    r = client.post(
        "/docs/ask",
        json={"question": "What is shadow mode?", "doc_filter": ["pi-missing"]},
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_docs_ask_success_with_fake_indexer(client, tmp_path, monkeypatch):
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps({"documents": [{"doc_id": "pi-abc", "name": "a.pdf", "sections": 3}], "total": 1, "indexed": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.api.main._docs_manifest_path", lambda: mf)

    class _FakeIndexer:
        def query(self, question: str, doc_ids: list[str], max_nodes: int = 8):
            return {
                "answer": "Shadow mode runs silently [1].",
                "citations": [
                    {
                        "doc_id": doc_ids[0],
                        "doc_name": "a.pdf",
                        "section": "Phase B",
                        "page": 2,
                        "node_id": "n1",
                        "snippet": "Phase B (Shadow Mode): run silently alongside clinicians.",
                        "relevance": 0.9,
                    }
                ],
                "reasoning_trace": ["PageIndex chat completion (test stub)"],
                "confidence": "high",
                "latency_ms": 5,
                "tokens_used": 120,
            }

    monkeypatch.setattr("src.rag.pageindex_client.PAGEINDEX_API_KEY", "test-key")
    monkeypatch.setattr("src.rag.pageindex_client.get_indexer", lambda: _FakeIndexer())

    r = client.post("/docs/ask", json={"question": "What is shadow mode?"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "answer" in data
    assert "citations" in data
    assert len(data["citations"]) > 0
    assert all("doc_name" in c for c in data["citations"])
    assert all("section" in c for c in data["citations"])
    assert all("page" in c for c in data["citations"])
    assert "audit_id" in data
    assert data.get("confidence") == "high"


async def _noop_insert_audit(*_a, **_k):
    return None


def test_feedback_docs_received(client, monkeypatch):
    """Feedback endpoint accepts payload (JSONL + optional Mongo)."""
    monkeypatch.setattr("src.db.repositories.insert_audit_log_event", _noop_insert_audit)
    r = client.post(
        "/feedback/docs",
        json={"audit_id": "a1b2c3d4e5f6g7h8", "reason": "Test flag", "question": "Q?"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json().get("status") == "received"
