# Plan: Clinical trials–aligned workflows and MLOps (this repository)

This document **walks through the current architecture** in trial-relevant terms and defines a **phased implementation plan** for workflows you care about: reproducible training/inference, multi-site–ready evaluation, spec-driven cohorts, imaging QC and verifiers, run analytics, and controlled synthetic or stress data—**without** RL/Gymnasium-style environments.

It complements:

- `docs/project-architecture.md` — component map and data flow  
- `docs/roadmap-research-to-hospital-grade.md` — 12–24 month regulated product arc  
- `docs/clinical-workflow.md` — radiology phases (research → shadow → assistive → DICOM-integrated)  
- `docs/workflows-and-features.md` — feature checklist  
- `docs/datasets-wmh-research.md` — WMH dataset strategy  

---

## 1. Architecture walkthrough (clinical lens)

Think in **layers**. Lower layers are closer to raw imaging; upper layers are closer to people and trials operations.

### 1.1 Config and secrets

| Piece | Location | Trial-relevant role |
|-------|----------|---------------------|
| Data paths, splits, augmentation | `configs/data.yaml`, `configs/data_3d*.yaml`, `configs/data_wmh_kaggle.yaml` | **Protocol binding**: what cohort, what split rule (e.g. patient-level), what preprocessing is “locked” for an analysis. |
| Model hyperparameters | `configs/custom_cnn.yaml`, `xception.yaml`, `transfer.yaml`, `configs/model_3d*.yaml`, `configs/model_wmh_unet.yaml` | **Reproducible** training definition; should pair with a **run manifest** (see Phase 2). |
| App / LLM | `configs/app.yaml`, `.env` | Demo and assistive text; for trials, scope what is **non-endpoint** vs validated outputs. |

### 1.2 Data plane

| Piece | Location | Trial-relevant role |
|-------|----------|---------------------|
| 2D classification datasets | `src/data/dataset.py`, `augmentation.py` | Stratified splits; **patient-level** split when `metadata.csv` exists — avoids optimistic bias. |
| DICOM ingestion | `src/data/dicom_loader.py` | Bridge to **real** PACS exports; metadata for QC (later: series consistency checks). |
| 3D BraTS-style segmentation | `src/data/dataset_3d_seg.py`, `scripts/train_3d_unet.py` | Multi-sequence 3D — closer to **clinical imaging** than JPG folders. |
| WMH Kaggle path | `src/data/dataset_wmh_kaggle.py`, `scripts/train_wmh_unet.py` | Second **adapter** pattern; MICCAI WMH becomes another adapter per `docs/datasets-wmh-research.md`. |

### 1.3 Training and evaluation

| Piece | Location | Trial-relevant role |
|-------|----------|---------------------|
| 2D training | `src/training/train.py`, `callbacks.py`, `scripts/train_*.py` | Standard supervised loop; needs **manifest + git SHA** for traceability. |
| 3D segmentation | `src/training/train_seg.py`, `losses_3d.py`, `models/unet3d.py` | Dice + CE — aligns with **segmentation endpoints** and publication metrics. |
| Classifier evaluation | `scripts/evaluate_models.py` | Confusion matrix / per-class metrics — **secondary analysis** style reporting. |

### 1.4 Inference, API, and UI

| Piece | Location | Trial-relevant role |
|-------|----------|---------------------|
| Inference | `src/inference/predict.py`, `predict_3d.py`, `saliency.py` | **Frozen model** + fixed preprocessing for any “locked” analysis. |
| API | `src/api/main.py` | Service boundary for **site integration**; needs study/case identifiers and auth in trial settings. |
| Streamlit | `src/app/*` | Research UI; **human-in-the-loop** before export. |

### 1.5 Governance and intelligence

| Piece | Location | Trial-relevant role |
|-------|----------|---------------------|
| Audit | `src/app/audit.py` | JSONL events — extend to **training** and **batch inference** for ALCOA-style trails. |
| LLM | `src/llm/*` | Constrained drafts; roadmap positions LLM as **non-primary** or tightly bounded vs measured outputs. |

### 1.6 End-to-end story today

**Ingest** (JPG/DICOM or NIfTI for 3D) → **config-bound loader** → **train** → **saved weights** → **API / app** → **predict (+ optional saliency / LLM)** → **audit**.

**Gaps vs trial-grade workflows** (this plan closes them incrementally):

- No single **run manifest** (config hashes, data version, git commit, environment summary) next to each training artifact.  
- **QC gates** (DICOM/NIfTI header checks, shape/channel rules) are not centralized as **verifiers**.  
- **Analytics** for training (duration, throughput, failure reasons) are not aggregated.  
- **Multi-site / multi-adapter** evaluation is documented but not one **unified eval harness** with stratified reporting.  
- **Synthetic or stress** data is implicit (augmentation only), not a **named pipeline** for regression tests or rare morphology.  

