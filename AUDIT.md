# NeuroSight Brain MRI — Phase 1 ML / API Audit

_Audit performed before consolidating `/predict` wiring. Paths are relative to project root._

---

## 1. Where inference code lives

| Artifact | Actual path |
|----------|--------------|
| 2D classification inference | `src/inference/predict.py` |
| 3D NIfTI inference | `src/inference/predict_3d.py` (not `src/api/predict_3d.py`) |
| FastAPI app | `src/api/main.py` — `POST /predict`, `GET /models`, `POST /predict-3d`, etc. |
| Model registry at startup | `src/api/model_loader.py` — **`KerasModelRegistry`** (TensorFlow), not PyTorch |

**Important:** Training and production inference in this repository are **TensorFlow / Keras** (`.keras` / `.h5`). `requirements.txt` includes `torch` / `torchvision`, but **`/predict` does not consume `.pt`/`.pth` checkpoints**. A literal port of the user-provided PyTorch `ModelRegistry` + `torch` preprocessing would **not** load existing trained weights unless training is migrated to PyTorch.

---

## 2. Exact model file paths (from config + code)

**Declared in `src/inference/predict.py` → `MODEL_PATHS`:**

| Key | Relative path |
|-----|----------------|
| `custom_cnn` | `models/saved/custom_cnn_best.keras` |
| `xception` | `models/saved/xception_best.keras` |
| `transfer` | `models/saved/transfer_best.keras` |

**3D classifier (`src/inference/predict_3d.py`):** `cnn_3d_best` → `models/saved/cnn_3d_best.keras`, etc.

**On disk at audit time:** `models/saved/` contained only `.gitkeep` (no shipped weights). Deployments must place checkpoints under `MODEL_DIR` or default `models/saved/`. **Tests** create a minimal `custom_cnn_best.keras` if missing (`tests/conftest.py`).

**Glob for `.pt`/`.pth`/`.h5` under `models/`:** none found (weights not committed).

---

## 3. Input shape the model expects

From `MODEL_INPUT_SIZES` in `src/inference/predict.py` and YAML:

| Model | `(H, W)` | Channels | Batch layout |
|-------|----------|------------|----------------|
| `custom_cnn` | 224 × 224 | 3 RGB | `(1, H, W, 3)` float32 |
| `transfer` | 224 × 224 | 3 | same |
| `xception` | 299 × 299 | 3 | same |

`configs/custom_cnn.yaml`: `input_shape: [224, 224, 3]`.  
`configs/xception.yaml`: `input_shape: [299, 299, 3]`.

3D route (`/predict-3d`): configurable volume shape (e.g. `96,96,96` via `VOLUME_3D_SHAPE`), separate Keras loader.

---

## 4. Normalization used in training vs API

**Folder-based training / validation (`src/data/dataset.py` → `get_dataset`):**

- JPEG/PNG decoded as **RGB**, resized to target size.
- If `image.normalize` is true: **`keras.layers.Rescaling(1.0 / 255.0)`** → values in **`[0, 1]`**.

**Inference raster path (`load_image_from_bytes`):** PIL RGB + resize + **`arr / 255.0`** — matches training.

**DICOM (`src/data/dicom_loader.py` → used by `_run_predict` / `preprocessing.build_inference_batch`):** slice resize + **per-volume min–max to `[0,1]`**, then stacked to **3 channels**. This is **not** identical to the JPEG `/255` pipeline; distributions can diverge vs folder training.

**`configs/data.yaml`:** lists ImageNet **`mean` / `std`** for reference when using pretrained backbones in training scripts; **the default dataset pipeline shown above uses `/255`, not ImageNet normalization**, unless a specific train script overrides it.

---

## 5. Number of classes and names

From `configs/data.yaml` **`classes`** (folder names / label order):

```yaml
classes:
  - glioma
  - meningioma
  - pituitary
  - notumor
```

**Four classes.** The benign class is spelled **`notumor`**, not `no_tumor`. The API resolves names via `_get_class_names()` reading this file.

---

## 6. `/predict`: what was wrong vs intended behavior

### Before fixes (bugs)

