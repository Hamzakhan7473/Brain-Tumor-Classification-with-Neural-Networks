"""
Second transfer-learning model for brain tumor classification.
Challenge 2: Target ≥99% accuracy (e.g. EfficientNetB0, ResNet50, DenseNet121).
"""
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.applications import EfficientNetB0


def build_transfer_model(
    base_name="EfficientNetB0",
    input_shape=(224, 224, 3),
    num_classes=4,
    trainable_layers=20,
    dropout=0.4,
    pooling="avg",
    name="transfer_brain",
):
    """Build a transfer model with pre-trained base and custom head."""
    if base_name == "EfficientNetB0":
        base = EfficientNetB0(include_top=False, weights="imagenet", input_shape=input_shape, pooling=pooling)
    else:
        raise ValueError(f"Unsupported base: {base_name}")

    base.trainable = True
    n = len(base.layers)
    for layer in base.layers[: max(0, n - trainable_layers)]:
        layer.trainable = False

    inputs = keras.Input(shape=input_shape, name="input")
    x = base(inputs)
    x = keras.layers.Dropout(dropout, name="dropout")(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", name="output")(x)
    return keras.Model(inputs=inputs, outputs=outputs, name=name)
