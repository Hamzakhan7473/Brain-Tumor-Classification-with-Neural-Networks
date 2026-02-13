# Challenge 6: Compare predictions of multiple CNN models side-by-side
import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.utils import get_class_names, project_root
from src.inference.predict import predict_from_bytes, MODEL_INPUT_SIZES, get_model_path

st.set_page_config(page_title="Model Comparison", page_icon="📊", layout="wide")
st.title("Model Comparison Dashboard")
st.markdown("Upload one Brain MRI scan to compare predictions from Custom CNN, Xception, and Transfer model side-by-side.")

class_names = get_class_names()
model_names = ["custom_cnn", "xception", "transfer"]
model_labels = ["Custom CNN", "Xception", "Transfer model"]
root = project_root()

uploaded = st.file_uploader("Upload one Brain MRI scan", type=["jpg", "jpeg", "png"])
if uploaded:
    image_bytes = uploaded.read()
    cols = st.columns(3)
    for col, name, label in zip(cols, model_names, model_labels):
        with col:
            st.subheader(label)
            st.image(image_bytes, use_container_width=True)
            path = get_model_path(name, root)
            if path is None:
                st.caption("Model not found. Train and save first.")
            else:
                pred_label, confidence, probs = predict_from_bytes(name, image_bytes, class_names, root)
                if pred_label is not None:
                    st.success(f"**{pred_label}** ({confidence:.1%})")
                    if probs is not None and len(probs) == len(class_names):
                        st.bar_chart(dict(zip(class_names, probs)))
                else:
                    st.caption("Prediction failed.")
