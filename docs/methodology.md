# Methodology

## Objective

Classify brain MRI scans into tumor categories (e.g. Glioma, Meningioma, No Tumor, Pituitary) using deep learning and provide interpretability and clinical-style reporting via multimodal LLMs.

## Data

- **Source:** Kaggle Brain Tumor Classification (MRI) or equivalent (single 2D slices as JPG/PNG).
- **Splits:** Stratified 75% train, 15% validation, 10% test. **Patient-level split:** When `splits.patient_split` is true and `splits.metadata_file` (CSV with `filename`, `patient_id`) is provided, train/val/test are split by patient ID so the same patient never appears in more than one split—recommended to avoid inflated accuracy from anatomy memorization.
- **Preprocessing:** Resize to model input size (224 or 299), normalize (e.g. [0,1] or ImageNet stats).
- **Augmentation (training only):** Horizontal flip, small rotation, zoom, brightness/contrast to improve generalization.

## Models

1. **Custom CNN:** Several convolutional blocks (Conv2D → BatchNorm → ReLU → MaxPool → Dropout) followed by global pooling and dense layers. Trained from scratch; target ≥98% accuracy (Challenge 1).
2. **Xception:** Pre-trained on ImageNet; replace head with a small dense classifier; optionally unfreeze last N layers and fine-tune.
3. **Second transfer model:** e.g. EfficientNetB0 or ResNet50, same protocol; target ≥99% accuracy (Challenge 2).

## Training

- Loss: categorical cross-entropy.
- Optimizer: Adam (or AdamW for transfer).
- Callbacks: ModelCheckpoint (best val accuracy), EarlyStopping, ReduceLROnPlateau.
- Metrics: accuracy, loss on validation set.

## Interpretability

- **Saliency maps:** Gradient of the winning class logit w.r.t. input pixels (Simonyan et al.). Used for UI explainability only; not validated against ground-truth segmentations or radiologist ROIs.
- **LLM explanations:** Multimodal model (Gemini 1.5 Flash) describes the scan and relates it to the model prediction in plain language. Prompts constrain the LLM from stating size or precise location; descriptions are not grounded to a segmentation mask.
- **Report:** Structured output (prediction, insights, analogous cases, next steps) for clinicians and patients.

## Evaluation

- Test set accuracy and per-class metrics (precision, recall, F1).
- Optional: confusion matrix, ROC curves for multi-class.

## Architecture & Governance

- **Service-first design:** The core of the system (data loading, training, inference, LLM calls, audit logging) is implemented as importable Python modules and scripts. The current Streamlit app is a **demo UI** sitting on top of these services; in a production setting they would be exposed via authenticated APIs and integrated into existing RIS/PACS or EMR workflows.
- **Audit trail:** Key events such as model inference, LLM explanation/report generation, and report export are logged as structured JSONL audit records (`logs/audit.log.jsonl`) including timestamps, session identifiers, model versions, and review flags.
- **Human-in-the-loop:** LLM-generated content is treated as a draft. The UI requires an explicit clinician review confirmation before any report can be exported, and the exported report is clearly marked as *AI-assisted, not a substitute for clinical judgment*.

## Limitations

- Not a replacement for clinical diagnosis; for research and education only.
- **Architecture:** 2D slice-level classifier on single images (JPG/PNG). No 3D pipeline, DICOM, volumetric measures, or midline shift.
- **Data leakage:** When patient-level split is not used, metrics can be optimistic (same patient in train and test). Use `patient_split` + metadata when available.
- **LLM grounding:** Report text is not grounded to segmentation or measurements; only the classifier label and confidence are model-derived. Size/location in text are descriptive only.
- **Interpretability:** Saliency maps are for UI explainability; they are not validated against ground truth.
- **Surgical utility:** Output is class and probability only. No spatial coordinates, vascular proximity, or surgical-planning outputs.
- Dataset and class balance may not reflect real-world prevalence.
- LLM text is generative and must be reviewed by qualified personnel.
