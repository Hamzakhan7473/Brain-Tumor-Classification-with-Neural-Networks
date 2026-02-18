"""
Saliency map implementation for CNN interpretability.
Highlights image regions that most influence the model's prediction.
Ref: Simonyan et al., Deep inside convolutional networks: Visualising image classification models and saliency maps.
TensorFlow is imported lazily to avoid protobuf errors at app startup.
"""
import numpy as np


def generate_saliency_map(model, image_batch, class_idx=None):
    """
    Compute saliency as gradient of (max class logit or class_idx) w.r.t. input.
    image_batch: (1, H, W, C), must be tf.Variable for gradient tape.
    Returns: (H, W) saliency map (absolute gradients, normalized).
    """
    import tensorflow as tf
    img = tf.Variable(image_batch, dtype=tf.float32)
    with tf.GradientTape() as tape:
        tape.watch(img)
        logits = model(img)
        if class_idx is not None:
            score = logits[0, class_idx]
        else:
            score = tf.reduce_max(logits[0])
    grads = tape.gradient(score, img)
    saliency = tf.reduce_max(tf.abs(grads), axis=-1)[0].numpy()
    saliency = (saliency - saliency.min()) / (saliency.max() - saliency.min() + 1e-8)
    return saliency
