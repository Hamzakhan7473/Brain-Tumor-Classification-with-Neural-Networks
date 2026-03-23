# Workflows and Features — Brain Tumor CNN Project

A single list of **workflows** (end-to-end flows) and **features** (capabilities) for the project.  
**Built** = implemented today. **Planned** = from roadmap/challenges. **To do** = from startup intelligence (see `docs/intelligence-market-regulatory-gtm.md` and `docs/startup-gap-analysis.md`).

---

## 1. Data

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 1.1 | **Download dataset** | Built | Script `scripts/download_data_kagglehub.py`: download Kaggle brain tumor MRI dataset (e.g. masoudnickparvar/brain-tumor-mri-dataset) and merge into `data/raw/<class>/`. |
| 1.2 | **Image-level train/val/test split** | Built | Stratified split by image (75/15/10) via Keras `image_dataset_from_directory` + `validation_split`. |
| 1.3 | **Patient-level train/val/test split** | Built | When `splits.patient_split: true` and `splits.metadata_file` (CSV with `filename`, `patient_id`) are set: split by **patient ID** so the same patient is never in two splits; stratified by class. |
| 1.4 | **Preprocessing** | Built | Resize to 224×224 (or 299 for Xception), normalize to [0,1], optional ImageNet stats. |
| 1.5 | **Augmentation (training only)** | Built | Horizontal flip, rotation, width/height shift, zoom, brightness/contrast; config in `configs/data.yaml`. |
| 1.6 | **Metadata CSV for patient split** | Built (config + code) | You supply `data/raw/metadata.csv` with `filename`, `patient_id`; data loader uses it when patient split is enabled. |

---

## 2. Models and Training

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 2.1 | **Custom CNN** | Built | Conv blocks (Conv2D → BatchNorm → ReLU → MaxPool → Dropout) + global pooling + dense head; target ≥98% (Challenge 1). |
| 2.2 | **Xception transfer** | Built | Pre-trained Xception, optional unfreeze of last N layers, custom classification head. |
| 2.3 | **Second transfer model (e.g. EfficientNetB0)** | Built | Same protocol; target ≥99% (Challenge 2). |
| 2.4 | **Training pipeline** | Built | `scripts/train_custom_cnn.py`, `train_xception.py`, `train_transfer.py`; use `src/training/train.run_training()` with configs. |
| 2.5 | **Training config** | Built | YAML configs: `configs/custom_cnn.yaml`, `xception.yaml`, `transfer.yaml`, `data.yaml`. |
| 2.6 | **Callbacks** | Built | ModelCheckpoint (best val accuracy), EarlyStopping, ReduceLROnPlateau. |
| 2.7 | **Loss and metrics** | Built | Categorical cross-entropy; Adam/AdamW; accuracy and loss on validation. |

---

## 3. Inference and Interpretability

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 3.1 | **Load model and predict** | Built | `src/inference/predict.load_model_and_predict(model_name, image_batch)` — returns class probabilities and predicted label. |
| 3.2 | **Predict from bytes** | Built | `predict_from_bytes(image_bytes, model_name)` for Streamlit uploads. |
| 3.3 | **Multi-model inference** | Built | Support for custom_cnn, xception, transfer (EfficientNetB0); load from `models/saved/`. |
| 3.4 | **Saliency map** | Built | `src/inference/saliency.generate_saliency_map(model, image_batch, class_idx)` — gradient of winning logit w.r.t. input (Simonyan et al.); for UI explainability. |
| 3.5 | **Saliency vs mask validation** | Planned | Script stub `scripts/evaluate_saliency_vs_mask.py`; implement when dataset with segmentation masks is available (Dice/IoU vs binarized saliency). |

---

