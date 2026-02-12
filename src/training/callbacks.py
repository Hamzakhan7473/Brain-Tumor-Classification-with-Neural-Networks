"""
Custom callbacks (optional: logging, metrics export).
"""
from tensorflow import keras


class MetricsLogger(keras.callbacks.Callback):
    """Log metrics to a list or file after each epoch."""

    def __init__(self, log_path=None):
        super().__init__()
        self.log_path = log_path
        self.history_extra = []

    def on_epoch_end(self, epoch, logs=None):
        if logs:
            self.history_extra.append({**logs, "epoch": epoch})
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(str(logs) + "\n")
