"""
Load saved models and run prediction on single or batch images.
"""
from pathlib import Path

import numpy as np
from tensorflow import keras


MODEL_PATHS = {
    "custom_cnn": "models/saved/custom_cnn_best.keras",
    "xception": "models/saved/xception_best.keras",
    "transfer": "models/saved/transfer_best.keras",
}


def load_model_and_predict(model_name: str, image_batch: np.ndarray, class_names: list = None):
    """
    Load model by name and return predicted class and probabilities.
    image_batch: (N, H, W, C) normalized.
    """
    path = MODEL_PATHS.get(model_name)
    if not path or not Path(path).exists():
        return None, None
    model = keras.models.load_model(path)
    probs = model.predict(image_batch, verbose=0)
    preds = np.argmax(probs, axis=-1)
    if class_names:
        pred_labels = [class_names[i] for i in preds]
    else:
        pred_labels = preds.tolist()
    return pred_labels, probs
