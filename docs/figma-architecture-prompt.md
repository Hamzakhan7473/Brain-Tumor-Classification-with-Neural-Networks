# Figma Architecture Diagram Prompt

Copy the prompt below into Figma (e.g. AI design or diagram generation) to create an architecture diagram for the backend, model training, and problem statement.

---

## Prompt (copy-paste)

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
