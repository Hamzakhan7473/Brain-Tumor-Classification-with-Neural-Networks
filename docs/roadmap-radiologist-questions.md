# Roadmap: Fulfilling the Radiologist Questions

This document maps each question to concrete changes you can make. Items are ordered by **feasibility and impact**: do the earlier ones first.

---

## 1. Data leakage — Split by patient ID (high impact, doable)

**Goal:** Train/val/test splits by **patient** (or study) so the same patient never appears in more than one split.

### What to do

| Step | Action |
|------|--------|
| 1 | **Get patient IDs.** Kaggle brain tumor datasets often don’t provide them. Options: (a) Use a dataset that has them (e.g. CSV with `filename, patient_id`); (b) Infer from filenames if they follow a pattern like `BraTS_001_slice_5.jpg` → patient `BraTS_001`; (c) Create `data/raw/metadata.csv` with columns `filename, patient_id` and fill from dataset docs or heuristics. |
| 2 | **Config.** In `configs/data.yaml` add a `patient_split` section (see below). |
| 3 | **Code.** In `src/data/dataset.py`: if `patient_split: true` and a metadata path is given, load the CSV, group by `patient_id`, stratify patients into train/val/test, then build file lists per split and create datasets from those lists (instead of `image_dataset_from_directory` with random `validation_split`). |
| 4 | **Fallback.** If no metadata/patient ID is available, keep current image-level split but set `patient_split: false` and document in methodology that metrics may be optimistic until patient-level split is used. |

**Deliverable:** Patient-based split when metadata exists; methodology and README updated.

---

## 2. LLM grounding — No ungrounded size/location (quick win)

**Goal:** Avoid the LLM “hallucinating” size or location; either constrain text or ground it to a mask later.

### What to do

| Step | Action |
|------|--------|
| 1 | **Prompt constraints.** In `src/llm/explanations.py` and `src/llm/report.py`, add explicit instructions: *“Do not state size, dimensions, or precise location. Only describe in relation to the model’s prediction and general image appearance.”* |
| 2 | **UI/docs.** In the report dashboard and in `docs/methodology.md`, state that LLM text is **not** grounded to measurements or segmentation; only the classifier output is. |
| 3 | **Optional later.** Add a 2D segmentation model (e.g. U-Net on a dataset with masks), produce a mask or bbox, and pass that to the LLM (e.g. “Describe only within the highlighted region”) for true grounding. |

**Deliverable:** Updated prompts + short disclaimer in UI and methodology.

---

## 3. Interpretability — Validate saliency (medium effort)

**Goal:** Either validate saliency maps against some ground truth or clearly document that they are for UI only.

### What to do

| Step | Action |
|------|--------|
| 1 | **Document.** In `docs/methodology.md` and README: saliency maps are for **interpretability in the UI** and are **not validated** against segmentations or radiologist ROIs. |
| 2 | **Optional validation.** If you have (or later add) data with segmentation masks: (a) Run saliency on the same images; (b) Binarize saliency (e.g. top 20% of pixels); (c) Compute Dice/IoU vs. ground-truth mask; (d) Add a small script `scripts/evaluate_saliency_vs_mask.py` and report metrics. |
| 3 | **Dataset.** Validation needs a dataset with both class labels and masks (e.g. BraTS-style or a subset). You can add this as a “Phase 2” dataset. |

**Deliverable:** Clear documentation; optional script + metrics when masks exist.

---

## 4. Architecture — 2D vs 3D, volumes, midline (large scope)

**Goal:** Be explicit that the current system is 2D slice-level; document what’s needed for volumes/midline and optionally add a path later.

### What to do

