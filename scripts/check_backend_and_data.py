#!/usr/bin/env python3
"""
Check backend and Kaggle dataset: config, data dir, class counts, and one batch from get_dataset.
Run from project root: python scripts/check_backend_and_data.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    print("=== Backend & dataset check ===\n")

    # 1. Config
    print("1. Config")
    config_path = ROOT / "configs" / "data.yaml"
    if not config_path.exists():
        print("   FAIL: configs/data.yaml not found")
        return 1
    import yaml
    with open(config_path) as f:
        data_config = yaml.safe_load(f)
    raw_dir = data_config.get("dataset", {}).get("raw_dir", "data/raw")
    raw_path = ROOT / raw_dir
    classes = data_config.get("classes", [])
    print("   raw_dir:", raw_dir)
    print("   resolved:", raw_path)
    print("   classes:", classes)
    print()

    # 2. Data dir and class folders
    print("2. Data directory")
    if not raw_path.exists():
        print("   FAIL: raw dir does not exist. Run: python scripts/download_data_kagglehub.py")
        return 1
    subdirs = [d for d in raw_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
    print("   subdirs (class folders):", [d.name for d in subdirs])
    if not subdirs:
        print("   FAIL: no class subdirs found")
        return 1
    for d in subdirs:
        images = list(d.glob("*.jpg")) + list(d.glob("*.jpeg")) + list(d.glob("*.png"))
        print("   ", d.name, ":", len(images), "images")
    if classes and set(d.name for d in subdirs) != set(classes):
        print("   WARN: config 'classes' does not match folder names. Update configs/data.yaml to match:", [d.name for d in subdirs])
    print()

    # 3. One batch from get_dataset (requires TensorFlow)
    print("3. Data pipeline (get_dataset)")
    try:
        from src.data.dataset import get_dataset
        train_ds = get_dataset(data_config, "train")
        batch = next(iter(train_ds))
        x, y = batch
        print("   train batch: x shape", x.shape, "y shape", y.shape)
        val_ds = get_dataset(data_config, "validation")
        v_batch = next(iter(val_ds))
        print("   val batch:  x shape", v_batch[0].shape, "y shape", v_batch[1].shape)
        print("   OK: data pipeline works")
    except ImportError as e:
        print("   SKIP: TensorFlow not available:", e)
    except FileNotFoundError as e:
        print("   FAIL:", e)
        return 1
    except Exception as e:
        print("   FAIL:", e)
        return 1
    print()

    # 4. Model paths (no TensorFlow import)
    print("4. Saved models")
    model_dir = ROOT / "models" / "saved"
    for name in ("custom_cnn_best.keras", "xception_best.keras", "transfer_best.keras"):
        p = model_dir / name
        print("   ", name, "->", "found" if p.exists() else "not found (train first)")
    print()

    # 5. App config
    print("5. App config")
    app_path = ROOT / "configs" / "app.yaml"
    if app_path.exists():
        with open(app_path) as f:
            app_config = yaml.safe_load(f)
        models_inference = app_config.get("models_for_inference", [])
        llm_providers = app_config.get("llm", {}).get("providers", [])
        print("   models_for_inference:", models_inference)
        print("   llm providers:", [p.get("name", p.get("id")) for p in llm_providers])
    else:
        print("   configs/app.yaml not found")
    print()

    print("=== Check done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
