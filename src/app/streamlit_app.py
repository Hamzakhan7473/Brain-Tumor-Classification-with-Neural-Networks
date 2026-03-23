"""
Main Streamlit app: HealthTech-style MRI report dashboard for doctors.
Upload Brain MRI → structured findings, saliency, similar cases, AI insights, export.
Run from project root: streamlit run src/app/streamlit_app.py

This UI is a **demo/front-end** for the underlying services. In a real clinical
setting, the backend would be exposed via authenticated APIs and integrated into
existing radiology workflows.
"""
import sys
from pathlib import Path
from datetime import datetime
import uuid

# Ensure project root is on path when run as script
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

import streamlit as st
from src.app.utils import load_app_config, get_class_names, project_root
from src.app.components.apple_ui import (
    inject_apple_css,
    hero,
    card_header,
    apple_card_markdown,
    report_topbar,
    report_patient_card,
    findings_card_html,
    recommendations_card_html,
    similar_cases_card_html,
)
from src.app.report_helpers import (
    build_findings_rows,
    recommended_next_steps,
    CLASS_DISPLAY,
)
from src.app.audit import log_event

import numpy as np
from src.inference.predict import predict_from_bytes, load_model, MODEL_INPUT_SIZES
from src.inference.saliency import generate_saliency_map
from src.data.dataset import load_image_from_bytes


def _escape_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else "")


