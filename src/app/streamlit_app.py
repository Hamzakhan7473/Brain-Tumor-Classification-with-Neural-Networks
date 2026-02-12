"""
Main Streamlit app: upload Brain MRI, get predictions from both models, explanations, report, chat.
"""
import streamlit as st

st.set_page_config(page_title="Brain Tumor MRI — Classification & Explainability", page_icon="🧠", layout="wide")

st.title("Brain Tumor MRI — Classification & Explainability")
st.markdown("Upload a Brain MRI scan to get predictions from the Custom CNN and Xception models, plus LLM-generated explanations and reports.")

# Sidebar: LLM selection (Challenge 3)
with st.sidebar:
    st.header("Settings")
    llm_provider = st.selectbox(
        "Multimodal LLM for explanations",
        options=["gemini"],
        format_func=lambda x: "Google Gemini 1.5 Flash" if x == "gemini" else x,
        index=0,
    )

# Main: file upload and prediction
uploaded = st.file_uploader("Upload a Brain MRI scan (e.g. JPEG, PNG)", type=["jpg", "jpeg", "png"])
if uploaded:
    col1, col2 = st.columns(2)
    with col1:
        st.image(uploaded, caption="Uploaded scan", use_container_width=True)
    with col2:
        # Placeholder: load models and run prediction (integrate src.inference.predict)
        st.info("Predictions will appear here after integrating inference and saved models.")
        st.caption("Custom CNN and Xception predictions, plus saliency and LLM explanation.")

# Navigation to sub-pages (Challenge 4: chat, Challenge 5: report, Challenge 6: comparison)
st.sidebar.markdown("---")
st.sidebar.markdown("**Pages**")
st.sidebar.page_link("streamlit_app.py", label="Upload & Predict", icon="📤")
st.sidebar.markdown("- **Model comparison** (Challenge 6): compare multiple CNNs side-by-side")
st.sidebar.markdown("- **Chat with scan** (Challenge 4): converse with the MRI image via LLM")
