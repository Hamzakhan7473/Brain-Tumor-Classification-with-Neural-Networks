# Chat with scan — Apple-style UI
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.utils import load_app_config
from src.app.components.apple_ui import inject_apple_css, hero, apple_card_markdown

st.set_page_config(page_title="Chat with Scan", page_icon="💬", layout="wide", initial_sidebar_state="expanded")
inject_apple_css()

hero(
    "Chat with Brain MRI Scan",
    "Upload an MRI image and ask questions about it. The AI uses the image as context.",
    badge="AI assistant",
)

app_config = load_app_config()
llm_config = app_config.get("llm", {})
providers = llm_config.get("providers", [{"id": "gemini", "name": "Google Gemini 1.5 Flash"}])
provider_options = [p["id"] for p in providers]
provider_labels = {p["id"]: p["name"] for p in providers}

with st.sidebar:
    st.markdown("### LLM")
    llm_provider = st.selectbox(
        "Model",
        options=provider_options,
        format_func=lambda x: provider_labels.get(x, x),
        index=0,
        label_visibility="collapsed",
    )
    llm_model_id = next((p.get("model_id") for p in providers if p["id"] == llm_provider), None)

uploaded = st.file_uploader("Upload Brain MRI scan", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
if uploaded:
    image_bytes = uploaded.read()
    col_img, col_chat = st.columns([1, 2])
    with col_img:
        apple_card_markdown('<p style="margin:0; font-size:0.95rem; color:#6e6e73;">Your scan</p>')
        st.image(image_bytes, use_container_width=True)

    with col_chat:
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask something about this scan…"):
            reply = ""
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                try:
                    from src.llm.client import get_llm_client, generate_with_image
                    with st.spinner("Thinking…"):
                        client = get_llm_client(provider=llm_provider, model_id=llm_model_id)
                        reply = generate_with_image(client, image_bytes, prompt)
                    st.markdown(reply or "*No response.*")
                except Exception as e:
                    st.error(f"LLM error (set GOOGLE_API_KEY in .env): {e}")
                    reply = str(e)
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
else:
    st.markdown(
        '<p class="apple-caption" style="text-align:center;">Upload a Brain MRI image to start the conversation.</p>',
        unsafe_allow_html=True,
    )
