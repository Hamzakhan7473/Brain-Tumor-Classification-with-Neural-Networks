# Whole Project Architecture

Single reference for the **Brain Tumor MRI AI** codebase: structure, data flow, components, and deployment. For a one-diagram Figma prompt, see [Figma prompt: whole project](#figma-prompt-whole-project) at the bottom.

---

## 1. Overview

End-to-end pipeline for **brain tumor classification** from MRI (2D slices) with interpretability and AI-assisted report drafts:

- **Input:** JPG/PNG or DICOM (file/bytes).
- **Training:** Raw images (+ optional metadata CSV for patient-level split) → data loader → three 2D classifiers (Custom CNN, Xception, Transfer) → saved `.keras` models.
- **Inference:** Image or DICOM → preprocessing → model → label, confidence, probabilities; optional saliency map.
- **LLM:** Constrained report/explanations (no size/location); human-in-the-loop before export.
- **Consumers:** Streamlit app (demo UI) and REST API (PACS/cloud).
- **Governance:** Config-driven; optional audit log (JSONL); Docker for API.

**Scope:** Research prototype; roadmap to hospital-grade (3D segmentation, DICOM SEG/SR, FDA path) is in `docs/roadmap-research-to-hospital-grade.md`.

---

## 2. Directory Structure

```
brain_tumor_Cnn/
├── README.md
├── requirements.txt
├── .env.example
├── .env                    # (gitignored) GOOGLE_API_KEY, KAGGLE_*, etc.
├── .gitignore
├── .dockerignore
├── Dockerfile              # API image for Cloud Run / ECS
│
├── configs/
│   ├── data.yaml           # Paths, splits, patient_split, metadata_file, augmentation, classes
│   ├── custom_cnn.yaml
│   ├── xception.yaml
│   ├── transfer.yaml
│   └── app.yaml            # Streamlit + LLM provider list, models_for_inference
│
├── data/
│   ├── raw/                # Kaggle dataset (class folders: glioma, meningioma, pituitary, notumor)
│   ├── processed/          # Optional processed indices
│   └── README.md           # Download and metadata CSV instructions
│
├── models/
│   ├── custom_cnn.py       # Custom CNN architecture
│   ├── xception_model.py   # Xception + head
│   ├── transfer_model.py   # Transfer model (e.g. EfficientNetB0)
│   ├── checkpoints/        # Training checkpoints
│   └── saved/              # Final .keras for deployment (custom_cnn, xception, transfer)
│
├── notebooks/
│   └── README.md           # EDA, training, saliency notebooks
│
├── src/
│   ├── data/
│   │   ├── dataset.py      # TF Dataset, patient-level or image-level split, load_image_for_inference
│   │   ├── augmentation.py # Train/val augmentation from config
│   │   └── dicom_loader.py # load_dicom_slice, load_dicom_series_to_slice (→ 1,H,W,3 + metadata)
│   │
│   ├── training/
│   │   ├── train.py        # run_training(), callbacks
│   │   └── callbacks.py    # Early stopping, checkpoint, LR schedule
│   │
│   ├── inference/
│   │   ├── predict.py      # load_model, load_model_and_predict, predict_from_bytes; MODEL_INPUT_SIZES
│   │   └── saliency.py     # generate_saliency_map (gradient-based; UI only)
│   │
│   ├── llm/
│   │   ├── client.py       # get_llm_client, generate_with_image (Gemini, etc.)
│   │   ├── explanations.py # explain_image (constrained: no size/location)
│   │   └── report.py       # build_report (insights, cases, next steps)
│   │
│   ├── api/
│   │   └── main.py         # FastAPI: GET /health, POST /predict, POST /report; DICOM or image
│   │
│   └── app/
│       ├── streamlit_app.py   # Main entry: upload → predict → saliency → report → export
│       ├── report_helpers.py  # build_findings_rows, recommended_next_steps, CLASS_DISPLAY
│       ├── audit.py           # log_event (inference, LLM, report, export) → JSONL
│       ├── utils.py           # load_app_config, get_class_names, project_root
│       ├── pages/
│       │   ├── upload_and_predict.py
│       │   ├── model_comparison.py   # Side-by-side model comparison
│       │   └── chat_with_scan.py     # Chat with MRI image (LLM)
│       └── components/
│           └── apple_ui.py   # Hero, cards, report layout, CSS
│
├── scripts/
│   ├── download_data.sh
│   ├── download_data_kagglehub.py
│   ├── train_custom_cnn.py
│   ├── train_xception.py
│   ├── train_transfer.py
│   ├── evaluate_models.py
│   ├── evaluate_saliency_vs_mask.py  # Stub for saliency vs mask validation
│   ├── run_api.sh            # Run uvicorn for API
│   ├── check_backend_and_data.py
│   ├── fix_tensorflow_protobuf.py
│   └── fix_rich_manual.py
│
└── docs/
    ├── project-architecture.md      # This file
    ├── figma-architecture-prompt.md  # Figma prompts (current + Merlin-like + whole project)
    ├── api.md                        # API / function reference
    ├── methodology.md
    ├── challenges.md
    ├── roadmap-research-to-hospital-grade.md
    ├── roadmap-radiologist-questions.md
    ├── workflows-and-features.md
    ├── clinical-workflow.md        # Phased radiology path + engineering backlog
    ├── startup-gap-analysis.md
    ├── intelligence-market-regulatory-gtm.md
    └── assets/
        └── brain_mri_foundation_model_pipeline.svg   # Future Merlin-like pipeline (reference)
```

---

## 3. End-to-End Data Flow

| Stage | Input | Output | Key modules |
|-------|--------|--------|-------------|
| **Ingest** | JPG/PNG file or DICOM (file/bytes) | Normalized image array (1, H, W, 3) | `dicom_loader` (DICOM), `dataset` / `predict` (image) |
| **Training data** | `data/raw/` + optional `metadata.csv` (filename, patient_id) | Train/val/test splits (patient-level if CSV) | `configs/data.yaml`, `dataset.py` |
| **Training** | Data loader + model config | Saved `.keras` in `models/saved/` | `train.py`, `callbacks.py`, `scripts/train_*.py` |
| **Inference** | Image bytes or DICOM | Label, confidence, probabilities (optional saliency) | `predict.py`, `saliency.py` |
| **Report** | Prediction + image | LLM draft (constrained); human review → export | `report.py`, `explanations.py`, `client.py` |
| **Consumers** | User upload or API request | Streamlit dashboard or JSON response | `streamlit_app.py`, `api/main.py` |
| **Audit** | Inference / LLM / export events | JSONL log | `audit.py` |

**One-line flow:**  
Input (JPG/DICOM) → Load/Split (patient-level if metadata) → Train (Custom CNN, Xception, Transfer) → Save → API / App → Predict + Saliency + LLM (constrained) → Human review → Export + Audit.

---

## 4. Component Map

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **Config** | `configs/*.yaml`, `.env` | Paths, splits, augmentation, model hyperparams, app/LLM settings, secrets |
| **Data** | `dataset.py` | Build TF Dataset; patient-level or stratified split; load single image for inference |
| **Data** | `dicom_loader.py` | DICOM → slice → (1,H,W,3) + metadata; used by API and inference path |
| **Data** | `augmentation.py` | Train/val augmentations from `data.yaml` |
| **Models** | `custom_cnn.py`, `xception_model.py`, `transfer_model.py` | Model build; training scripts load these + config |
| **Training** | `train.py`, `callbacks.py` | Training loop; early stopping, checkpoint, LR schedule |
| **Inference** | `predict.py` | Load saved model; preprocess; return label, confidence, probabilities |
| **Inference** | `saliency.py` | Gradient-based saliency (explainability; not validated vs ground truth) |
| **LLM** | `client.py` | Multimodal client (Gemini); image + prompt → text |
| **LLM** | `explanations.py`, `report.py` | Constrained text (no size/location); report builder |
| **API** | `api/main.py` | FastAPI: `/health`, `/predict`, `/report`; image or DICOM in → JSON out |
| **App** | `streamlit_app.py` | Main UI: upload, model choice, predict, saliency, report, export |
| **App** | `pages/*.py`, `components/apple_ui.py` | Model comparison, chat with scan; shared UI components |
| **Governance** | `audit.py` | Log inference, LLM, report, export to JSONL |
| **Deploy** | `Dockerfile`, `run_api.sh` | API container; uvicorn entrypoint |

---

## 5. Config and Environment

- **configs/data.yaml:** `raw_dir`, `processed_dir`, `splits` (train/val/test, `patient_split`, `metadata_file`), `classes`, `image` (target_size, normalize, mean/std), `augmentation`, `batch_size`.
- **configs/custom_cnn.yaml, xception.yaml, transfer.yaml:** Model-specific hyperparameters and paths.
- **configs/app.yaml:** Streamlit and LLM provider list; `models_for_inference`.
- **.env:** `GOOGLE_API_KEY` (LLM), `KAGGLE_USERNAME`/`KAGGLE_KEY` if using Kaggle CLI; optional `DATA_DIR`.

---

## 6. Deployment

- **Streamlit (local):** `streamlit run src/app/streamlit_app.py`
- **API (local):** `uvicorn src.api.main:app --host 0.0.0.0 --port 8000` or `scripts/run_api.sh`
- **API (Docker):** `docker build -t brain-tumor-mri-api . && docker run -p 8000:8000 brain-tumor-mri-api`  
  See `README.md` and `docs/api.md` for endpoints and DICOM support.

---

## 7. Figma Prompt: Whole Project

Use this in Figma (or any diagram tool) to generate a **single diagram of the whole project** (current product only).

**Copy-paste:**

Create one system architecture diagram for the **Brain Tumor MRI AI** project. Top-to-bottom or left-to-right flow. Rectangles for components, arrows for data/control; label arrows; max 2 lines per box.

**1. PROBLEM & SCOPE**  
Title: "Brain Tumor MRI AI — whole project".  
Content: "Classify brain MRI (Glioma, Meningioma, Pituitary, No Tumor). 2D slice classifiers + interpretability (saliency) + constrained LLM report drafts. Patient-level split when metadata provided; DICOM + JPG/PNG input; API-first deployment."  
Callout: "Research prototype; roadmap to hospital-grade (docs/roadmap-research-to-hospital-grade.md)."

**2. CONFIG & DATA**  
- Box "configs/*.yaml" (data, model, app) + ".env" (GOOGLE_API_KEY, Kaggle).  
- Box "data/raw" + optional "metadata.csv (filename, patient_id)".  
- Arrow to "Data loader (dataset.py)" — label "patient-level or image-level split".  
- Box "dicom_loader.py" — "DICOM → slice → (1,H,W,3)".  
- Arrows: raw + metadata → dataset; DICOM path used at inference/API.

**3. MODELS & TRAINING**  
- Three boxes: "Custom CNN", "Xception", "Transfer (e.g. EfficientNetB0)" — configs: custom_cnn.yaml, xception.yaml, transfer.yaml.  
- Box "Training engine (train.py)" — callbacks: early stopping, checkpoint, LR.  
- Box "models/saved/*.keras".  
- Arrows: Data loader → Training engine; Training engine → Saved models; "Patient-level split for valid metrics".

**4. INFERENCE & API**  
- Box "Inference (predict.py)" — image or DICOM → label, confidence, probabilities.  
- Box "Saliency (saliency.py)" — gradient map (UI explainability).  
- Box "REST API (src/api/main.py)" — "GET /health", "POST /predict", "POST /report".  
- Arrows: Image/DICOM → API → Inference; Inference → predictions; optional Saliency; predictions + image → LLM.

**5. LLM & REPORT**  
- Box "LLM client (Gemini)" — image + prompt → text.  
- Box "Explanations" + "Report builder" — constrained (no size/location).  
- Box "Human-in-the-loop" — review before export; "AI-assisted" label.  
- Arrow: predictions + image → LLM → draft → Human review → Export.

**6. CONSUMERS**  
- Box "Streamlit app (streamlit_app.py)" — upload, dashboard, saliency, report, export; pages: upload_and_predict, model_comparison, chat_with_scan.  
- Box "REST API clients" — PACS, scripts, Docker (Cloud Run / ECS).  
- Arrows: both use Inference + LLM.

**7. GOVERNANCE**  
- Box "Audit log (audit.py → JSONL)" — inference, LLM, report, export.  
- Box "Dockerfile" — API image for Cloud Run/AWS.  
- Dashed arrows: Config → Training, API, LLM; Audit ← App & API.

**Style**  
- Input/config = neutral; data/training = blue/gray; inference/API = teal; LLM/report = green; consumers = orange/purple; governance = light gray.  
- One-line at bottom: "Config + Data → Train → Saved models → API/App → Predict + Saliency + LLM (constrained) → Review → Export + Audit."

---

This document is the **single reference for whole project architecture**. For Figma prompts only (current product, Merlin-like future, or radiology pipeline), use `docs/figma-architecture-prompt.md`.
