"""
Main Streamlit app: upload Brain MRI, get predictions, saliency, LLM explanation & report.
Ondex-inspired HealthTech UI. Run from project root: streamlit run src/app/streamlit_app.py
"""
import sys
from pathlib import Path

# Ensure project root is on path when run as script (e.g. streamlit run src/app/streamlit_app.py)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from src.app.utils import load_app_config, get_class_names, project_root
from src.app.components.apple_ui import inject_apple_css, hero, card_header, apple_card_markdown

import numpy as np
from src.inference.predict import predict_from_bytes, load_model, MODEL_INPUT_SIZES
from src.inference.saliency import generate_saliency_map
from src.data.dataset import load_image_from_bytes

st.set_page_config(
    page_title="Brain Tumor MRI — Classification & Explainability",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_apple_css()

app_config = load_app_config()
class_names = get_class_names()
models_for_inference = app_config.get("models_for_inference", ["custom_cnn", "xception", "transfer"])
llm_config = app_config.get("llm", {})
providers = llm_config.get("providers", [{"id": "gemini", "name": "Google Gemini 1.5 Flash", "model_id": "gemini-1.5-flash"}])

# ——— Sidebar ———
with st.sidebar:
    st.markdown("### Settings")
    st.markdown("")
    provider_options = [p["id"] for p in providers]
    provider_labels = {p["id"]: p["name"] for p in providers}
    llm_provider = st.selectbox(
        "Multimodal LLM for explanations",
        options=provider_options,
        format_func=lambda x: provider_labels.get(x, x),
        index=0,
        label_visibility="collapsed",
    )
    llm_model_id = next((p.get("model_id") for p in providers if p["id"] == llm_provider), None)
    st.markdown("---")
    st.markdown("**Navigate**")
    st.markdown("• **Upload & Predict** — current")
    st.markdown("• **Model comparison** — compare CNNs side-by-side")
    st.markdown("• **Chat with scan** — converse with the MRI via LLM")

# ——— Hero (Ondex-style) ———
hero(
    "Brain Tumor MRI",
    "AI-driven classification and explainability for brain MRI scans. Upload a scan for instant predictions and clinical-style reports.",
    badge="AI-Powered HealthTech",
)

# ——— Upload ———
uploaded = st.file_uploader(
    "Upload a Brain MRI scan (JPEG or PNG)",
    type=["jpg", "jpeg", "png"],
    label_visibility="collapsed",
)
if uploaded:
    image_bytes = uploaded.read()
    root = project_root()

    # ——— Two columns: Image | Predictions ———
    col_img, col_pred = st.columns([1, 1])
    with col_img:
        apple_card_markdown('<p style="margin:0; font-size:0.95rem; color:#6e6e73;">Your scan</p>')
        st.image(image_bytes, use_container_width=True)

    with col_pred:
        card_header("Predictions")
        results = {}
        for model_name in models_for_inference:
            label, conf, probs = predict_from_bytes(model_name, image_bytes, class_names, root)
            if label is not None:
                results[model_name] = {"label": label, "confidence": conf, "probs": probs}
                display_name = model_name.replace("_", " ").title()
                st.markdown(
                    f'<span class="apple-pill"><strong>{display_name}</strong> · {label} ({conf:.0%})</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption(f"{model_name}: model not found (train and save first).")

    if not results:
        st.info("Train models and save them to `models/saved/` to see predictions. See README for training commands.")
    else:
        # ——— Saliency (full width below) ———
        first_model = list(results.keys())[0]
        size = MODEL_INPUT_SIZES.get(first_model, (224, 224))
        batch = load_image_from_bytes(image_bytes, target_size=size, normalize=True)
        model = load_model(first_model, root)
        if model is not None:
            try:
                saliency = generate_saliency_map(model, batch)
                card_header("Saliency map")
                st.caption(f"Regions that most influenced the **{first_model}** prediction.")
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(1, 1, figsize=(5, 5))
                ax.imshow(saliency, cmap="jet")
                ax.axis("off")
                fig.patch.set_facecolor("#f5f5f7")
                ax.set_facecolor("#f5f5f7")
                st.pyplot(fig)
                plt.close(fig)
            except Exception as e:
                st.caption(f"Saliency could not be generated: {e}")

        # ——— LLM explanation & report ———
        st.markdown('<div class="apple-divider"></div>', unsafe_allow_html=True)
        card_header("AI explanation & report")
        st.caption("Uses the selected LLM to explain the scan and generate a short report. Requires GOOGLE_API_KEY.")
        col_btn1, col_btn2, _ = st.columns([1, 1, 2])
        with col_btn1:
            gen_expl = st.button("Generate explanation")
        with col_btn2:
            gen_report = st.button("Generate full report")

        if gen_expl:
            try:
                from src.llm.explanations import explain_image
                pred_summary = "; ".join([f"{k}: {v['label']} ({v['confidence']:.0%})" for k, v in results.items()])
                with st.spinner("Generating explanation…"):
                    explanation = explain_image(image_bytes, pred_summary, provider=llm_provider, model_id=llm_model_id)
                st.markdown("---")
                st.markdown(explanation or "*No response.*")
            except Exception as e:
                st.error(f"Explanation failed (set GOOGLE_API_KEY in .env): {e}")
        if gen_report:
            try:
                from src.llm.report import build_report
                pred_label = results[first_model]["label"]
                pred_conf = results[first_model]["confidence"]
                with st.spinner("Generating report…"):
                    report = build_report(image_bytes, pred_label, pred_conf, provider=llm_provider, model_id=llm_model_id)
                st.markdown("---")
                st.markdown(report or "*No response.*")
            except Exception as e:
                st.error(f"Report failed (set GOOGLE_API_KEY in .env): {e}")
else:
    st.markdown(
        '<p class="apple-caption" style="text-align:center;">Drag and drop or click to upload a brain MRI image.</p>',
        unsafe_allow_html=True,
    )