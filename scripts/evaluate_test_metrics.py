#!/usr/bin/env python3
"""
Evaluate saved models on the **held-out test split** (stratified 75/15/10, same seed as data.yaml).
Prints confusion matrix, per-class precision/recall/F1, accuracy, and loss.

Use this to fill docs/validation-report-template.md and to sanity-check high val acc vs loss (e.g. transfer model).

Usage:
  python scripts/evaluate_test_metrics.py
  python scripts/evaluate_test_metrics.py --models custom_cnn xception transfer
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from sklearn.metrics import classification_report, confusion_matrix, log_loss
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.inference.predict import MODEL_INPUT_SIZES, load_model, get_model_path


def _collect_paths_and_labels(raw_dir: Path, classes: list[str]):
    paths, labels = [], []
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    for li, c in enumerate(classes):
        d = raw_dir / c
        if not d.is_dir():
            continue
        found = []
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in exts:
                found.append(p)
        if not found:
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.suffix.lower() in exts:
                    found.append(p)
        for p in found:
            paths.append(str(p))
            labels.append(li)
    return paths, np.array(labels, dtype=np.int32)


def _load_batch(paths_batch: list[str], target_size: tuple[int, int]):
    """Load images as (N, H, W, 3) float32 in [0, 1]."""
    from PIL import Image

    imgs = []
    for p in paths_batch:
        img = Image.open(p).convert("RGB").resize(target_size)
        imgs.append(np.asarray(img, dtype=np.float32) / 255.0)
    return np.stack(imgs, axis=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=str(ROOT / "configs" / "data.yaml"))
    parser.add_argument(
        "--models",
        nargs="*",
        default=["custom_cnn", "xception", "transfer"],
        help="Model names to evaluate",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--out-json", type=str, default="", help="Optional path to write metrics JSON")
    args = parser.parse_args()

    with open(args.config) as f:
        data_config = yaml.safe_load(f)

    raw = data_config.get("dataset", {}).get("raw_dir", "data/raw")
    raw_dir = Path(raw) if Path(raw).is_absolute() else ROOT / raw
    classes = data_config.get("classes", ["glioma", "meningioma", "pituitary", "notumor"])
    splits = data_config.get("splits", {})
    seed = splits.get("seed", 42)
    train_ratio = splits.get("train_ratio", 0.75)
    val_ratio = splits.get("val_ratio", 0.15)
    test_ratio = splits.get("test_ratio", 0.10)

    paths, labels = _collect_paths_and_labels(raw_dir, classes)
    if len(paths) == 0:
        print(f"No images found under {raw_dir}. Download data first (see data/README.md).")
        return 1

    # Stratified: train | temp then val | test
    train_paths, rest_paths, train_y, rest_y = train_test_split(
        paths, labels, train_size=train_ratio, stratify=labels, random_state=seed
    )
    val_share = val_ratio / (val_ratio + test_ratio) if (val_ratio + test_ratio) > 0 else 0.5
    val_paths, test_paths, val_y, test_y = train_test_split(
        rest_paths, rest_y, train_size=val_share, stratify=rest_y, random_state=seed
    )

    print("=" * 60)
    print("DATA SPLIT (same stratified logic as training pipeline)")
    print("=" * 60)
    print(f"  Total images: {len(paths)}")
    print(f"  Train: {len(train_paths)}  Val: {len(val_paths)}  Test: {len(test_paths)}")
    print(f"  Classes: {classes}")
    print()

    report = {"dataset": str(raw_dir), "n_test": len(test_y), "classes": classes, "models": {}}

    for model_name in args.models:
        path = get_model_path(model_name, ROOT)
        if path is None:
            print(f"[{model_name}] No saved model — skip.\n")
            continue

        size = MODEL_INPUT_SIZES.get(model_name, (224, 224))
        model = load_model(model_name, ROOT)
        if model is None:
            continue

        y_true = test_y.copy()
        y_pred_list = []
        prob_chunks = []

        bs = args.batch_size
        for i in range(0, len(test_paths), bs):
            batch_paths = test_paths[i : i + bs]
            x = _load_batch(batch_paths, size)
            probs = model.predict(x, verbose=0)
            prob_chunks.append(probs)
            y_pred_list.append(np.argmax(probs, axis=-1))

        y_pred = np.concatenate(y_pred_list, axis=0)
        y_prob = np.vstack(prob_chunks)
        acc = float(np.mean(y_true == y_pred))

        # Multiclass log loss (sklearn) — comparable across models; single forward pass only
        sk_loss = log_loss(y_true, y_prob, labels=list(range(len(classes))))

        print("=" * 60)
        print(f"MODEL: {model_name}  |  test images: {len(test_y)}")
        print("=" * 60)
        print(f"  Accuracy: {acc*100:.2f}%")
        print(f"  Log loss (sklearn, from predicted probs): {sk_loss:.4f}")
        print()
        print("Confusion matrix (rows=true, cols=pred):")
        cm = confusion_matrix(y_true, y_pred, labels=list(range(len(classes))))
        print(cm)
        print()
        print(classification_report(y_true, y_pred, target_names=classes, digits=4))
        print()

        report["models"][model_name] = {
            "accuracy": acc,
            "log_loss": float(sk_loss),
            "confusion_matrix": cm.tolist(),
        }

    if args.out_json:
        out_path = Path(args.out_json)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote metrics to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
