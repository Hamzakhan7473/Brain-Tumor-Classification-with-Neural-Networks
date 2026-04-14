"""Segmentation losses: Dice + sparse CE (common in BraTS / 3D U-Net notebooks)."""
import tensorflow as tf


def multiclass_dice_coefficient(y_true_sparse, y_pred, num_classes: int, smooth: float = 1e-6):
    """
    y_true_sparse: (B, D, H, W) int
    y_pred: (B, D, H, W, C) softmax
    Returns scalar mean Dice (higher is better).
    """
    y_true_sparse = tf.cast(y_true_sparse, tf.int32)
    y_true_oh = tf.one_hot(y_true_sparse, depth=num_classes, dtype=tf.float32)
    # (B,D,H,W,C)
    intersection = tf.reduce_sum(y_true_oh * y_pred, axis=[1, 2, 3])
    denom = tf.reduce_sum(y_true_oh + y_pred, axis=[1, 2, 3])
    dice_per_class = (2.0 * intersection + smooth) / (denom + smooth)
    # Mean over classes (skip empty classes in batch — still ok for training signal)
    return tf.reduce_mean(dice_per_class)


def dice_loss(num_classes: int):
    def loss(y_true, y_pred):
        dice = multiclass_dice_coefficient(y_true, y_pred, num_classes)
        return 1.0 - dice

    return loss


def combined_seg_loss(num_classes: int, dice_weight: float = 0.5):
    """Sparse CE + weighted (1 - Dice), as in many Kaggle BraTS U-Net notebooks."""

    def loss(y_true, y_pred):
        y_true = tf.cast(y_true, tf.int32)
        scce = tf.keras.losses.sparse_categorical_crossentropy(y_true, y_pred)
        scce = tf.reduce_mean(scce)
        d = dice_loss(num_classes)(y_true, y_pred)
        return scce + dice_weight * d

    return loss


def mean_dice_metric(num_classes: int):
    """Keras metric: mean multiclass Dice."""

    class MeanDice(tf.keras.metrics.Metric):
        def __init__(self, name="mean_dice", **kwargs):
            super().__init__(name=name, **kwargs)
            self.num_classes = num_classes
            self.total = self.add_weight(name="total", initializer="zeros", dtype=tf.float32)
            self.count = self.add_weight(name="count", initializer="zeros", dtype=tf.float32)

        def update_state(self, y_true, y_pred, sample_weight=None):
            d = multiclass_dice_coefficient(y_true, y_pred, self.num_classes)
            self.total.assign_add(d)
            self.count.assign_add(1.0)

        def result(self):
            return self.total / (self.count + 1e-8)

        def reset_state(self):
            self.total.assign(0.0)
            self.count.assign(0.0)

    return MeanDice()