---

## 2. Guiding principles (trials and SaMD-minded)

1. **Patient (or subject) as the unit of split** whenever longitudinal or multiple images exist — already supported for 2D when metadata is provided; enforce the same rule for 3D/WMH cohort definitions in config.  
2. **Frozen definitions**: a “run” is reproducible from manifest + configs + data snapshot ID (hash or DVC/Kaggle version string), not from memory.  
3. **Verifiers before metrics**: fail fast on corrupt volumes, wrong channels, or protocol deviation flags; then compute Dice/AUC/etc.  
4. **Separation of concerns**: validated **measurements** (volumes, Dice) vs **draft narrative** (LLM) — aligns with `docs/roadmap-research-to-hospital-grade.md`.  
5. **No PHI in git** — manifests reference paths and approved dataset versions only.  

---

## 3. Implementation phases (concrete)

Work **in order** where dependencies exist; parallelize within a phase where independent.

### Phase 0 — Inventory and definitions (short)

**Goal:** One page internal “data dictionary” for each active track (2D Kaggle, 3D BraTS, WMH Kaggle, future MICCAI).

**Deliverables:**

- [ ] Extend `docs/workflows-and-features.md` (or a small table in this doc) with columns: **adapter module**, **config file**, **split rule**, **primary metric**, **QC checks**.  
- [ ] Confirm WMH Kaggle layout and patient/site grouping if available in metadata (if not, document “image-level only” limitation).

**Exit criteria:** Any engineer can answer “which config + script + metric defines run X?” without reading source.

---

### Phase 1 — Spec-driven cohort and split contract

**Goal:** YAML-first **study/cohort profile** that training scripts consume (even if thin at first).

**Deliverables:**

- [ ] Add `configs/cohort_profiles/*.yaml` (example: `wmh_kaggle.yaml`, `brats_seg.yaml`) referencing existing `data_*` YAMLs plus explicit fields: `split_unit` (`patient` | `image` | `study`), `stratify_by`, `holdout_sites` (optional list for future multi-site).  
- [ ] Wire `scripts/train_wmh_unet.py` (and optionally `train_3d_unet.py`) to log the resolved cohort profile path into the run manifest (Phase 2).  
- [ ] If WMH metadata supports subject IDs, implement **patient-level** split in `dataset_wmh_kaggle.py`; if not, document and keep stratified image-level with clear limitation for publications.

**Exit criteria:** Changing split policy does not require editing Python except when adding a **new** dataset family.

---

### Phase 2 — Run manifest and training audit

**Goal:** Every training job writes a **JSON manifest** next to checkpoints (and optionally one JSONL line to a central `logs/training_runs.jsonl`).

**Manifest fields (minimum):**

- `run_id` (UUID), `started_at`, `ended_at`, `duration_s`  
- `git_commit` (best effort), `command_argv`  
- Paths or hashes: `data_config`, `model_config`, `cohort_profile`  
- `framework_versions` (TensorFlow, Python)  
- `artifacts`: best model path, final model path  
- `best_val_metric` (e.g. best `val_loss` or val Dice once exposed)

**Implementation sketch:**

- [ ] New module `src/clinical/run_manifest.py` (or `src/ops/run_manifest.py`) with `write_manifest(path, payload)`.  
- [ ] Call from `run_training_seg` and `run_training` (2D) on completion (and on failure where possible).  

**Exit criteria:** You can answer an auditor or statistician: “What exact inputs produced model file Y?”

---

### Phase 3 — Verifiers (imaging QC gates)

**Goal:** Deterministic checks **before** training or eval batches are trusted.

**Verifier examples:**

| Verifier | When | Action |
|----------|------|--------|
| Expected channels (e.g. 2 for T1+FLAIR) | Dataset init / first batch | Raise or skip with reason code |
| Spatial shape vs `volume.shape` in config | Per volume | Reject or crop per policy |
| Mask presence and label values | Segmentation | Reject empty mask or wrong dtype |
| DICOM: required tags present | API / DICOM loader | Return structured error for trial logs |

**Deliverables:**

- [ ] `src/clinical/verifiers.py` (or `src/data/qc_verifiers.py`) with small pure functions + a `VerifierReport` dataclass.  
- [ ] Integrate into `get_dataset_wmh_kaggle` / 3D dataset builders with `strict: true/false` in YAML.  
- [ ] API: optional strict mode returning JSON error codes (no stack traces to clients).  

