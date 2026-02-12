"""
Custom CNN for brain tumor MRI classification.
Challenge 1: Target ≥98% accuracy.
"""
import tensorflow as tf
from tensorflow import keras


def build_custom_cnn(
    input_shape=(224, 224, 3),
    num_classes=4,
    filters=(32, 64, 128, 256),
    dense_units=(256, 128),
    dropout=0.5,
    name="custom_cnn",
):
    """Build a convolutional classifier with conv blocks + dense head."""
    inputs = keras.Input(shape=input_shape, name="input")

    x = inputs
    for i, f in enumerate(filters):
        x = keras.layers.Conv2D(f, 3, padding="same", name=f"conv_{i}")(x)
        x = keras.layers.BatchNormalization(name=f"bn_{i}")(x)
        x = keras.layers.Activation("relu", name=f"relu_{i}")(x)
        x = keras.layers.MaxPooling2D(2, name=f"pool_{i}")(x)
        x = keras.layers.Dropout(0.2, name=f"drop_conv_{i}")(x)

    x = keras.layers.GlobalAveragePooling2D(name="gap")(x)
    for i, u in enumerate(dense_units):
        x = keras.layers.Dense(u, activation="relu", name=f"dense_{i}")(x)
        x = keras.layers.Dropout(dropout, name=f"drop_dense_{i}")(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", name="output")(x)

    return keras.Model(inputs=inputs, outputs=outputs, name=name)
