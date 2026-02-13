"""
Training loop with callbacks (checkpoint, early stopping, LR reduction).
"""
import argparse
from pathlib import Path

import yaml
from tensorflow import keras


def run_training(model, train_ds, val_ds, config: dict):
    """Run training with config-driven callbacks."""
    train_cfg = config.get("training", {})
    paths = config.get("paths", {})

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=train_cfg.get("learning_rate", 1e-3)),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    callbacks = [
        keras.callbacks.ModelCheckpoint(
            paths.get("save_best", "best.keras"),
            monitor=train_cfg.get("early_stopping_monitor", "val_accuracy"),
            save_best_only=True,
            verbose=1,
        ),
        keras.callbacks.EarlyStopping(
            monitor=train_cfg.get("early_stopping_monitor", "val_accuracy"),
            patience=train_cfg.get("early_stopping_patience", 10),
            restore_best_weights=True,
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=train_cfg.get("lr_factor", 0.5),
            patience=train_cfg.get("lr_patience", 5),
            min_lr=1e-6,
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
        epochs=train_cfg.get("epochs", 50),
        callbacks=callbacks,
    )
    if paths.get("save_final"):
        Path(paths["save_final"]).parent.mkdir(parents=True, exist_ok=True)
        model.save(paths["save_final"])
    return history


def parse_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    args = parser.parse_args()
    parse_config(args.config)
