"""
Xception-based model for brain tumor MRI classification (transfer learning).
"""
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.applications import Xception as XceptionBase


def build_xception(
    input_shape=(299, 299, 3),
    num_classes=4,
    trainable_layers=30,
    dropout=0.5,
    pooling="avg",
    name="xception_brain",
):
    """Build Xception with optional unfreezing and custom head."""
    base = XceptionBase(include_top=False, weights="imagenet", input_shape=input_shape, pooling=pooling)
    if trainable_layers == 0:
        base.trainable = False
    else:
        base.trainable = True
        for layer in base.layers[:-trainable_layers]:
            layer.trainable = False

    inputs = keras.Input(shape=input_shape, name="input")
    x = base(inputs)
    x = keras.layers.Dropout(dropout, name="dropout")(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", name="output")(x)
    return keras.Model(inputs=inputs, outputs=outputs, name=name)
