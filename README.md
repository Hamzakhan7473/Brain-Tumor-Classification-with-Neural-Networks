# Brain Tumor Classification from MRI Scans: A Deep Learning and Multimodal AI Approach

A research-oriented pipeline for classifying brain MRI scans using convolutional neural networks (CNNs), transfer learning, and multimodal large language models (LLMs) for interpretability and clinical decision support.

---

## Table of Contents

- [Overview](#overview)
- [Theoretical Background](#theoretical-background)
- [Dataset](#dataset)
- [Methodology](#methodology)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Usage](#usage)
- [Challenges & Extensions](#challenges--extensions)
- [References](#references)

---

## Overview

This project implements an end-to-end system for **brain tumor detection and classification** from magnetic resonance imaging (MRI) data. It combines:

1. **Custom CNN** — A hand-designed convolutional architecture for baseline performance (target: ≥98% accuracy).
2. **Xception** — A depthwise separable convolution–based architecture for efficient transfer learning.
3. **Additional transfer learning** — A second pre-trained base model to reach ≥99% accuracy (Challenge 2).
4. **Streamlit web application** — Upload MRI scans, obtain model predictions, and compare models side-by-side.
5. **Multimodal LLM integration** — Explanations and chat over brain MRI images using Gemini 1.5 Flash (and selectable LLMs).
6. **Clinical-style reporting** — Predictions, insights, historical cases, and next steps for patients and clinicians.

---

## Theoretical Background

### What is a Neural Network?

Neural networks are function approximators composed of layers of interconnected units (neurons). Each neuron applies a non-linear transformation to a weighted sum of its inputs. Stacking such layers enables learning of hierarchical representations from raw data (Goodfellow et al., 2016).

**Relevant resources:**
- [3Blue1Brown — Neural Networks](https://www.youtube.com/watch?v=aircAruvnKk)
- [Kaggle — Intro to Deep Learning](https://www.kaggle.com/learn/intro-to-deep-learning)

### How Neural Networks Learn

Learning is formulated as optimization of a loss function (e.g., cross-entropy for classification) with respect to the network parameters. **Backpropagation** computes gradients of the loss with respect to each parameter, and **gradient-based optimizers** (e.g., Adam) update the weights to minimize the loss (Rumelhart et al., 1986).

**Relevant resources:**
- [3Blue1Brown — Backpropagation](https://www.youtube.com/watch?v=Ilg3gGewQ5U)
- [Stanford CS231n — Backpropagation](http://cs231n.stanford.edu/)

### What is a Convolution?

A **convolution** is a linear operation that applies a small learnable filter (kernel) across the input (e.g., an image), producing a feature map. In CNNs, multiple filters are learned to detect edges, textures, and higher-level patterns. **Pooling** (e.g., max-pooling) reduces spatial dimensions and adds translation invariance (LeCun et al., 1998).

**Relevant resources:**
- [Interactive CNN Explainer](https://poloclub.github.io/cnn-explainer/) — Poloclub, Georgia Tech
- [CS231n — Convolutional Neural Networks](http://cs231n.stanford.edu/)

### Transfer Learning

**Transfer learning** reuses representations learned on large-scale datasets (e.g., ImageNet) for a target task with limited data. Typically, the base model’s early layers are frozen or fine-tuned, and a new classification head is trained on the target dataset (Yosinski et al., 2014). This is standard in medical imaging to mitigate overfitting and improve generalization.

**Relevant resources:**
- [What is Transfer Learning?](https://www.tensorflow.org/tutorials/images/transfer_learning) — TensorFlow
- [Tesla — Neural Networks for Self-Driving](https://www.tesla.com/blog/neural-networks-power-autopilot) — Industry application of CNNs

### Saliency and Interpretability

**Saliency maps** highlight image regions that most influence the model’s decision (Simonyan et al., 2014). They support interpretability and can be extended with Grad-CAM and attention visualizations. This project includes a **Saliency Map Implementation** for model explanations.

---

## Dataset

- **Source:** [Kaggle — Brain Tumor Classification (MRI)](https://www.kaggle.com/datasets/sartajbhuvaji/brain-tumor-classification-mri) or equivalent brain MRI classification dataset.
- **Content:** MRI scans labeled by tumor type (e.g., Glioma, Meningioma, No Tumor, Pituitary).
- **Usage:** Images are split into train/validation/test sets; augmentation (rotation, flip, brightness/contrast) is applied for robustness.

Place the dataset under `data/raw/` (or configure paths in `configs/`) and follow the structure expected by the data loaders in `src/data/`.

---

## Methodology

| Component        | Description |
|-----------------|-------------|
| **Data pipeline** | Load, augment, and batch MRI images; normalize to model input format. |
| **Custom CNN**    | Convolutional blocks (Conv2D → BatchNorm → ReLU → MaxPool) + dense head; trained from scratch to achieve ≥98% accuracy. |
| **Xception**      | Pre-trained Xception backbone; frozen or partially fine-tuned; custom classification head for brain tumor classes. |
| **Second TL model** | Another pre-trained architecture (e.g., EfficientNet, ResNet, DenseNet) fine-tuned to reach ≥99% accuracy. |
| **Streamlit app** | Upload MRI → run inference with selected models → show predictions, saliency/explanation, LLM-generated report and chat. |
| **Multimodal LLM** | Gemini 1.5 Flash (default) or user-selected model; generates text explanations and supports image-based chat. |
| **Reporting**      | Combined report: model prediction, confidence, insights, analogous cases, and recommended next steps. |

---

## Project Structure

```
brain_tumor_Cnn/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables (API keys, paths)
├── configs/
│   ├── data.yaml             # Dataset paths, splits, augmentation
│   ├── custom_cnn.yaml       # Custom CNN hyperparameters
│   ├── xception.yaml         # Xception training config
│   └── app.yaml              # Streamlit and LLM settings
├── data/
│   ├── raw/                  # Kaggle dataset (downloaded separately)
│   ├── processed/            # Preprocessed splits and indices
│   └── README.md             # Data description and download instructions
├── models/
│   ├── checkpoints/          # Training checkpoints
│   ├── saved/                # Final .h5 / .keras / .pt for deployment
│   ├── custom_cnn.py         # Custom CNN architecture
│   ├── xception_model.py     # Xception wrapper and head
│   └── transfer_model.py    # Second transfer-learning model
├── notebooks/
│   ├── 01_eda.ipynb          # Exploratory data analysis
│   ├── 02_train_custom_cnn.ipynb
│   ├── 03_train_xception.ipynb
│   ├── 04_train_transfer.ipynb
│   └── 05_saliency_and_analysis.ipynb
├── src/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── dataset.py        # Dataset class and loaders
│   │   └── augmentation.py   # Augmentation pipelines
│   ├── training/
│   │   ├── __init__.py
│   │   ├── train.py          # Training loops
│   │   └── callbacks.py      # Checkpoints, early stopping
│   ├── inference/
│   │   ├── __init__.py
│   │   ├── predict.py        # Single/batch prediction
│   │   └── saliency.py       # Saliency map generation
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py         # Multimodal LLM client (Gemini, etc.)
│   │   ├── explanations.py  # Generate text explanations from image
│   │   └── report.py        # Build comprehensive report
│   └── app/
│       ├── __init__.py
│       ├── streamlit_app.py  # Main Streamlit entry
│       ├── pages/
│       │   ├── upload_and_predict.py
│       │   ├── model_comparison.py   # Side-by-side dashboard (Challenge 6)
│       │   └── chat_with_scan.py     # Chat with MRI image (Challenge 4)
│       └── components/       # Reusable UI components
├── docs/
│   ├── methodology.md        # Detailed methodology
│   ├── api.md                # API / function reference
│   └── challenges.md         # Challenge write-ups and results
└── scripts/
    ├── download_data.sh      # Kaggle CLI download
    ├── train_custom_cnn.py   # CLI training
    ├── train_xception.py
    └── train_transfer.py
```

---

## Setup & Installation

1. **Clone and enter the project:**
   ```bash
   cd brain_tumor_Cnn
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env: set KAGDLE_USERNAME, KAGDLE_KEY, GOOGLE_API_KEY (for Gemini), etc.
   ```

4. **Download the dataset:**
   ```bash
   bash scripts/download_data.sh
   # Or use Kaggle CLI / manual download into data/raw/
   ```

5. **Train models (optional; pre-trained weights can be provided):**
   ```bash
   python scripts/train_custom_cnn.py --config configs/custom_cnn.yaml
   python scripts/train_xception.py --config configs/xception.yaml
   python scripts/train_transfer.py --config configs/transfer.yaml
   ```

### Troubleshooting

- **`ImportError: cannot import name 'runtime_version' from 'google.protobuf'`** — TensorFlow does **not** work with protobuf 4.x. Use protobuf 5.x or 3.20.x and reinstall TensorFlow:
  ```bash
  python scripts/fix_tensorflow_protobuf.py
  ```
  Or manually:
  ```bash
  pip install --upgrade 'protobuf>=5.0,<6'
  pip install --upgrade --force-reinstall tensorflow
  ```
  If that fails, try protobuf 3.20.x: `pip install 'protobuf>=3.20,<4'` then reinstall TensorFlow. Using a fresh virtual environment and `pip install -r requirements.txt` also often resolves it.

- **`numpy.dtype size changed, may indicate binary incompatibility`** — Usually **pandas** (used by Keras) was built against a different numpy. Reinstall numpy and pandas so ABIs match:
  ```bash
  pip install --upgrade --force-reinstall numpy pandas
  python -c "from tensorflow import keras; print('OK')"
  ```
  If it still fails, reinstall TensorFlow as well: `pip install --upgrade --force-reinstall tensorflow`.

- **`Cannot uninstall rich` / `no RECORD file`** — The `rich` package is broken (no RECORD file; often from conda). Run the fix script; it removes the broken install and installs `rich` with `--ignore-installed` so pip does not try to uninstall the broken entry:
  ```bash
  python scripts/fix_rich_manual.py
  python -c "from tensorflow import keras; print('OK')"
  ```
  If training still fails with `ModuleNotFoundError: No module named 'rich'`, run: `python -m pip install --ignore-installed rich` then retry. If the script can't delete the folder (permissions), delete the `rich` folder under site-packages (e.g. `rm -rf .../site-packages/rich` and any `rich-*.dist-info`), then run `python -m pip install --ignore-installed rich`.

---

## Usage

### Training

- **Custom CNN:** `python scripts/train_custom_cnn.py --config configs/custom_cnn.yaml`
- **Xception:** `python scripts/train_xception.py --config configs/xception.yaml`
- **Transfer model:** `python scripts/train_transfer.py --config configs/transfer.yaml`

Training logs and checkpoints are written to `models/checkpoints/`. Final models are saved to `models/saved/`.

### Streamlit Application

```bash
streamlit run src/app/streamlit_app.py
```

From the app you can:

- **Upload a Brain MRI scan** and get predictions from both the custom CNN and Xception (and optionally the second transfer model).
- **Select which multimodal LLM** to use for explanations (Challenge 3).
- **Chat with the MRI image** using the selected LLM (Challenge 4).
- **View a comprehensive report** with prediction, insights, historical cases, and next steps (Challenge 5).
- **Use the comparison dashboard** to compare predictions of multiple CNN models side-by-side (Challenge 6).

---

## Challenges & Extensions

| Challenge | Description | Location / Notes |
|-----------|-------------|------------------|
| **1** | Achieve ≥98% accuracy with a custom CNN | `models/custom_cnn.py`, `configs/custom_cnn.yaml`, tuning and augmentation |
| **2** | Use transfer learning with a different base model and achieve ≥99% accuracy | `models/transfer_model.py`, `configs/transfer.yaml` |
| **3** | Add UI to select which multimodal LLM is used for explanations | `src/app/` and `src/llm/client.py` |
| **4** | Allow the user to chat with the brain MRI image via the multimodal LLM | `src/app/pages/chat_with_scan.py`, `src/llm/client.py` |
| **5** | Generate a report with prediction, insights, historical cases, and next steps | `src/llm/report.py`, report template in app |
| **6** | Add a Streamlit dashboard to compare predictions of multiple CNN models side-by-side | `src/app/pages/model_comparison.py` |

Detailed write-ups and results can be documented in `docs/challenges.md`.

---

## References

1. Goodfellow, I., Bengio, Y., & Courville, A. (2016). *Deep Learning*. MIT Press.
2. LeCun, Y., Bottou, L., Bengio, Y., & Haffner, P. (1998). Gradient-based learning applied to document recognition. *Proceedings of the IEEE*, 86(11), 2278–2324.
3. Rumelhart, D. E., Hinton, G. E., & Williams, R. J. (1986). Learning representations by back-propagating errors. *Nature*, 323, 533–536.
4. Simonyan, K., Vedaldi, A., & Zisserman, A. (2014). Deep inside convolutional networks: Visualising image classification models and saliency maps. *ICLR Workshop*.
5. Yosinski, J., Clune, J., Bengio, Y., & Lipson, H. (2014). How transferable are features in deep neural networks? *NeurIPS*, 3320–3328.
6. Chollet, F. (2017). Xception: Deep learning with depthwise separable convolutions. *CVPR*, 1251–1258.

---

## License

This project is for educational and research purposes. Ensure compliance with the Kaggle dataset license and clinical use regulations when applicable.