**Exit criteria:** A deliberately corrupted file fails with a **coded reason** in logs/manifest, not a cryptic TF error.

---

### Phase 4 — Unified evaluation harness

**Goal:** One entry pattern for **segmentation** (and later 2D) eval: load checkpoint → run val/test → write **metrics JSON** + optional confusion / per-case CSV.

**Deliverables:**

- [ ] `scripts/evaluate_segmentation.py` (or extend `evaluate_test_metrics.py` if it already exists) accepting `--model`, `--data-config`, `--split validation|test`.  
- [ ] Metrics: mean Dice (and per-class if multi-class), Hausdorff optional later, failure case list (low Dice UIDs).  
- [ ] Output: `outputs/eval_<run_id>/metrics.json` + manifest pointer to checkpoint.  

**Exit criteria:** Publication or DSMB-style table can be generated from `metrics.json` without re-running training.

---

### Phase 5 — Platform analytics (trial ops + MLOps)

**Goal:** Aggregate **operational** signals without building a full BI stack on day one.

**Deliverables:**

- [ ] Append-only `logs/training_runs.jsonl` (one object per line) populated from Phase 2.  
- [ ] Optional: tiny `scripts/summarize_runs.py` → CSV (date, duration, best metric, data config) for spreadsheets.  
- [ ] Later: same pattern for **batch inference** (study_uid, model_version, latency_ms, outcome) if shadow-mode batch jobs appear — aligns with `docs/clinical-workflow.md` Phase B.  

**Exit criteria:** You can plot “time per epoch / per run” and “failure rate” over a month of experiments.

---

### Phase 6 — Synthetic and stress data (medical, bounded)

**Goal:** **Regression and stress** sets, not entertainment-style simulation.

**Deliverables:**

- [ ] `src/data/synthetic_slices.py` (or 3D patches): procedurally generated shapes + masks with **known** ground truth for **unit tests** of metrics and model invariance.  
- [ ] Config flag `stress_test_dir` pointing to a small fixed set of perturbed volumes (rotation/noise within ethical augmentation bounds) for **CI or nightly** eval.  
- [ ] Document in `docs/datasets-wmh-research.md` or a short note: synthetic data is for **engineering validation**, not for claiming clinical performance unless IRB/protocol say otherwise.  

**Exit criteria:** CI or a one-command script proves “metrics + verifiers still behave” after refactors.

---

### Phase 7 — API and audit alignment for multi-site readiness

**Goal:** Logs contain **study/case identifiers** and **model version** for shadow trials.

**Deliverables:**

- [ ] Request/response schema: optional `study_instance_uid`, `site_id`, `model_version` (aligned with `docs/clinical-workflow.md` gaps).  
- [ ] Extend `audit.log_event` payload for these fields on `/predict` and `/report`.  
- [ ] Auth stub (API key or mTLS placeholder) behind env flag — document only until deployment target is fixed.  

**Exit criteria:** A single audit line uniquely ties an inference to a model artifact and external ID.

---

## 4. Suggested timeline (small team, repo-focused)

| Week block | Phases |
|------------|--------|
| 1 | Phase 0 + start Phase 1 (one cohort YAML + WMH script logging path) |
| 2 | Phase 2 (manifest module + segmentation training hooked) |
| 3 | Phase 3 (verifiers + strict mode on WMH loader) |
| 4 | Phase 4 (eval harness + metrics JSON) |
| 5–6 | Phase 5 + Phase 6 (JSONL summaries + synthetic stress set) |
| 7+ | Phase 7 as integration needs appear; parallel with DICOM SEG roadmap from hospital-grade doc |

Adjust speed if you are solo; **Phase 2 + 4** give the most “trial credibility” per hour.

---

## 5. What this plan explicitly does **not** include (see other docs)

- Full **QMSR / 510(k)** documentation (see `roadmap-research-to-hospital-grade.md`).  
- **IHE AIW-I / DICOM SEG SR** production integration (see `clinical-workflow.md` Phase D).  
- **Annotation adjudication UI** (design-partner phase in roadmap).  

Those are larger than repo-only workflow work; this plan **feeds** them with manifests, metrics, and logs.

---

## 6. Success metrics for “done enough” for a methods paper or sponsor demo

1. Train WMH (or BraTS) with a **manifest** and **frozen YAML** set.  
2. Run **eval harness** on held-out split; produce **metrics.json** with Dice and case list.  
3. Show **verifier** log for one failed QC case.  
4. Show **training_runs.jsonl** summary of last N runs.  

Together, that story matches **clinical trials and regulated ML engineering** vocabulary: traceability, QC, locked eval, and operations visibility—without changing the scientific core of your imaging stack.