def _build_export_html(
    primary_label: str,
    primary_conf: float,
    findings_rows: list[tuple[str, str, str]],
    steps: list[str],
    ai_content: str,
) -> str:
    """Build a self-contained HTML report for download (print to PDF)."""
    rows_html = "".join(
        f"<tr><td>{l}</td><td>{v}</td><td>{s}</td></tr>" for l, v, s in findings_rows
    )
    steps_html = "".join(f"<li>{_escape_html(s)}</li>" for s in steps)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Brain MRI Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 700px; margin: 2rem auto; padding: 1rem; color: #1e293b; }}
    h1 {{ font-size: 1.5rem; }}
    .meta {{ color: #64748b; font-size: 0.9rem; margin-bottom: 1.5rem; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
    th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
    th {{ font-weight: 600; color: #475569; }}
    .section {{ margin-top: 1.5rem; }}
    .section h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
    ul {{ padding-left: 1.25rem; }}
    .ai-content {{ white-space: pre-wrap; background: #f8fafc; padding: 1rem; border-radius: 8px; margin-top: 0.5rem; }}
  </style>
</head>
<body>
  <h1>Brain MRI — Classification Report</h1>
  <p class="meta">Generated {datetime.now().strftime('%B %d, %Y at %H:%M')}. AI-assisted; not a substitute for clinical judgment.</p>
  <div class="section">
    <h2>Findings</h2>
    <table>
      <thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="section">
    <h2>Recommended next steps</h2>
    <ul>{steps_html}</ul>
  </div>
  <div class="section">
    <h2>AI insights</h2>
    <div class="ai-content">{_escape_html(ai_content or "— Not generated —")}</div>
  </div>
</body>
</html>"""

st.set_page_config(
    page_title="Brain Tumor MRI — Clinical Report",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

app_config = load_app_config()
class_names = get_class_names()
models_for_inference = app_config.get("models_for_inference", ["custom_cnn", "xception", "transfer"])
llm_config = app_config.get("llm", {})
providers = llm_config.get("providers", [{"id": "gemini", "name": "Google Gemini 1.5 Flash", "model_id": "gemini-1.5-flash"}])

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "ai_content" not in st.session_state:
    st.session_state.ai_content = ""
if "report_reviewed" not in st.session_state:
    st.session_state.report_reviewed = False

# ——— Sidebar (dashboard nav + theme) ———
with st.sidebar:
    st.markdown("### 🧠 MRI Report")
    st.markdown("")
    dark_mode = st.toggle("Dark mode", value=st.session_state.dark_mode, help="Easier on the eyes in low light")
    if dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode
    st.markdown("**Navigate**")
    st.markdown("• **Report dashboard** — upload & view report")
    st.markdown("• **Model comparison** — compare CNNs")
    st.markdown("• **Chat with scan** — converse with MRI via LLM")
    st.markdown("---")
    st.markdown("**Settings**")
    provider_options = [p["id"] for p in providers]
    provider_labels = {p["id"]: p["name"] for p in providers}
    llm_provider = st.selectbox(
        "LLM for explanations",
        options=provider_options,
        format_func=lambda x: provider_labels.get(x, x),
        index=0,
        label_visibility="collapsed",
    )
    llm_model_id = next((p.get("model_id") for p in providers if p["id"] == llm_provider), None)

inject_apple_css(dark=st.session_state.dark_mode)

# ——— Landing: no image ———
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0
uploaded = st.file_uploader(
    "Upload a Brain MRI scan (JPEG or PNG)",
    type=["jpg", "jpeg", "png"],
    label_visibility="collapsed",
    key=f"mri_upload_{st.session_state.upload_key}",
)

if not uploaded:
    hero(
        "Brain Tumor MRI",
        "AI-driven classification and explainability for brain MRI. Upload a scan to open the clinical report dashboard.",
        badge="AI-Powered HealthTech",
    )
    st.markdown(
        '<p class="apple-caption" style="text-align:center;">Drag and drop or click to upload a brain MRI image.</p>',
        unsafe_allow_html=True,
    )
    st.stop()

# ——— Report view (image uploaded) ———
image_bytes = uploaded.read()
root = project_root()

# Run inference
results = {}
for model_name in models_for_inference:
    label, conf, probs = predict_from_bytes(model_name, image_bytes, class_names, root)
    if label is not None:
        results[model_name] = {"label": label, "confidence": conf, "probs": probs}

if not results:
    st.info("Train models and save them to `models/saved/` to see the report. See README for training commands.")
    st.stop()

first_model = list(results.keys())[0]
primary_label = results[first_model]["label"]
primary_conf = results[first_model]["confidence"]
probs = results[first_model].get("probs")  # numpy array or None; don't use "or {}" (array truth is ambiguous)

log_event(
    "inference",
    {
        "session_id": st.session_state.session_id,
        "primary_label": primary_label,
        "primary_confidence": primary_conf,
        "models": {
            name: {"label": res["label"], "confidence": res["confidence"]}
            for name, res in results.items()
        },
    },
)

# ——— Dashboard top bar ———
report_topbar(title="MRI Report", show_search=True)
col_export, col_new, _ = st.columns([1, 1, 4])
with col_export:
    pass  # Export is below in Export report section
with col_new:
    if st.button("New scan", help="Upload a different MRI"):
        st.session_state.upload_key = st.session_state.get("upload_key", 0) + 1
        st.rerun()

# ——— Patient / scan context ———
report_patient_card(
    patient_name="Current scan",
    meta=f"Uploaded — {datetime.now().strftime('%b %d, %Y')}",
)

# ——— MRI Findings card (structured, with status pills) ———
findings_rows = build_findings_rows(primary_label, primary_conf, results, class_names)
st.markdown(findings_card_html("MRI findings", findings_rows), unsafe_allow_html=True)

# ——— Two columns: Image + Saliency | Similar cases ———
col_left, col_right = st.columns([1, 1])
with col_left:
    apple_card_markdown('<p style="margin:0; font-size:0.95rem; color:#6e6e73;">Scan</p>')
    st.image(image_bytes, width="stretch")
    # Saliency
    size = MODEL_INPUT_SIZES.get(first_model, (224, 224))
    batch = load_image_from_bytes(image_bytes, target_size=size, normalize=True)
    model = load_model(first_model, root)
    if model is not None:
        try:
            saliency = generate_saliency_map(model, batch)
            card_header("Saliency map")
            st.caption(f"Regions that influenced **{first_model}** prediction.")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 1, figsize=(4, 4))
            ax.imshow(saliency, cmap="jet")
            ax.axis("off")
            fig.patch.set_facecolor("#f5f5f7")
            ax.set_facecolor("#f5f5f7")
            st.pyplot(fig)
            plt.close(fig)
        except Exception as e:
            st.caption(f"Saliency unavailable: {e}")

with col_right:
    # Classification distribution (similar-cases style: how this scan compares)
    if probs is not None and len(probs) == len(class_names):
        import matplotlib.pyplot as plt
        labels_display = [CLASS_DISPLAY.get(c, c) for c in class_names]
        vals = [float(probs[i]) for i in range(len(class_names))]
        fig, ax = plt.subplots(figsize=(5, 3))
        colors = ["#0d9488" if class_names[i] == primary_label else "#cbd5e1" for i in range(len(class_names))]
        ax.barh(labels_display, vals, color=colors)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Probability")
        ax.set_facecolor("#fafbfc")
        fig.patch.set_facecolor("#fafbfc")
        st.pyplot(fig)
        plt.close(fig)
    st.markdown(
        similar_cases_card_html(
            "Classification distribution",
            "<p style='font-size:0.9rem; color:#64748b;'>Model confidence by class. Compare to similar presentations.</p>",
        ),
        unsafe_allow_html=True,
    )

# ——— Recommended next steps ———
steps = recommended_next_steps(primary_label, primary_conf)
st.markdown(recommendations_card_html("Recommended next steps", steps), unsafe_allow_html=True)

# ——— AI explanation & report + Export ———
st.markdown('<div class="apple-divider"></div>', unsafe_allow_html=True)
card_header("AI insights & report")
st.caption(
    "You can generate a structured template report from the model outputs alone, or use an LLM "
    "for a narrative explanation (requires GOOGLE_API_KEY in .env)."
)
col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
with col_btn1:
    gen_template = st.button("Structured template (no LLM)")
with col_btn2:
    gen_expl = st.button("LLM explanation")
with col_btn3:
    gen_report = st.button("LLM full report")

if gen_template:
    from src.app.report_helpers import build_structured_report_markdown

    content = build_structured_report_markdown(primary_label, primary_conf, findings_rows, steps)
    st.session_state.ai_content = content
    st.session_state.report_reviewed = False
    log_event(
        "structured_report",
        {
            "session_id": st.session_state.session_id,
            "primary_label": primary_label,
            "primary_confidence": primary_conf,
        },
    )

if gen_expl:
    try:
        from src.llm.explanations import explain_image
        pred_summary = "; ".join([f"{k}: {v['label']} ({v['confidence']:.0%})" for k, v in results.items()])
        with st.spinner("Generating explanation…"):
            content = explain_image(image_bytes, pred_summary, provider=llm_provider, model_id=llm_model_id) or ""
        st.session_state.ai_content = content
        st.session_state.report_reviewed = False
        log_event(
            "llm_explanation",
            {
                "session_id": st.session_state.session_id,
                "provider": llm_provider,
                "model_id": llm_model_id,
                "primary_label": primary_label,
                "primary_confidence": primary_conf,
            },
        )
    except Exception as e:
        st.error(f"Explanation failed (set GOOGLE_API_KEY in .env): {e}")
if gen_report:
    try:
        from src.llm.report import build_report
        with st.spinner("Generating report…"):
            report = build_report(image_bytes, primary_label, primary_conf, provider=llm_provider, model_id=llm_model_id)
        st.session_state.ai_content = report or ""
        st.session_state.report_reviewed = False
        log_event(
            "llm_report",
            {
                "session_id": st.session_state.session_id,
                "provider": llm_provider,
                "model_id": llm_model_id,
                "primary_label": primary_label,
                "primary_confidence": primary_conf,
            },
        )
    except Exception as e:
        st.error(f"Report failed (set GOOGLE_API_KEY in .env): {e}")

if st.session_state.ai_content:
    st.markdown("---")
    st.markdown(st.session_state.ai_content or "*No response.*")
    st.info(
        "AI content is a draft and must be reviewed by a qualified clinician before it "
        "is treated as part of the clinical record. Descriptions of size or location are not "
        "grounded to segmentation or measurements—only the classifier output is model-derived."
    )
    st.session_state.report_reviewed = st.checkbox(
        "Mark AI-generated content as reviewed by a clinician (enables export)",
        value=st.session_state.report_reviewed,
    )

# ——— Export report (HTML for download / print to PDF) ———
st.markdown("---")
card_header("Export report")
export_html = _build_export_html(
    primary_label=primary_label,
    primary_conf=primary_conf,
    findings_rows=findings_rows,
    steps=steps,
    ai_content=st.session_state.ai_content,
)
did_download = st.download_button(
    label="Download report (HTML)",
    data=export_html,
    file_name=f"brain_mri_report_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
    mime="text/html",
    disabled=not (st.session_state.ai_content and st.session_state.report_reviewed),
)
if did_download:
    log_event(
        "export_report",
        {
            "session_id": st.session_state.session_id,
            "primary_label": primary_label,
            "primary_confidence": primary_conf,
            "has_ai_content": bool(st.session_state.ai_content),
            "report_reviewed": bool(st.session_state.report_reviewed),
        },
    )
st.caption(
    "Export is enabled only after AI content has been generated and explicitly marked as reviewed. "
    "Open the HTML in a browser and use Print → Save as PDF for a PDF copy."
)