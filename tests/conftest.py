"""Pytest: create a minimal Keras model on disk before test modules import the FastAPI app."""

from __future__ import annotations

import os
from pathlib import Path


def _create_dummy_keras_model_if_needed() -> None:
    """Create models/saved/custom_cnn_best.keras if missing (4-class softmax, Conv2D for Grad-CAM)."""
    root = Path(__file__).resolve().parents[1]
    saved = root / "models" / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    target = saved / "custom_cnn_best.keras"
    if target.exists():
        return
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
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


def pytest_configure(config):
    """Runs before test modules are imported — ensures weights exist before `from src.api.main import app`."""
    _create_dummy_keras_model_if_needed()
