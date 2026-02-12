# Data

## Dataset

Use a **Brain MRI tumor classification** dataset from Kaggle, for example:

- [Brain Tumor Classification (MRI)](https://www.kaggle.com/datasets/sartajbhuvaji/brain-tumor-classification-mri)
- Or: [Brain Tumor MRI (Multi-Class)](https://www.kaggle.com/datasets/maxwellbernard/brain-tumor-mri-multi-class-dataset)

## Expected structure

Place the downloaded data under `raw/` so that images are organized by class:

```
data/
  raw/
    glioma/
      img1.jpg
      img2.jpg
    meningioma/
      ...
    no_tumor/
      ...
    pituitary/
      ...
  processed/   # optional: precomputed splits, cached arrays
```

Class names and paths can be overridden in `configs/data.yaml`.

## Download (Kaggle CLI)

1. Install Kaggle CLI: `pip install kaggle`
2. Place `kaggle.json` (with your API credentials) in `~/.kaggle/`
3. Run: `bash scripts/download_data.sh` (or use the dataset-specific command from the dataset page)

## License

Respect the license of the dataset you use. Do not commit raw image data to the repository.
