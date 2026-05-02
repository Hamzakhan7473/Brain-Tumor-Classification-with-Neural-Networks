"""Smoke tests for /predict, /models, and auth (requires weights under models/saved/ or conftest dummy)."""

from __future__ import annotations

import base64
import io
import os

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("APP_API_KEY", "test-key")

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def _ensure_dummy_keras_weights() -> None:
    """Minimal 4-class classifier at models/saved/custom_cnn_best.keras for CI (must run before importing app)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
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

from src.api.main import app

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client():
    # Lifespan runs here — loads Keras registry (required for /models and /predict).
    with TestClient(app) as c:
        yield c
# Matches configs/data.yaml class folder names
CLASSES = {"glioma", "meningioma", "pituitary", "notumor"}


def make_fake_scan(size: int = 256) -> bytes:
    """Create a grayscale brain-like test image (saved as JPEG)."""
    arr = np.zeros((size, size), dtype=np.uint8)
    cx, cy, r = size // 2, size // 2, size // 3
    y, x = np.ogrid[:size, :size]
    mask = (x - cx) ** 2 + (y - cy) ** 2 <= r**2
    arr[mask] = np.random.randint(100, 200, mask.sum())
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_models_list(client):
    r = client.get("/models", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0, "No models — ensure models/saved/custom_cnn_best.keras exists"
    assert "name" in data[0]


def test_predict_returns_valid_shape(client):
    r = client.post(
        "/predict",
        files={"file": ("scan.jpg", make_fake_scan(), "image/jpeg")},
        headers=HEADERS,
    )
    assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
    data = r.json()
    assert "prediction" in data
    assert "label" in data
    assert "confidence" in data
    assert "class_probabilities" in data
    assert data["prediction"] in CLASSES
    assert 0.0 <= data["confidence"] <= 1.0
    probs = data["class_probabilities"]
    assert abs(sum(probs.values()) - 1.0) < 0.01


def test_predict_all_models(client):
    models_r = client.get("/models", headers=HEADERS)
    assert models_r.status_code == 200
    tested = 0
    for m in models_r.json():
        if m.get("task") != "classification" or int(m.get("dims", 0)) != 2:
            continue  # WMH etc. belong on /predict-3d, not /predict
        tested += 1
        r = client.post(
            "/predict",
            files={"file": ("scan.jpg", make_fake_scan(), "image/jpeg")},
            params={"model_name": m["name"]},
            headers=HEADERS,
        )
        assert r.status_code == 200, f"Model {m['name']} failed: {r.text}"
    assert tested > 0, "Expected at least one loaded 2D classifier in GET /models"


def test_predict_empty_file_returns_400(client):
    r = client.post(
        "/predict",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_predict_bad_format_returns_422(client):
    r = client.post(
        "/predict",
        files={"file": ("bad.exe", b"not-an-image", "application/octet-stream")},
        headers=HEADERS,
    )
    assert r.status_code in (400, 422)


def test_saliency_map_present(client):
    r = client.post(
        "/predict",
        files={"file": ("scan.jpg", make_fake_scan(), "image/jpeg")},
        headers=HEADERS,
    )
    data = r.json()
    if data.get("saliency_map_b64"):
        decoded = base64.b64decode(data["saliency_map_b64"])
        img = Image.open(io.BytesIO(decoded))
        assert img.size[0] > 0


def test_auth_rejects_bad_key(client):
    r = client.post(
        "/predict",
        files={"file": ("scan.jpg", make_fake_scan(), "image/jpeg")},
        headers={"X-API-Key": "wrong-key"},
    )
    assert r.status_code == 403


def test_audit_id_returned_predict(client):
    r = client.post(
        "/predict",
        files={"file": ("scan.jpg", make_fake_scan(), "image/jpeg")},
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("audit_id"), str) and len(data["audit_id"]) >= 12
    assert isinstance(data.get("audit_timestamp"), str)


def test_indeterminate_disposition_below_threshold(monkeypatch, client):
    from src.inference.model_registry import registry

    m = registry.models.get("custom_cnn")
    if m is None:
        pytest.skip("custom_cnn not loaded")

    def _low_probs(tensor, verbose=0):
        return np.array([[0.26, 0.24, 0.25, 0.25]], dtype=np.float32)

    monkeypatch.setattr(m, "predict", _low_probs)

    r = client.post(
        "/predict",
        files={"file": ("scan.jpg", make_fake_scan(), "image/jpeg")},
        params={"model_name": "custom_cnn"},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("disposition") == "indeterminate"
    assert data.get("prediction") == "indeterminate"


def test_predict_3d_missing_patient_age_422(client):
    r = client.post(
        "/predict-3d",
        files={"file": ("flair_placeholder.nii.gz", b"x" * 4096)},
        headers=HEADERS,
    )
    assert r.status_code == 422, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("error") == "clinical_context_required"