| Step | Action |
|------|--------|
| 1 | **Document.** In README and methodology: **current:** 2D slice classifier on JPG/PNG; **not included:** 3D volumes, DICOM, volume estimation, midline shift. |
| 2 | **Future path.** Add a short “Future work” section: to support volumes/midline you would need: DICOM or NIfTI loading (`pydicom`, `nibabel`), 3D data (full series), 3D model (e.g. 3D UNet or Swin-UNETR), segmentation labels, and post-processing (voxel volume from mask + spacing; midline shift algorithm). No code change required now—just a clear roadmap. |

**Deliverable:** Documentation only for now; 3D/volumetric as a stated future direction.

---

## 5. Surgical utility — Coordinates and vascular proximity (large scope)

**Goal:** Don’t claim surgical utility today; define what would be needed and optionally add a minimal 2D output as a first step.

### What to do

| Step | Action |
|------|--------|
| 1 | **Document.** State clearly: **current output:** class + probability only; **not provided:** spatial coordinates, vascular proximity, or surgical-planning outputs. |
| 2 | **Optional first step.** If you later add 2D segmentation: output a 2D bounding box or centroid (in pixel coordinates) and document that this is **not** in world coordinates or suitable for surgical planning without further pipeline (3D, registration, DICOM, vascular imaging). |
| 3 | **Full surgical.** True surgical utility would require 3D segmentation, registration to atlas, vascular imaging (e.g. MRA), and integration with planning tools—treat as a separate, long-term project. |

**Deliverable:** Clear boundaries in docs; optional 2D bbox later if you add segmentation.

---

## 6. Model optimization — Per-layer dropout/activation and feature-wise tuning (ongoing)

**Goal:** Systematically explore more fine-grained regularization and architectural choices (per-layer dropout rates, layer-wise activations, and feature-wise normalization/regularization) to push generalization without overfitting or making the model impossible to maintain.

### What to do

| Step | Action |
|------|--------|
| 1 | **Expose per-layer hyperparameters.** In `models/custom_cnn.py` and the associated YAML (e.g. `configs/custom_cnn.yaml`), add config fields for per-layer dropout rates and activations (e.g. ReLU, LeakyReLU, GELU) instead of a single global setting. |
| 2 | **Per-feature / channel-wise options.** Experiment with different normalization variants (BatchNorm vs LayerNorm / GroupNorm where appropriate), and optionally channel-wise dropout or stochastic depth in deeper transfer models. Surface these as config toggles rather than hard-coding. |
| 3 | **Search strategy.** Use small-scale sweeps (e.g. grid/random search or a simple Bayesian tuner) over these per-layer/per-feature settings on the **validation** set only—always with **patient-level split** enabled to avoid leakage. Record best configs and their variance across seeds. |
| 4 | **Documentation.** In `docs/challenges.md`, add a short subsection under the model performance challenges describing which per-layer/per-feature setups actually improved robustness (and which just added complexity without real gain). |

**Deliverable:** Configurable, documented support for per-layer dropout/activations and feature-wise normalization options, plus at least one “optimized” configuration with evidence that it improves validation performance under patient-level splitting.

---

## Summary: What you can build now

| Priority | Item | Effort | Implement now? |
|----------|------|--------|----------------|
| 1 | Patient-based split (config + dataset.py + metadata) | Medium | Yes (code path + config; you add CSV when available) |
| 2 | LLM prompt constraints + disclaimer | Low | Yes |
| 3 | Saliency: document “not validated”; optional script when masks exist | Low / Medium | Doc now; script when you have masks |
| 4 | Per-layer dropout/activation and feature-wise tuning (§6 above) | Medium | Config + experiments when optimizing |
| 5 | 2D vs 3D / volumes / midline: document + future work | Low | Doc only |
| 6 | Surgical: document boundaries; optional 2D bbox later | Low | Doc only |

**Full startup to-do (phased):** See **`docs/workflows-and-features.md` §9** for the single ordered to-do list (Phase 1–3 + ongoing) aligned with market, regulatory, and GTM intelligence (DICOM, API, design partners, validation report, segmentation path, compliance, regulatory strategy).