## 4. Streamlit App (UI)

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 4.1 | **Report dashboard (main)** | Built | Upload brain MRI (JPG/PNG) → view primary prediction, confidence, findings card, recommendations, similar cases, saliency overlay. |
| 4.2 | **Model comparison** | Built | Page: one upload → side-by-side predictions from Custom CNN, Xception, Transfer model (Challenge 6). |
| 4.3 | **Chat with scan** | Built | Page: conversational UI; send image + user message to LLM; session history (Challenge 4). |
| 4.4 | **LLM provider selection** | Built | Sidebar dropdown to choose LLM (e.g. Gemini); config in `configs/app.yaml` (Challenge 3). |
| 4.5 | **Dark mode** | Built | Toggle in sidebar. |
| 4.6 | **AI explanation** | Built | Button to generate short LLM explanation of the scan given the model prediction. |
| 4.7 | **Full report generation** | Built | Button to generate structured report (prediction summary, insights, analogous cases, next steps) via `src/llm/report.build_report()` (Challenge 5). |
| 4.8 | **Report disclaimer** | Built | Info box: AI content is draft; size/location not grounded to measurements; clinician review required. |
| 4.9 | **Export report** | Built | Download report as HTML (after marking “reviewed by clinician”); human-in-the-loop. |
| 4.10 | **Apple-style UI** | Built | Components in `src/app/components/apple_ui.py`: hero, cards, patient card, topbar, etc. |

---

## 5. LLM (Multimodal)

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 5.1 | **Gemini client** | Built | `src/llm/client.get_llm_client(provider, model_id)`; `generate_with_image(client, image, prompt)`. |
| 5.2 | **Short explanation** | Built | `src/llm/explanations.explain_image()` — brief explanation given image + model prediction; prompt constrains no size/precise location. |
| 5.3 | **Full report** | Built | `src/llm/report.build_report()` — sections: prediction summary, insights, analogous cases, next steps; prompt states descriptions not grounded to measurements. |
| 5.4 | **Chat with image** | Built | Chat page sends image + messages to LLM. |
| 5.5 | **LLM grounding to mask** | Planned | Optional: add 2D segmentation, pass mask or bbox to LLM for description “within highlighted region” (roadmap). |

---

## 6. Governance and Audit

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 6.1 | **Audit logging** | Built | `src/app/audit.log_event()` — append JSONL to `logs/audit.log.jsonl` for inference, LLM explanation, report generation, export. |
| 6.2 | **Human-in-the-loop** | Built | Export enabled only after “Mark AI-generated content as reviewed by a clinician”; report marked as AI-assisted. |
| 6.3 | **Service-first design** | Built | Data, training, inference, LLM, audit are importable modules; Streamlit is a demo on top; production would use APIs. |

---

## 7. Evaluation and Scripts

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 7.1 | **Backend and data check** | Built | `scripts/check_backend_and_data.py` — verify config, data layout, class counts, one batch. |
| 7.2 | **Model evaluation** | Built | `scripts/evaluate_models.py` — evaluate saved models on test/val data. |
| 7.3 | **Per-class metrics** | Built / Config | Precision, recall, F1; optional confusion matrix, ROC (methodology). |

---

## 8. Planned / Future (from roadmap and challenges)

| # | Workflow / Feature | Status | Description |
|---|-------------------|--------|-------------|
| 8.1 | **Saliency validation** | Planned | Implement mask loading in `evaluate_saliency_vs_mask.py` when dataset with masks is available; report Dice/IoU. |
| 8.2 | **2D segmentation + grounding** | Planned | Add 2D segmentation model (e.g. U-Net), output mask or bbox; optionally pass to LLM for grounded description. |
| 8.3 | **Per-layer dropout/activation tuning** | Planned | Configurable per-layer dropout and activations; see `docs/roadmap-radiologist-questions.md` §6. |
| 8.4 | **3D pipeline (volumes, midline)** | Future | DICOM/NIfTI load, 3D model (e.g. UNet/Swin-UNETR), volumetric measures, midline shift; documented as future work. |
| 8.5 | **Surgical utility** | Future | 2D bbox/centroid as optional first step; full surgical pipeline (3D, registration, vascular) as separate project. |

---

## 9. To do (startup path — aligned with intelligence)

*Source: `docs/intelligence-market-regulatory-gtm.md`, `docs/startup-gap-analysis.md`. Order = suggested priority.*

