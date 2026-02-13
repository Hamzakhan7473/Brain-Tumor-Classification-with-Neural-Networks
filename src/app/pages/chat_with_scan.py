# Challenge 4: Chat with the brain MRI image using the multimodal LLM
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.utils import load_app_config, project_root

st.set_page_config(page_title="Chat with Scan", page_icon="💬", layout="wide")
st.title("Chat with Brain MRI Scan")
st.markdown("Upload an MRI image and ask questions about it. The multimodal LLM uses the image as context.")

app_config = load_app_config()
llm_config = app_config.get("llm", {})
providers = llm_config.get("providers", [{"id": "gemini", "name": "Google Gemini 1.5 Flash"}])
provider_options = [p["id"] for p in providers]
provider_labels = {p["id"]: p["name"] for p in providers}

with st.sidebar:
    llm_provider = st.selectbox(
        "LLM",
        options=provider_options,
        format_func=lambda x: provider_labels.get(x, x),
        index=0,
    )

uploaded = st.file_uploader("Upload Brain MRI scan", type=["jpg", "jpeg", "png"])
if uploaded:
    image_bytes = uploaded.read()
    st.image(image_bytes, caption="Your scan", use_container_width=True)

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask something about this scan..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                from src.llm.client import get_llm_client, generate_with_image
                client = get_llm_client(provider=llm_provider)
                reply = generate_with_image(client, image_bytes, prompt)
                st.markdown(reply or "*No response.*")
            except Exception as e:
                st.error(f"LLM error (set GOOGLE_API_KEY in .env): {e}")
                reply = ""
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
else:
    st.info("Upload a Brain MRI image to start the conversation.")
