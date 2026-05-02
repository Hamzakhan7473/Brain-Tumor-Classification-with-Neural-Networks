"""
Grad-CAM for TensorFlow/Keras image classifiers (last Conv2D layer).
Returns a base64-encoded PNG heatmap for optional overlay in the UI.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _find_last_conv(model):
    from tensorflow import keras

    for layer in reversed(model.layers):
        if isinstance(layer, keras.layers.Conv2D):
            return layer
        if isinstance(layer, keras.layers.SeparableConv2D):
            return layer
    return None


def keras_gradcam_heatmap(
    model,
    batch: np.ndarray,
    class_idx: int,
    target_size: Tuple[int, int],
) -> Optional[np.ndarray]:
    """
    Compute a 2D heatmap [H, W] in [0, 1], resized to target_size (height, width).
    """
    import tensorflow as tf

    last_conv = _find_last_conv(model)
    if last_conv is None:
        return None

    try:
        grad_model = tf.keras.Model(
            inputs=model.inputs,
            outputs=[last_conv.output, model.output],
        )
    except Exception as e:
        logger.debug("GradCAM grad_model build failed: %s", e)
        return None

    x = tf.convert_to_tensor(batch, dtype=tf.float32)
    with tf.GradientTape() as tape:
        conv_out, preds = grad_model(x)
        if class_idx < 0 or class_idx >= int(preds.shape[1]):
            class_idx = int(tf.argmax(preds[0]).numpy())
        tape.watch(conv_out)
        class_channel = preds[0, class_idx]
    grads = tape.gradient(class_channel, conv_out)
    if grads is None:
        return None

    # Grad-CAM: channel-wise mean gradient weights × conv activations, sum over channels.
    pooled = tf.reduce_mean(grads, axis=(1, 2))
    heatmap = tf.reduce_sum(conv_out * pooled[:, tf.newaxis, tf.newaxis, :], axis=-1)
    heatmap = tf.nn.relu(heatmap[0])
    mx = tf.reduce_max(heatmap)
    if mx.numpy() > 0:
        heatmap = heatmap / mx
    hm = heatmap.numpy().astype(np.float32)

    th, tw = target_size
    img = hm[np.newaxis, ..., np.newaxis]
    resized = tf.image.resize(img, (th, tw), method="bilinear")
    out = resized.numpy()[0, :, :, 0]
    return np.clip(out, 0.0, 1.0)


def heatmap_to_base64_png(hm: np.ndarray) -> str:
    """Encode heatmap as PNG with jet colormap; returns base64 ASCII."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.cm as cm
    from PIL import Image

    rgba = cm.jet(hm)
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    pil_img = Image.fromarray(rgb)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def keras_gradcam_base64(
    model,
    batch: np.ndarray,
    class_idx: int,
    target_size: Tuple[int, int],
) -> Optional[str]:
    hm = keras_gradcam_heatmap(model, batch, class_idx, target_size)
    if hm is None:
        return None
    try:
        return heatmap_to_base64_png(hm)
    except Exception as e:
        logger.debug("GradCAM PNG encode failed: %s", e)
        return None
