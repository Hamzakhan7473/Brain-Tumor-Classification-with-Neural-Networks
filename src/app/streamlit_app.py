"""
Main Streamlit app: upload Brain MRI, get predictions from both models, explanations, report, chat.
Run from project root: streamlit run src/app/streamlit_app.py
"""
import io
from pathlib import Path

import streamlit as st

from .utils import ensure_project_in_path, load_app_config, get_class_names, project_root

ensure_project_in_path()

import numpy as np
from src.inference.predict import predict_from_bytes, load_model, MODEL_INPUT_SIZES
from src.inference.saliency import generate_saliency_map
from src.data.dataset import load_image_from_bytes

st.set_page_config(
    page_title="Brain Tumor MRI — Classification & Explainability",
    page_icon="🧠",
    layout="wide",
)

app_config = load_app_config()
class_names = get_class_names()
models_for_inference = app_config.get("models_for_inference", ["custom_cnn", "xception", "transfer"])
llm_config = app_config.get("llm", {})
providers = llm_config.get("providers", [{"id": "gemini", "name": "Google Gemini 1.5 Flash", "model_id": "gemini-1.5-flash"}])

# Sidebar: LLM selection (Challenge 3)
with st.sidebar:
    st.header("Settings")
    provider_options = [p["id"] for p in providers]
    provider_labels = {p["id"]: p["name"] for p in providers}
    llm_provider = st.selectbox(
        "Multimodal LLM for explanations",
        options=provider_options,
        format_func=lambda x: provider_labels.get(x, x),
        index=0,
    )
    st.markdown("---")
    st.markdown("**Pages**")
    st.markdown("- **Upload & Predict** (current)")
    st.markdown("- **Model comparison**: compare CNNs side-by-side")
    st.markdown("- **Chat with scan**: converse with the MRI via LLM")

st.title("Brain Tumor MRI — Classification & Explainability")
st.markdown("Upload a Brain MRI scan to get predictions from the Custom CNN and Xception models, plus optional LLM explanations and reports.")

uploaded = st.file_uploader("Upload a Brain MRI scan (JPEG or PNG)", type=["jpg", "jpeg", "png"])
if uploaded:
    image_bytes = uploaded.read()
    root = project_root()

    col_img, col_pred = st.columns([1, 1])
    with col_img:
        st.image(image_bytes, caption="Uploaded scan", use_container_width=True)

    with col_pred:
        st.subheader("Predictions")
        results = {}
        for model_name in models_for_inference:
            label, conf, probs = predict_from_bytes(model_name, image_bytes, class_names, root)
            if label is not None:
                results[model_name] = {"label": label, "confidence": conf, "probs": probs}
                st.success(f"**{model_name.replace('_', ' ').title()}**: {label} ({conf:.1%})")
            else:
                st.caption(f"*{model_name}*: model not found (train and save first).")

    if not results:
        st.info("Train models and save them to `models/saved/` to see predictions. See README for training commands.")
    else:
        # Saliency for first available model
        first_model = list(results.keys())[0]
        size = MODEL_INPUT_SIZES.get(first_model, (224, 224))
        batch = load_image_from_bytes(image_bytes, target_size=size, normalize=True)
        model = load_model(first_model, root)
        if model is not None:
            try:
                saliency = generate_saliency_map(model, batch)
                st.subheader("Saliency map")
                st.caption(f"Regions that most influenced the **{first_model}** prediction.")
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(1, 1, figsize=(5, 5))
                ax.imshow(saliency, cmap="jet")
                ax.axis("off")
                st.pyplot(fig)
                plt.close(fig)
            except Exception as e:
                st.caption(f"Saliency could not be generated: {e}")

        # LLM explanation and report (Challenge 5)
        st.markdown("---")
        st.subheader("LLM explanation & report")
        if st.button("Generate explanation (Gemini)"):
            try:
                from src.llm.explanations import explain_image
                from src.llm.client import get_llm_client, generate_with_image

                pred_summary = "; ".join([f"{k}: {v['label']} ({v['confidence']:.0%})" for k, v in results.items()])
                explanation = explain_image(image_bytes, pred_summary, provider=llm_provider)
                st.markdown(explanation or "*No response.*")
            except Exception as e:
                st.error(f"Explanation failed (set GOOGLE_API_KEY in .env): {e}")

        if st.button("Generate full report (prediction, insights, next steps)"):
            try:
                from src.llm.report import build_report

                pred_label = results[first_model]["label"]
                pred_conf = results[first_model]["confidence"]
                report = build_report(image_bytes, pred_label, pred_conf, provider=llm_provider)
                st.markdown(report or "*No response.*")
            except Exception as e:
                st.error(f"Report failed (set GOOGLE_API_KEY in .env): {e}")
