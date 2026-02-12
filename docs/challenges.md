# Challenges — Write-ups and Results

Use this document to record your approach and results for each challenge.

## Challenge 1: ≥98% accuracy with custom CNN

- **Approach:** (e.g. architecture depth, regularization, augmentation.)
- **Best config:** (reference `configs/custom_cnn.yaml`.)
- **Result:** Test accuracy ____%, validation ____%.

## Challenge 2: Transfer learning, ≥99% accuracy

- **Base model:** (e.g. EfficientNetB0.)
- **Approach:** (freeze/unfreeze, LR, epochs.)
- **Result:** Test accuracy ____%, validation ____%.

## Challenge 3: UI to select multimodal LLM

- **Implementation:** Dropdown in Streamlit sidebar; config in `configs/app.yaml`.
- **Providers supported:** Gemini (add OpenAI/Anthropic as needed).

## Challenge 4: Chat with the MRI image

- **Implementation:** `src/app/pages/chat_with_scan.py`; session state for message history; LLM receives image + user message.

## Challenge 5: Comprehensive report

- **Sections:** Prediction summary, additional insights, historical cases, next steps.
- **Implementation:** `src/llm/report.py` and prompt in `build_report()`.

## Challenge 6: Model comparison dashboard

- **Implementation:** `src/app/pages/model_comparison.py`; one upload, display predictions from Custom CNN, Xception, and Transfer model side-by-side.
