# Methodology

## Objective

Classify brain MRI scans into tumor categories (e.g. Glioma, Meningioma, No Tumor, Pituitary) using deep learning and provide interpretability and clinical-style reporting via multimodal LLMs.

## Data

- **Source:** Kaggle Brain Tumor Classification (MRI) or equivalent.
- **Splits:** Stratified 75% train, 15% validation, 10% test.
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

- **Saliency maps:** Gradient of the winning class logit w.r.t. input pixels (Simonyan et al.).
- **LLM explanations:** Multimodal model (Gemini 1.5 Flash) describes the scan and relates it to the model prediction in plain language.
- **Report:** Structured output (prediction, insights, analogous cases, next steps) for clinicians and patients.

## Evaluation

- Test set accuracy and per-class metrics (precision, recall, F1).
- Optional: confusion matrix, ROC curves for multi-class.

## Limitations

- Not a replacement for clinical diagnosis; for research and education only.
- Dataset and class balance may not reflect real-world prevalence.
- LLM text is generative and must be reviewed by qualified personnel.