**Cloud credits:** We have **AWS**, **Google Cloud**, and **other** free credits. Use them for deployment, API, training, and design-partner pilots so foundation and evidence work stays within credits (no heavy infra spend until revenue or funding). The **Cloud** column below says which credit to use for each item where it applies.

**24-month hospital-grade roadmap:** For the full path from research prototype to FDA-clearable product (DICOM, 3D segmentation, DICOM SEG/SR, IHE, QMSR, 510(k)), see **`docs/roadmap-research-to-hospital-grade.md`**. The to-do below is consistent with that roadmap; the hospital-grade doc adds phased sprints, staffing, costs, datasets, regulatory path, and pilot plan.

**Phase 1 build status:** DICOM **ingestion** (T2 in), **REST API** (T4), and **Docker** (T5) are implemented: `src/data/dicom_loader.py`, `src/api/main.py`, `Dockerfile`, `scripts/run_api.sh`. Run with `uvicorn src.api.main:app --port 8000` or `docker run -p 8000:8000 brain-tumor-mri-api`. DICOM **output** (SEG/SR) and full PACS integration are later phases.

### Phase 1: Foundation (0–6 months)

| # | To do | Status | Cloud | Notes |
|---|-------|--------|--------|------|
| T1 | **Define first segment and value prop** (e.g. design partners for retrospective validation; or triage vs draft report for neuro). | **Done (doc)** | — | See `docs/startup-gap-analysis.md` §5 (Initial segment and value proposition). |
| T2 | **DICOM in/out** — Ingest at least one sequence/series; output structured JSON or HL7-friendly. | **In (done)** / Out later | **AWS or GCP** | DICOM **ingestion** done (`dicom_loader.py`, API). DICOM **output** (SEG/SR) in later phase. |
| T3 | **Patient-level split as default** for any claimed metrics + one external or multi-site validation (even small). | **Policy in docs** / external TBD | **GCP or AWS** | `docs/methodology.md` — claimed metrics when metadata exists; multi-site validation = next when partner data exists. |
| T4 | **API-first** — REST: image in → prediction + optional report draft out. | **Done** | **GCP preferred** | `src/api/main.py`: GET /health, POST /predict, POST /report; DICOM or image. |
| T5 | **Deployment package** — Docker image, env config, minimal docs; deploy to cloud for pilots. | **Done** + **cloud guide** | **GCP + AWS** | Dockerfile + `docs/deploy-cloud.md` (Cloud Run + ECR/App Runner). Run deploy when ready for partner URL. |
| T6 | **Compliance baseline** — BAA-ready architecture, encryption (transit/at rest), audit log retention, RBAC, privacy policy. | **Doc added** | **GCP or AWS** | See `docs/compliance-baseline.md` for technical checklist. Next: map this onto a concrete GCP or AWS deployment. |
| T7 | **Structured report templates** — Report draft from measured/structured outputs (not unconstrained LLM text) when moving toward clinical. | **Done (template path in app)** | — | Deterministic, template-style report built from classification + next steps; LLM narrative remains optional. |

### Phase 2: Evidence and distribution (6–12 months)

| # | To do | Cloud | Notes |
|---|-------|--------|------|
| T8 | **Validation report** — Sensitivity, specificity, PPV, NPV, confusion matrix; patient-level split; state limitations. | **GCP or AWS** | Template: `docs/validation-report-template.md`. **Script:** `scripts/evaluate_test_metrics.py` — test split + confusion matrix + per-class report + JSON (`--out-json docs/validation-metrics-latest.json`). Fill template from output; add patient-level when metadata exists. |
| T9 | **5–10 design partners** — 1–2 deep integration (e.g. academic neuro with IRB+PACS); rest for feedback. Offer “retrospective evaluation pack” (per-patient split, calibration, error analysis by site, clinician feedback). | **GCP or AWS** | Host pilot **API + demo** on Cloud Run or Lambda so partners can hit a stable URL; no on-prem until later. Use credits for traffic and compute. **Other** credits: use for staging or a second region if needed. |
| T10 | **Segmentation (2D) or 3D path** — If positioning beyond triage: volumes, masks, longitudinal (one high-value cohort, e.g. brain mets or glioma follow-up). | **GCP or AWS** | Training: **GCP Vertex AI** or **AWS SageMaker** (or GPU VMs) within credits. Prefer one provider to simplify BAA later. |
| T11 | **LLM grounding or strict templates** — If report draft is core; measure error rates; avoid unconstrained generative text in device claim. | **GCP** | Gemini already on GCP; keep LLM eval and logging in same cloud for compliance and cost. |
| T12 | **Saliency vs mask validation** — When dataset with masks exists; Dice/IoU in `evaluate_saliency_vs_mask.py`. | **GCP or AWS** | Run script on Cloud Run / Lambda or a small VM; store masks in GCS/S3. Credits for compute + storage. |

