# Challenge 4: Chat with the brain MRI image using the multimodal LLM
import streamlit as st

st.set_page_config(page_title="Chat with Scan", page_icon="💬", layout="wide")
st.title("Chat with Brain MRI Scan")
st.markdown("Upload an MRI image and ask questions about it. The multimodal LLM will use the image as context.")

uploaded = st.file_uploader("Upload Brain MRI scan", type=["jpg", "jpeg", "png"])
if uploaded:
    st.image(uploaded, caption="Your scan", use_container_width=True)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Ask something about this scan..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        # Call LLM with image + prompt (integrate src.llm.client)
        with st.chat_message("assistant"):
            reply = "*(Integrate get_llm_client and generate_with_image with the uploaded image and prompt here.)*"
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
