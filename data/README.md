# Data

## Dataset

Use a **Brain MRI tumor classification** dataset from Kaggle, for example:

- [Brain Tumor MRI Dataset](https://www.kaggle.com/datasets/masoudnickparvar/brain-tumor-mri-dataset) — used by `scripts/download_data_kagglehub.py`
- [Brain Tumor Classification (MRI)](https://www.kaggle.com/datasets/sartajbhuvaji/brain-tumor-classification-mri)
- [Brain Tumor MRI (Multi-Class)](https://www.kaggle.com/datasets/maxwellbernard/brain-tumor-mri-multi-class-dataset)

## Expected structure

After running `download_data_kagglehub.py`, data is under `raw/` with one folder per class:

```
data/
  raw/
    glioma/
      img1.jpg ...
    meningioma/
      ...
    pituitary/
      ...
    notumor/
      ...
  processed/   # optional: precomputed splits, cached arrays
```

Class names in `configs/data.yaml` must match these folder names (`glioma`, `meningioma`, `pituitary`, `notumor`).

## Download

### Option 1: kagglehub (recommended)

No API key in env needed; uses Kaggle credentials from `~/.kaggle/kaggle.json` or prompts login:

```bash
pip install kagglehub
python scripts/download_data_kagglehub.py
```

Downloads **masoudnickparvar/brain-tumor-mri-dataset** and places it under `data/raw/`.

### Option 2: Kaggle CLI

1. Install Kaggle CLI: `pip install kaggle`
2. Place `kaggle.json` (with your API credentials) in `~/.kaggle/`
3. Run: `bash scripts/download_data.sh` (or use the dataset-specific command from the dataset page)

## Verify backend and data

From project root:

```bash
python scripts/check_backend_and_data.py
```

This checks config, `data/raw` layout, class counts, and (if TensorFlow is installed) one batch from the data pipeline.

## License

Respect the license of the dataset you use. Do not commit raw image data to the repository.
