# Figma Architecture Diagram Prompt

Copy the prompt below into Figma (e.g. AI design or diagram generation) to create an architecture diagram for the backend, model training, and problem statement.

**Whole project architecture:** The full prompt for a single diagram of the entire project (config, data, training, inference, API, LLM, app, audit, deployment) is in [docs/project-architecture.md](project-architecture.md) §7. Use that for one “whole project” Figma diagram.

---

## Merlin-like brain MRI foundation model (future pipeline only)

*Use this for a diagram of the future “brain MRI Merlin” pipeline: 3D + vision-language + EHR, not the current 2D classifier product. Reference: [docs/assets/brain_mri_foundation_model_pipeline.svg](assets/brain_mri_foundation_model_pipeline.svg).*

**Copy-paste:**

Create a clean, vertical pipeline diagram for a **brain MRI foundation model** (Merlin-style: 3D vision + text + EHR). One column or 2–3 columns; top-to-bottom flow. Rectangles for components, arrows for data flow; label arrows; max 2 lines per box. No paragraphs inside shapes.

**1. ROW 1 — DATA SOURCES (three boxes side by side)**  
- **Brain MRI scans** — subtext: "T1, T2, FLAIR, DWI".  
- **Radiology reports** — subtext: "Findings + impressions".  
- **EHR / ICD codes** — subtext: "Diagnoses, phenotypes".  
- Arrows from each box down to Row 2.

**2. ROW 2 — PREPROCESSING (three boxes, same order)**  
- **MRI preprocessing** — subtext: "Skull-strip, normalize, register".  
- **Report splitting** — subtext: "By brain region / lobe".  
- **Phecode mapping** — subtext: "PheWAS grouping".  
- Arrows from each box down; MRI and EHR arrows can converge toward center for Row 3.

**3. ROW 3 — MODEL (two main boxes)**  
- **3D Image encoder** — subtext: "3D ResNet or ViT-3D".  
- **Text encoder** — subtext: "ClinicalBERT / Longformer".  
- Arrows: MRI preprocessing → 3D Image encoder; Report splitting → Text encoder; Phecode mapping → both (or to training).  
- Arrows from both encoders down to Row 4.

**4. ROW 4 — TRAINING (two boxes)**  
- **Contrastive loss** — subtext: "InfoNCE (image ↔ text)".  
- **EHR supervision** — subtext: "Binary cross entropy".  
- Arrows from Row 3 encoders into these; then one arrow down to Row 5.

**5. ROW 5 — DOWNSTREAM TASKS (four boxes + one wide box)**  
- **Zero-shot classification**  
- **Report gen.** — subtext: "LLM adapter".  
- **Segmentation** — subtext: "UNet decoder".  
- **Disease risk** — subtext: "5-year prediction".  
- **Cross-modal retrieval** — one wide box: "Cross-modal retrieval (image ↔ report)".  
- Dashed or solid arrows from "Training" (Row 4) to all downstream tasks.

**TITLE (top)**  
- "Brain MRI foundation model pipeline (Merlin-like)".  
- Small note: "Future direction: 3D + VLM + EHR; not current 2D classifier product."

**Style**  
- Color: MRI/data = blue; reports = purple/violet; EHR = green; encoders = warm (orange/red, pink); training = amber/gold and green; downstream = neutral gray/beige.  
- One-line summary at bottom optional: "Data (MRI + reports + EHR) → Preprocess → 3D + text encoders → Contrastive + EHR training → Zero-shot, report gen, segmentation, risk, retrieval."

**Short version (if character limit):**  
Brain MRI foundation model (Merlin-like): (1) Data: Brain MRI (T1/T2/FLAIR/DWI), Radiology reports, EHR/ICD. (2) Preprocess: skull-strip/normalize/register; report split by region; Phecode/PheWAS. (3) Model: 3D image encoder (3D ResNet/ViT-3D), Text encoder (ClinicalBERT/Longformer). (4) Training: InfoNCE contrastive (image↔text), EHR binary cross entropy. (5) Downstream: zero-shot classification, report gen (LLM adapter), segmentation (UNet), disease risk (5-y), cross-modal retrieval. Vertical flow; boxes and arrows; 2 lines max per box; color by layer.

