#!/usr/bin/env python3
"""
Evaluate saved models on the validation set. Reports accuracy and loss.
Target: ≥98% custom CNN, ≥99% transfer model (per project challenges).
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.inference.predict import MODEL_PATHS, MODEL_INPUT_SIZES, load_model, get_model_path


def main():
    data_path = ROOT / "configs" / "data.yaml"
    if not data_path.exists():
        print("Config not found: configs/data.yaml")
        sys.exit(1)
    with open(data_path) as f:
        data_config = yaml.safe_load(f)

    try:
        from src.data.dataset import get_dataset
    except FileNotFoundError as e:
        print(f"Data not found: {e}")
        print("Download the dataset first (see data/README.md or scripts/download_data_kagglehub.py).")
        sys.exit(1)

    results = []
    for model_name in MODEL_PATHS:
        path = get_model_path(model_name, ROOT)
        if path is None:
            print(f"[{model_name}] No saved model at {MODEL_PATHS[model_name]} — skip.")
            results.append((model_name, None, None))
            continue

        size = MODEL_INPUT_SIZES.get(model_name, (224, 224))
        data_config_eval = dict(data_config)
        data_config_eval.setdefault("image", {})["target_size"] = list(size)

        val_ds = get_dataset(data_config_eval, "validation")
        model = load_model(model_name, ROOT)
        if model is None:
            results.append((model_name, None, None))
            continue

        loss, accuracy = model.evaluate(val_ds, verbose=1)
        acc_pct = accuracy * 100
        results.append((model_name, accuracy, loss))
        status = "✓" if acc_pct >= 99 else ("~" if acc_pct >= 98 else "✗")
        print(f"[{model_name}] {status} val_accuracy = {acc_pct:.2f}%  val_loss = {loss:.4f}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY (validation set)")
    print("=" * 60)
    for name, acc, loss in results:
        if acc is not None:
            print(f"  {name:15}  accuracy = {acc*100:.2f}%   loss = {loss:.4f}")
        else:
            print(f"  {name:15}  (model not found)")
    print("=" * 60)
    accs = [r[1] for r in results if r[1] is not None]
    if accs:
        best = max(accs)
        best_name = next(r[0] for r in results if r[1] == best)
        print(f"Best: {best_name} at {best*100:.2f}%")
        if best < 0.99:
            print("\nTo reach ≥99%: train transfer model (scripts/train_transfer.py) and/or tune epochs, LR, augmentation.")
    else:
        print("No models evaluated. Train with: train_custom_cnn.py, train_xception.py, train_transfer.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
