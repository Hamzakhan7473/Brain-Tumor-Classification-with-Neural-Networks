#!/usr/bin/env python3
"""
Download Brain Tumor MRI dataset using kagglehub.
Dataset: masoudnickparvar/brain-tumor-mri-dataset

Layout via kagglehub: Training/{glioma, meningioma, pituitary, notumor}
                      Testing/{...}. We merge into data/raw/<class>/ for the pipeline.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"

# Class folder names as they appear in the dataset (Training/Testing subdirs)
DATASET_CLASSES = ("glioma", "meningioma", "pituitary", "notumor")


def main():
    import kagglehub

    path = kagglehub.dataset_download("masoudnickparvar/brain-tumor-mri-dataset")
    print("Path to dataset files:", path)

    path = Path(path)
    if not path.exists():
        print("Download path does not exist.", file=sys.stderr)
        sys.exit(1)

    DATA_RAW.mkdir(parents=True, exist_ok=True)

    # Dataset may have train/test or Training/Testing (kagglehub uses capital T)
    train_dir = test_dir = None
    for (t, s) in (("train", "test"), ("Training", "Testing")):
        if (path / t).is_dir() and (path / s).is_dir():
            train_dir, test_dir = path / t, path / s
            break
    if train_dir is None:
        dirs = [d for d in path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(dirs) == 1:
            path = dirs[0]
            for (t, s) in (("train", "test"), ("Training", "Testing")):
                if (path / t).is_dir() and (path / s).is_dir():
                    train_dir, test_dir = path / t, path / s
                    break

    if train_dir is not None and test_dir is not None:
        # Remove old split links/folders (Training, Testing) so we only have class folders
        for existing in list(DATA_RAW.iterdir()):
            if existing.name not in DATASET_CLASSES:
                if existing.is_symlink():
                    existing.unlink()
                elif existing.is_dir():
                    shutil.rmtree(existing)
                else:
                    existing.unlink()
        # Merge train + test into data/raw/<Class>/
        for class_name in DATASET_CLASSES:
            dest_dir = DATA_RAW / class_name
            dest_dir.mkdir(parents=True, exist_ok=True)
            for split_dir in (train_dir, test_dir):
                src = split_dir / class_name
                if not src.is_dir():
                    continue
                for f in src.iterdir():
                    if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                        shutil.copy2(f, dest_dir / f.name)
            count = len(list(dest_dir.glob("*.*")))
            print("Merged", class_name, "->", dest_dir, "(", count, "images)")
    else:
        # Fallback: assume path has class folders (or one subdir with them)
        dirs = [d for d in path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(dirs) == 1:
            path = dirs[0]
        for item in path.iterdir():
            if item.name.startswith(".") or not item.is_dir():
                continue
            dest = DATA_RAW / item.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
            print("Copied", item.name, "->", dest)

    print("Dataset ready under", DATA_RAW)
    return 0


if __name__ == "__main__":
    sys.exit(main())
