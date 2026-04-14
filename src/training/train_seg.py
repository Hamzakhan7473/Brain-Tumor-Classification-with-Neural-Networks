"""Training loop for 3D segmentation (U-Net): combined Dice + sparse CE, monitor val_loss."""
from pathlib import Path

from tensorflow import keras


def run_training_seg(model, train_ds, val_ds, config: dict):
    train_cfg = config.get("training", {})
    paths = config.get("paths", {})
    num_classes = int(config["model"]["num_classes"])
    dice_w = float(train_cfg.get("dice_weight", 0.5))

    from src.training.losses_3d import combined_seg_loss

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=train_cfg.get("learning_rate", 1e-4)),
        loss=combined_seg_loss(num_classes, dice_weight=dice_w),
        metrics=[keras.metrics.SparseCategoricalAccuracy(name="sparse_acc")],
    )

    monitor = train_cfg.get("early_stopping_monitor", "val_loss")
    callbacks = [
        keras.callbacks.ModelCheckpoint(
            paths.get("save_best", "unet3d_best.keras"),
            monitor=monitor,
            mode="min",
            save_best_only=True,
            verbose=1,
        ),
        keras.callbacks.EarlyStopping(
            monitor=monitor,
            patience=train_cfg.get("early_stopping_patience", 15),
            restore_best_weights=True,
            mode="min",
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor=monitor,
            factor=train_cfg.get("lr_factor", 0.5),
            patience=train_cfg.get("lr_patience", 5),
            min_lr=1e-7,
            mode="min",
        ),
    ]
    if paths.get("checkpoint_dir"):
        Path(paths["checkpoint_dir"]).mkdir(parents=True, exist_ok=True)
        callbacks.append(
            keras.callbacks.ModelCheckpoint(
                str(Path(paths["checkpoint_dir"]) / "epoch_{epoch:02d}.keras"),
                save_freq="epoch",
            )
        )

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=train_cfg.get("epochs", 100),
        callbacks=callbacks,
    )
    if paths.get("save_final"):
        Path(paths["save_final"]).parent.mkdir(parents=True, exist_ok=True)
        model.save(paths["save_final"])
    return history
