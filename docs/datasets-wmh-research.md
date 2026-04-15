# WMH segmentation research — datasets and training workflow

This note captures a **white matter hyperintensity (WMH)** segmentation research plan: which public datasets to use, in what order, and how that relates to this repository. It complements the existing **brain tumor** classification / BraTS-style **glioma** U-Net code paths.

---

## Dataset priority (use in this order)

### 1. MICCAI 2017 WMH Segmentation Challenge (primary benchmark)

- **Role:** Gold-standard WMH benchmark; reviewers will compare to published Dice on this set.
- **Access:** Register (free) and download via **DataverseNL** — DOI: [https://doi.org/10.34894/AECRSD](https://doi.org/10.34894/AECRSD)
- **Contents (typical):** ~170 subjects; **T1 + FLAIR** with **pixel-level WMH masks**; multiple sites (e.g. Utrecht, Amsterdam, Singapore) for scanner diversity; extra observer masks for inter-rater analysis (per challenge documentation).
- **Reporting target:** Top methods on public leaderboards often sit around high 0.7s–0.8+ Dice depending on metric definition; treat **≥ 0.75** as a realistic **publication-oriented** goal to aim for after proper validation — always match the **exact** evaluation protocol (including preprocessing and train/val/test splits) from the challenge or your Methods section.

**Download (after registration):**

- Browser download from the Dataverse page linked from the DOI, or
- `pip install dataverse-client` and use the Dataverse API per their docs.

---

### 2. ADNI (age-matched normative context)

- **Role:** Build **age-matched** reference statistics (e.g. WMH burden percentiles by age group) — supports the “clinical context” story if your paper stratifies by age.
- **Access:** [https://adni.loni.usc.edu](https://adni.loni.usc.edu) — account + research agreement; approval often **1–2 days**.
- **Imaging:** T1 + FLAIR (and more) over longitudinal visits; demographics including age for stratification.
- **Download:** [IDA](https://ida.loni.usc.edu) — filter study/modality (e.g. ADNI3, MRI FLAIR), use LONI download tools. Optional programmatic access: `pyxnat` (see LONI docs).

---

### 3. BraTS 2024 (pretraining / backbone, not WMH labels)

- **Role:** **Pretrain** a 3D encoder–decoder (e.g. U-Net) on **multimodal brain MRI + tumor masks**, then **fine-tune** on MICCAI WMH with WMH masks. Improves data efficiency and small-lesion behavior when WMH training data are limited.
- **Access:** [Synapse — BraTS challenges](https://www.synapse.org) — search **“BraTS 2024”** and accept the challenge terms. Synapse **entity IDs** differ by sub-challenge and year; always use the **official challenge page** for the current `syn…` ID and folder layout (glioma / meningioma / pediatric tracks have expanded over time).
- **Contents:** Large multi-institutional cohorts with **T1, T1ce, T2, FLAIR** and expert labels (task-specific; **not** WMH).

**Synapse CLI (typical):**

```bash
pip install synapseclient
synapse login
# synapse get <Synapse_ID_from_official_challenge_page>
```

**Hugging Face:** Some groups mirror BraTS-style archives (e.g. search “BraTS 2024” on Hugging Face) — still cite the official challenge and respect licenses.

---

## Suggested local folder layout

Aligns with a WMH-focused project tree (you can mirror under this repo or a sibling directory):

```text
wmh-alert/
  data/miccai_wmh/     # MICCAI 2017 WMH after download
  data/adni/           # ADNI subsets you approve
  data/brats2024/      # BraTS for pretraining
  models/
  outputs/
```

This repo already uses `data/raw_3d_seg/` for **BraTS-style** multimodal + mask folders (see `configs/data_3d_seg.yaml`).

---

## Environment and tooling (Mac + cloud)

**Python 3.11** is a solid default (matches the project Dockerfile direction).

**Core imaging (overlap with this repo):** `nibabel` is already in `requirements.txt`. For heavier preprocessing, add as needed: `SimpleITK`, `monai`, etc.

**Framework choice:**

| Track | Tooling | Notes |
|-------|---------|--------|
| **This repo** | TensorFlow/Keras `scripts/train_3d_unet.py`, `models/unet3d.py` | BraTS-style 4-channel input + 4-class softmax; **not** WMH-ready until you add a **WMH-specific** loader (e.g. T1+FLAIR → 2 channels, **binary or multi-class WMH** masks). |
| **nnU-Net v2** | `nnunetv2` | Common for WMH and MICCAI-style benchmarks; separate dataset conversion step. |
| **PyTorch + MONAI** | `torch`, `monai` | Strong for medical 3D; Apple **MPS** available for development (`torch.backends.mps.is_available()`). |

**Experiment tracking (optional):** `wandb` (commented optional in `requirements.txt`).

**Reality check on Mac:** MPS/CPU is fine for **debugging** and small crops. Full **3D U-Net** training on full-resolution volumes is usually run on **NVIDIA GPUs** (local workstation, Colab, Lambda, or **GCP Vertex AI** / your existing Cloud Run training jobs) for acceptable iteration speed.

---

## Integration roadmap for *this* codebase

1. **BraTS pretrain:** Use `data/raw_3d_seg` + `train_3d_unet.py` as a **glioma** segmentation pretraining path (same as already documented in `scripts/train_3d_unet.py`).
2. **WMH fine-tune:** Add a dedicated dataset module (e.g. `src/data/dataset_wmh_miccai.py`) that reads MICCAI 2017 WMH layout, outputs `(volume, mask)` with **WMH label semantics** (often binary foreground vs background, or multi-label per challenge rules), and either:
   - switch `build_unet_3d` to `num_classes=2`, **or**
   - keep a compatible channel/label mapping in YAML.
3. **ADNI:** Use only in compliance with ADNI policies; typically for **normative** or secondary analysis, not for mixing labels with WMH challenge test sets without clear methodology.

---

## Citations and licenses

- Cite **MICCAI 2017 WMH**, **ADNI**, and **BraTS** per each challenge’s **required citation** and **data use agreement**.
- Do not commit **raw imaging data** to git — only paths, configs, and non-PHI metadata.

---

## Quick links

| Resource | URL |
|----------|-----|
| MICCAI 2017 WMH (DataverseNL) | [https://doi.org/10.34894/AECRSD](https://doi.org/10.34894/AECRSD) |
| ADNI | [https://adni.loni.usc.edu](https://adni.loni.usc.edu) |
| BraTS (Synapse) | [https://www.synapse.org](https://www.synapse.org) — open the **current** BraTS challenge page for IDs and terms |
