# Model comparison — Apple-style UI
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.utils import get_class_names, project_root
from src.app.components.apple_ui import inject_apple_css, hero, card_header, apple_card_markdown
from src.inference.predict import predict_from_bytes, get_model_path

st.set_page_config(page_title="Model Comparison", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
inject_apple_css()

hero(
    "Model Comparison",
    "Upload one Brain MRI scan to compare predictions from Custom CNN, Xception, and Transfer model side-by-side.",
    badge="Compare models",
)

class_names = get_class_names()
model_names = ["custom_cnn", "xception", "transfer"]
model_labels = ["Custom CNN", "Xception", "Transfer model"]
root = project_root()

uploaded = st.file_uploader("Upload one Brain MRI scan", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
if uploaded:
    image_bytes = uploaded.read()
    cols = st.columns(3)
    for col, name, label in zip(cols, model_names, model_labels):
        with col:
            apple_card_markdown(f"<p style='margin:0 0 0.5rem 0; font-weight:600; color:#1d1d1f;'>{label}</p>")
            st.image(image_bytes, use_container_width=True)
            path = get_model_path(name, root)
            if path is None:
                st.caption("Model not found. Train and save first.")
            else:
                pred_label, confidence, probs = predict_from_bytes(name, image_bytes, class_names, root)
                if pred_label is not None:
                    st.markdown(
                        f'<span class="apple-pill"><strong>{pred_label}</strong> · {confidence:.0%}</span>',
                        unsafe_allow_html=True,
                    )
                    if probs is not None and len(probs) == len(class_names):
                        st.bar_chart(dict(zip(class_names, probs)))
                else:
                    st.caption("Prediction failed.")
else:
    st.markdown(
        '<p class="apple-caption" style="text-align:center;">Upload a brain MRI image to compare all three models.</p>',
        unsafe_allow_html=True,
    )