---

## Best prompt (updated — post radiologist feedback & Phase 1 build)

*Use this version to reflect: patient-level splits, DICOM ingestion, REST API, Docker/deployment, constrained LLM, audit trail, and human-in-the-loop.*

**Copy-paste:**

Create a clean, professional system architecture diagram for a Brain Tumor MRI AI platform that has been updated for clinical rigor and hospital readiness. Show one end-to-end flow (left-to-right or top-to-bottom). Use rectangles for components, arrows for data/control flow; label every arrow; max 2 lines per box. No paragraphs inside shapes.

**1. PROBLEM & SCOPE (top or left)**  
- Title: "Problem & scope".  
- Content: "Classify brain MRI (Glioma, Meningioma, Pituitary, No Tumor) with interpretability and AI-assisted report drafts. Updated for: no data leakage (patient-level split), DICOM input path, API-first deployment, and LLM constrained to classifier output (no ungrounded size/location)."  
- Small callout: "Research prototype today; roadmap to hospital-grade (3D segmentation, DICOM SEG/SR, FDA path)."

**2. INPUT & DATA PIPELINE**  
- **Inputs:** Two entry points — box "JPG/PNG upload" and box "DICOM (file or bytes)" with arrow to "DICOM loader (dicom_loader.py)" → extract slice, normalize, (1,H,W,3).  
- **Data for training:** Box "Raw data (data/raw)" + optional "Metadata CSV (filename, patient_id)" with arrow to "Data loader (dataset.py)".  
- **Split:** Box "Train/Val/Test" — label "Patient-level split (same patient never in two splits)" when metadata present; else "Stratified image-level split".  
- **Preprocessing:** Resize, normalize, augment (training only); config from data.yaml.  
- Arrows: Raw + metadata → Data loader; Data loader → "Training engine".

**3. MODEL TRAINING**  
- Three model boxes: "Custom CNN", "Xception", "Transfer (e.g. EfficientNetB0)" — each fed by Data loader; configs (custom_cnn.yaml, xception.yaml, transfer.yaml).  
- One box: "Training engine (train.py)" — callbacks: early stopping, checkpoint, LR schedule.  
- Output: "Saved models (models/saved/*.keras)" — one per model.  
- Arrow label: "Patient-level split enforced for valid metrics".

**4. INFERENCE & API (first-class)**  
- Box "Inference (predict.py)" — input: image bytes or DICOM; load model, preprocess → label, confidence, probabilities.  
- Box "Saliency (saliency.py)" — gradient-based map (UI explainability; not validated vs ground truth).  
- Box "REST API (src/api/main.py)" — three endpoints: "GET /health", "POST /predict" (image or DICOM → JSON), "POST /report" (predict + LLM draft). Label: "API-first for PACS/Cloud Run/Lambda".  
- Arrows: Image/DICOM → REST API → Inference; Inference → predictions; optional Saliency; predictions + image → LLM for report.

**5. LLM & REPORTING (constrained)**  
- Box "LLM client (Gemini)" — image + prompt in; text out.  
- Box "Explanations" and "Report builder" — prompts constrain: no size, no precise location; only classifier output is model-derived.  
- Box "Human-in-the-loop" — "Clinician review before export"; "Report marked AI-assisted".  
- Small note: "LLM = documentation support; not the regulated core (per FDA CDS guidance)."  
- Arrow: predictions + image → LLM; LLM → draft report → Human review → Export.

**6. CONSUMERS**  
- Box "Streamlit app" — upload → dashboard, saliency, report, export (demo UI).  
- Box "REST API clients" — PACS, scripts, Cloud Run/Lambda (Docker).  
- Arrows: REST API and Streamlit both use Inference + LLM; label "Docker deploy (Cloud Run / ECS)".

