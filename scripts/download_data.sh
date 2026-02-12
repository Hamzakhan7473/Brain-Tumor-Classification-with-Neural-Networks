#!/usr/bin/env bash
# Download Brain Tumor MRI dataset from Kaggle.
# Set KAGDLE_USERNAME and KAGDLE_KEY in .env or environment.
# Dataset: e.g. sartajbhuvaji/brain-tumor-classification-mri

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_RAW="$PROJECT_ROOT/data/raw"

mkdir -p "$DATA_RAW"
cd "$PROJECT_ROOT"

if command -v kaggle &> /dev/null; then
  # Replace with your chosen dataset (e.g. sartajbhuvaji/brain-tumor-classification-mri)
  kaggle datasets download -d sartajbhuvaji/brain-tumor-classification-mri -p "$DATA_RAW" --unzip
  echo "Downloaded and extracted to $DATA_RAW"
else
  echo "Kaggle CLI not found. Install with: pip install kaggle"
  echo "Then configure ~/.kaggle/kaggle.json and run again."
  exit 1
fi