1. **Model reload every request:** `load_model_and_predict` called `load_model` internally, reloading Keras weights per request → slow and wrong for production.
2. **No Grad-CAM in response:** placeholder `saliency_url`; no spatial explanation payload.
3. **`GET /models`** returned **`{"models": [...]}`** while some clients/tests expect a **top-level JSON array** of `{ "name": ... }`.
4. **Auth semantics:** mixed use of missing vs invalid key; tests expect **403** for wrong key.

### After fixes (current intended behavior)

1. **`lifespan` in `main.py`** warms **`KerasModelRegistry`** (`model_loader.py`) → one load per model name at startup; handlers pass **`model=...`** into `load_model_and_predict`.
2. **Preprocessing centralized** in `src/api/preprocessing.py` **`build_inference_batch`** — mirrors previous inline logic (`load_image_from_bytes` / `load_dicom_slice`).
3. **Keras Grad-CAM** in `src/api/gradcam.py` → optional **`saliency_map_b64`** on `PredictResponse`.
4. **`PredictResponse`** includes aliases **`prediction`**, **`class_probabilities`**, **`inference_time_s`**, backward-compatible **`label`**, **`probabilities`**, **`model`**.
5. **`GET /models`** returns **list** of `{ name, architecture, loaded, … }`.
6. **Query `model_name`** supported as alias for form field **`model`** on `/predict`.

---

## 7. Dependencies & Dockerfile

**`requirements.txt` (relevant pins):**

- `tensorflow>=2.12`, `keras>=2.12`, `protobuf` range
- `torch>=2.0`, `torchvision>=0.15` — present but **not** used by `/predict`
- `nibabel>=5` — 3D / NIfTI
- MONAI — **not** listed as a core API dependency (3D U-Net configs exist separately)

**Dockerfile:** `python:3.11-slim`, installs `requirements.txt`, copies app, **`CMD uvicorn src.api.main:app`**. Does **not** preload models in Dockerfile; **`lifespan`** loads weights when the process starts.

---

## 8. Evaluation script output (`scripts/evaluate_models.py`)

For each entry in **`MODEL_PATHS`**, resolves path, builds **validation `tf.data`** with **`target_size`** from **`MODEL_INPUT_SIZES`**, runs **`model.evaluate`**, prints **`val_accuracy`** and **`val_loss`**, prints a short summary vs ≥98%/≥99% targets.

---

## 9. Config inventory (`configs/`)

YAML files reviewed: **`data.yaml`**, **`custom_cnn.yaml`**, **`xception.yaml`**, **`transfer.yaml`**, **`app.yaml`**, **`data_3d.yaml`**, **`data_3d_seg.yaml`**, **`model_3d.yaml`**, **`model_3d_unet.yaml`**, **`model_wmh_unet.yaml`**, **`data_wmh_kaggle.yaml`**.  
**2D classification `/predict`** is driven primarily by **`data.yaml`** (classes) + **`MODEL_INPUT_SIZES` / `MODEL_PATHS`** in code. Per-model training hyperparameters live in **`custom_cnn.yaml`** / **`xception.yaml`** / **`transfer.yaml`**.

---

## 10. `list_available_models` vs saved-directory clutter

Previously, every `.keras` / `.h5` stem under `models/saved/` was exposed as a `/predict` model name. Segmentation checkpoints (for example **`unet_3d_wmh_best`**) are not valid inputs to the **2D classifier** pipeline and caused **500**s when enumerated in tests.

**Current behavior:** `list_available_models()` only returns keys from **`MODEL_PATHS`** whose files exist. To serve an extra classifier file at a new stem, add it to **`MODEL_PATHS`** in `src/inference/predict.py`.

---

## 11. Regression checklist

- Use project venv: `python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx`, then `PYTHONPATH=. .venv/bin/python -m pytest tests/test_predict.py -v`.
- Smoke: health, `/models`, `/predict`, auth, empty file, bad MIME.
- JPEG → **200**, probabilities sum ≈ **1**.
- Wrong API key → **403** when keys configured; missing key → **401**.
- **Class label** spelling matches **`configs/data.yaml`** (**`notumor`**).

_End of Phase 1 audit._
