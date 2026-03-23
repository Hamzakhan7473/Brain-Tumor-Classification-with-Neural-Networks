# Validation Report Template (patient-level)

This is a **template** for documenting validation results once you run evaluation scripts (e.g., `scripts/evaluate_models.py`) with a **patient-level split** enabled in `configs/data.yaml`.

Fill in the sections below for each model and dataset you report.

---

## 1. Overview

- **Model(s):** (e.g., Custom CNN vX, Xception vY, Transfer model vZ)
- **Dataset:** (name, source, version; e.g., Kaggle brain tumor MRI + site-specific data)
- **Task:** Brain MRI tumor classification (glioma, meningioma, pituitary, no tumor)
- **Evaluation mode:** Patient-level split (no patient appears in more than one split)
- **Date:** (YYYY-MM-DD)

---

## 2. Data and split

- **Total patients:** (N)
- **Total studies / images:** (N)
- **Sites / scanners (if applicable):** (list)
- **Split strategy:**
  - Train/val/test ratios (e.g., 75/15/10)
  - `splits.patient_split: true`
  - `splits.metadata_file: ...` (CSV with `filename`, `patient_id`)
- **Inclusion/exclusion criteria:** (brief)

---

## 3. Metrics (per model)

For each model, fill in the table. Use **patient-level** counts (each patient counted once in the confusion matrix, per the chosen reference label).

### 3.1 Confusion matrix (per class)

Example format (one per model):

| True \\ Pred | Glioma | Meningioma | Pituitary | No tumor |
|--------------|--------|------------|-----------|----------|
| **Glioma**   | TP_gg  | ...        | ...       | ...      |
| **Meningioma** | ...  | TP_mm      | ...       | ...      |
| **Pituitary** | ...   | ...        | TP_pp     | ...      |
| **No tumor** | ...    | ...        | ...       | TN_nn    |

### 3.2 Summary metrics

For each model (Custom CNN, Xception, Transfer), report:

- **Overall accuracy** (patient-level)
- **Per-class**:
  - Sensitivity (recall)
  - Specificity
  - Precision (PPV)
  - NPV
  - F1 score

Suggested table:

| Model | Class | Sensitivity | Specificity | Precision (PPV) | NPV | F1 | Support (patients) |
|-------|-------|-------------|------------|------------------|-----|----|--------------------|
| Custom CNN | Glioma |  |  |  |  |  |  |
| ...   | ...   |  |  |  |  |  |  |

---

## 4. Calibration and thresholds

- **Operating point / threshold:** (if different from argmax)
- **Calibration method:** (e.g., temperature scaling on val set, none)
- **Calibration plots:** (e.g., reliability diagram; link or description)

---

## 5. Limitations

- Domain shift (sites, scanners, protocols)
- Class imbalance
- Missing sequences or poor-quality images
- Cases excluded from analysis (and why)
- Any known failure modes (describe with examples)

---

## 6. Conclusion

- Short summary of:
  - Which model performs best and why.
  - In what settings these metrics are valid (patient population, imaging protocols).
  - How these results will be used (research only vs. baseline for future clinical product).

---

## 7. Reproducibility notes

- Exact config files used:
  - `configs/data.yaml` (with `patient_split: true` and `metadata_file`)
  - `configs/custom_cnn.yaml`, `xception.yaml`, `transfer.yaml`
- Command(s) run:
  - `python scripts/evaluate_models.py`
  - Any additional scripts used for confusion matrices / metrics.