**7. GOVERNANCE & DEPLOYMENT**  
- Box "Audit log (JSONL)" — log: inference, LLM call, report generation, export.  
- Box "Config & secrets" — configs/*.yaml, .env (GOOGLE_API_KEY).  
- Box "Deployment" — "Dockerfile → Cloud Run / AWS (credits); BAA-ready path later."  
- Dashed arrows: Config → Training, API, LLM; Audit ← API & App.

**Style**  
- Color: input = neutral; data/training = blue/gray; inference/API = teal; LLM/report = green; consumers = orange/purple; governance = light gray.  
- Optional one-line flow at bottom: "Input (JPG/DICOM) → Load/Split → Train (patient-split) → Save → API → Predict + Saliency + LLM (constrained) → Human review → Export + Audit".

**Short version (if character limit):**  
Architecture: (1) Input: JPG/PNG + DICOM (dicom_loader). (2) Data: raw + optional metadata CSV → patient-level split (dataset.py). (3) Train: Custom CNN, Xception, Transfer → saved .keras. (4) Inference + REST API: /health, /predict, /report; DICOM or image in → JSON out. (5) LLM: constrained (no size/location); human-in-the-loop before export. (6) Consumers: Streamlit + API (Docker → Cloud Run/AWS). (7) Audit log + config. Style: boxes and arrows; label flows; 2 lines max per box; color by layer.

---

## Prompt (copy-paste) — original

**Create a clean, professional system architecture diagram for a Brain Tumor MRI Classification platform. Include these three sections:**

### 1. PROBLEM STATEMENT (top or left)
- **Title:** "Problem Statement"
- **Content:** "Classify brain MRI scans into tumor types (Glioma, Meningioma, Pituitary, No Tumor) to support clinical decision-making. Goals: high accuracy (≥98–99%), interpretability (saliency maps), and AI-generated clinical-style reports for doctors."
- Use a small card or callout box with a light background and short bullet points.

### 2. DATA & MODEL TRAINING PIPELINE (center / main flow)
- **Data:** Box "Kaggle Brain Tumor MRI Dataset" → arrows to "Raw Data (data/raw)" and "Data Loader (src/data/dataset.py)" with preprocessing (resize, normalize, augment).
- **Training:** Three parallel model branches:
  - **Custom CNN** — Conv2D → BatchNorm → ReLU → MaxPool blocks + dense head; trained from scratch (scripts/train_custom_cnn.py).
  - **Xception** — Pre-trained backbone + custom classification head; fine-tuned (scripts/train_xception.py).
  - **Transfer model** — Second pre-trained model (e.g. EfficientNet/ResNet) + head; fine-tuned (scripts/train_transfer.py).
- **Training loop:** "Training Engine (src/training/train.py)" with inputs "Data Loader" and "Model Config (configs/*.yaml)", outputs "Checkpoints" and "Saved model (.keras)".
- **Callbacks:** Early stopping, model checkpointing, optional learning-rate scheduler.
- **Output:** "Saved models (models/saved/)" — one artifact per model: custom_cnn_best.keras, xception_best.keras, transfer_best.keras.

### 3. BACKEND / INFERENCE & REPORTING (right or bottom)
- **Inference:** Box "Inference API (src/inference/predict.py)" — loads saved model, preprocesses image, returns class label + confidence + probabilities.
- **Interpretability:** Box "Saliency (src/inference/saliency.py)" — generates saliency map from model gradients.
- **LLM layer:** Box "LLM Client (src/llm/client.py)" — calls Gemini (or selected provider) with image + text. Two consumers: "Explanations (explanations.py)" and "Report builder (report.py)" for clinical-style text (insights, next steps).
- **Config:** Small box "Configs (configs/data.yaml, app.yaml)" feeding into training and app.
- **Environment:** ".env (GOOGLE_API_KEY)" for LLM.

### 4. CONSUMER (optional)
- **App:** "Streamlit app (src/app/streamlit_app.py)" — upload MRI → run inference + saliency + LLM report → HealthTech dashboard (findings, export).

### Style
- Use rectangles for components, arrows for data/control flow.
- Label arrows briefly (e.g. "MRI image", "predictions", "saved .keras").
- Use a light color for "Problem", blue/gray for "Data/Training", green/teal for "Inference/LLM", and one accent for "App".
- Keep text short; no long paragraphs inside shapes.
- Optional: add a small "Problem → Data → Train → Save → Infer → Report" flow as a one-line summary at the top or bottom.

---

## Short version (if character limit)

**Backend + training architecture diagram:**

1. **Problem:** Brain MRI → classify Glioma / Meningioma / Pituitary / No Tumor; support doctors with interpretability and reports.
2. **Data:** Kaggle dataset → raw → dataset.py (load, augment, batch).
3. **Training:** Three models (Custom CNN, Xception, Transfer) trained via train.py + callbacks; configs in configs/*.yaml; outputs in models/saved/*.keras.
4. **Backend:** predict.py (load model, predict), saliency.py (gradient-based map), llm/client.py + explanations.py + report.py (Gemini, API key in .env).
5. **Consumer:** Streamlit app uploads MRI, runs inference and LLM, shows dashboard and export.

Use boxes and arrows; label flows; minimal text per box.

---

## Radiology pipeline (full diagram — best for Figma)

Use this prompt for a single, end-to-end radiology architecture diagram. Left-to-right or top-to-bottom flow; one clear pipeline.

**Prompt (copy-paste):**

Create a single end-to-end architecture diagram for a Radiology AI pipeline: from MRI input to structured report and follow-ups. Use a clear left-to-right (or top-to-bottom) flow. No paragraphs inside boxes — only short labels.

**1. INPUT (left/top)**  
- Box: "MRI scan (brain)" with icon or placeholder.  
- Arrow labeled "upload" to next stage.

**2. DATA & PREPROCESSING**  
- Box: "Raw dataset (e.g. Kaggle Brain Tumor MRI)".  
- Box: "Data loader" — resize, normalize, augment; train/val split.  
- Arrows: dataset → loader; label arrows "config (splits, augmentation)".

**3. MODEL TRAINING (parallel branches)**  
- Three boxes in a row or column:  
  - "Custom CNN" (from scratch)  
  - "Xception" (pre-trained, fine-tuned)  
  - "Transfer model" (e.g. EfficientNet/ResNet, fine-tuned)  
- One box: "Training engine" — callbacks: early stopping, checkpoint, LR schedule; config-driven.  
- Arrows: Data loader → each model; Model config → Training engine; Training engine → "Saved models (.keras)".  
- One box: "Saved models" — list: custom_cnn_best, xception_best, transfer_best.

**4. INFERENCE & INTERPRETABILITY**  
- Box: "Inference API" — load model, preprocess image → prediction (class, confidence, probabilities).  
- Box: "Saliency / explainability" — gradient-based map (which regions drove the decision).  
- Arrows: MRI image → Inference API; Inference API → Saliency; Inference API → "predictions".

**5. LLM & REPORTING**  
- Box: "LLM client (e.g. Gemini)" — image + text in, clinical-style text out.  
- Two boxes: "Explanations" (short) and "Report builder" (structured: findings, insights, next steps).  
- Arrow: predictions + image → LLM; LLM → Explanations & Report.  
- Small note: "API key via .env; config (app.yaml)".

**6. CLINICAL CONSUMER**  
- Box: "Radiology assistant UI (e.g. Streamlit)" — upload MRI → run pipeline → dashboard: findings, status pills (Normal/Follow/Refer), saliency, AI insights, recommended next steps, export report (HTML/PDF).  
- Arrows: All of the above feed into this UI; label "audit-friendly, deployable".

**7. EXTERNAL (optional)**  
- Small boxes: "Config (data.yaml, model yamls)" and ".env (secrets)" with dashed arrows into Training engine and LLM.

**Style and best practices:**  
- Rectangles for components; rounded for "output" or "artifact" (e.g. Saved models, Report).  
- Solid arrows = data flow; dashed = config/secrets.  
- Label every arrow (e.g. "MRI", "predictions", "saved .keras", "structured report").  
- Color coding: input = neutral; data/training = blue/gray; inference/saliency = teal; LLM/report = green; UI = one accent (e.g. orange or purple).  
- Optional: add a thin horizontal "timeline" bar at top: "Acquire → Ingest → Train → Deploy → Infer → Explain → Report → Follow-up".  
- Keep the diagram readable at one glance; no more than 2 lines of text per box.
