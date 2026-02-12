# Challenge 6: Dashboard to compare predictions of multiple CNN models side-by-side
import streamlit as st

st.set_page_config(page_title="Model Comparison", page_icon="📊", layout="wide")
st.title("Model Comparison Dashboard")
st.markdown("Compare predictions from Custom CNN, Xception, and Transfer model side-by-side.")

uploaded = st.file_uploader("Upload one Brain MRI scan", type=["jpg", "jpeg", "png"])
if uploaded:
    cols = st.columns(3)
    model_names = ["Custom CNN", "Xception", "Transfer"]
    for col, name in zip(cols, model_names):
        with col:
            st.subheader(name)
            st.image(uploaded, use_container_width=True)
            st.caption("Prediction and confidence will be loaded from inference pipeline.")
