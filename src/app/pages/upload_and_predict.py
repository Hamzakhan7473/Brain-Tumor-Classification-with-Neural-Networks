# Redirect to main Report dashboard (upload lives there)
import streamlit as st

st.set_page_config(page_title="MRI Report", page_icon="🧠", layout="wide")
st.switch_page("streamlit_app.py")
