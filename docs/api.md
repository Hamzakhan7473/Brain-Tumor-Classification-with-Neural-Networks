# API / Function Reference

## Data

- `src.data.dataset.get_dataset(config, split)` — Returns a `tf.data.Dataset` or Keras image dataset for train/val/test.
- `src.data.dataset.load_image_for_inference(path, target_size, normalize)` — Load and preprocess a single image for inference.

## Models

- `models.custom_cnn.build_custom_cnn(...)` — Build the custom CNN.
- `models.xception_model.build_xception(...)` — Build Xception with custom head.
- `models.transfer_model.build_transfer_model(...)` — Build second transfer model (e.g. EfficientNetB0).

## Training

- `src.training.train.run_training(model, train_ds, val_ds, config)` — Run training with callbacks; saves best and final weights.

## Inference

- `src.inference.predict.load_model_and_predict(model_name, image_batch, class_names)` — Load saved model and return predictions and probabilities.
- `src.inference.saliency.generate_saliency_map(model, image_batch, class_idx)` — Compute saliency map for interpretability.

## LLM

- `src.llm.client.get_llm_client(provider, model_id)` — Get multimodal LLM client (e.g. Gemini).
- `src.llm.client.generate_with_image(client, image, prompt)` — Generate text from image + prompt.
- `src.llm.explanations.explain_image(image, model_prediction, provider)` — Short explanation of the scan.
- `src.llm.report.build_report(image, prediction, confidence, provider)` — Full report (insights, cases, next steps).

## Evaluation scripts

- `scripts/evaluate_models.py` — Validation accuracy/loss for each saved model (Keras `validation` subset).
- `scripts/evaluate_test_metrics.py` — Stratified **test** split (75/15/10, seed from `configs/data.yaml`), confusion matrix, sklearn `classification_report`, per-model log loss. Optional: `--out-json path.json`.

## REST API (Phase 1 roadmap)

- **Run:** `uvicorn src.api.main:app --host 0.0.0.0 --port 8000` (from project root). Or: `docker build -t brain-tumor-mri-api . && docker run -p 8000:8000 brain-tumor-mri-api`
- **Cloud deploy:** `docs/deploy-cloud.md` (GCP Cloud Run, AWS ECR + App Runner).
- **Endpoints:**
  - `GET /health` — Health check.
  - `POST /predict` — Upload image (JPG/PNG or DICOM); query param `model` = `custom_cnn` \| `xception` \| `transfer`. Returns `{ "label", "confidence", "probabilities", "model", "dicom_meta" }`.
  - `POST /report` — Same as predict plus LLM report draft (requires `GOOGLE_API_KEY`).
- **DICOM:** `src.data.dicom_loader.load_dicom_slice(path_or_bytes, ...)` — Load DICOM, extract one slice, return (1, H, W, 3) array and optional metadata.

## App

- `streamlit run src/app/streamlit_app.py` — Launch the main Streamlit app.