### Phase 3: Scale and regulation (12–24 months)

| # | To do | Cloud | Notes |
|---|-------|--------|------|
| T13 | **Regulatory strategy** — Choose one initial claim: CADx (POK), CADt (QAS), or segmentation/volumetrics (892.2050); QMS if device. | — | Per intelligence: don’t bundle classifier + report + triage in one first clearance. |
| T14 | **PACS/RIS integration** — One major vendor or standard (DICOM, IHE). | **GCP or AWS** | Integration endpoints and optional DICOM gateway (e.g. GCP Healthcare API or AWS HealthLake / custom) can run on same cloud as API; use credits for dev/staging. |
| T15 | **Pricing and packaging** — Per-site, per-study, or platform; pilot pricing; document ROI. | — | Revenue and sustainability. |

### Ongoing / roadmap (not phase-bound)

| # | To do | Cloud | Notes |
|---|-------|--------|------|
| T16 | **Per-layer/per-feature model optimization** — Configurable dropout/activations; document in `docs/challenges.md`. | **GCP or AWS** | Training runs on Vertex AI / SageMaker or GPU VMs within credits; compare configs without extra spend. |

---

## 10. Current vs minimum sellable (from intelligence)

| Dimension | Current | Minimum sellable (hospital-facing) |
|-----------|---------|------------------------------------|
| **Input** | JPG/PNG upload | DICOM-native ingestion + PACS integration |
| **Output** | Class + probability + LLM narrative | Structured findings; optional segmentation + volumetrics; **structured report templates** from measured outputs |
| **Model** | 2D classification only | 2D triage OK for research; for clinical purchase expect segmentation + volumes (1–2 tumor types) |
| **Report** | Free-form LLM draft (prompt-constrained) | Constrained, grounded, auditable; or templates from segmentation/volumetrics |
| **Evidence** | None; patient split optional | Patient-level split default; validation report; design-partner retrospective pack |
| **Compliance** | Audit log only | BAA-ready, encryption, SOC 2 path, HIPAA alignment |
| **GTM** | Demo only | Design partners (academic neuro, IRB+PACS) → retrospective evaluation pack; no paying clinical until DICOM + clearance path |

---

## Summary

- **Workflows:** Data download → (optional) metadata for patient split → train/val/test load → training (custom CNN, Xception, transfer) → save checkpoints → inference + saliency → Streamlit upload → predictions + explanation + report → export with review.
- **Features (built):** Patient-based split, three classifiers, saliency maps, multimodal LLM (Gemini) with constrained prompts, chat with scan, clinical-style report, model comparison, audit log, human-in-the-loop export, dark mode, Apple-style UI.
- **Planned:** Saliency vs mask validation, per-layer optimization, optional 2D segmentation and LLM grounding, 3D/volumetric and surgical as future scope.
- **To do:** See **§9** for the single ordered list (Phase 1–3 + ongoing) aligned with market, regulatory, and GTM intelligence. **Cloud:** Use **AWS**, **Google Cloud**, and **other** free credits for API (Cloud Run / Lambda), deployment (Docker), validation runs, design-partner pilots, and training—see the **Cloud** column in §9.
