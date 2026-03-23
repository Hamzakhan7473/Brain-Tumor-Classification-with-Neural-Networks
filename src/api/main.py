"""
REST API for brain tumor MRI: predict and optional report draft.
Deploy with: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Phase 1 roadmap: API-first for PACS/RIS and cloud deployment (Cloud Run, Lambda).
"""
import sys
from pathlib import Path

# Ensure project root on path when run as module
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Brain Tumor MRI API",
    description="Classification and optional report draft for brain MRI (2D slice). Supports JPG/PNG and DICOM.",
    version="0.1.0",
)


# --- Response models ---
class PredictResponse(BaseModel):
    label: str
    confidence: float
    probabilities: dict
    model: str
    dicom_meta: Optional[dict] = None


class ReportResponse(BaseModel):
    prediction: str
    confidence: float
    report_text: str


# --- Helpers ---
def _get_class_names():
    try:
        import yaml
        cfg = _ROOT / "configs" / "data.yaml"
        if cfg.exists():
            with open(cfg) as f:
                data = yaml.safe_load(f) or {}
                return data.get("classes", ["glioma", "meningioma", "pituitary", "notumor"])
    except Exception:
        pass
    return ["glioma", "meningioma", "pituitary", "notumor"]


def _run_predict(bytes_data: bytes, model_name: str, filename: str, content_type: str):
    """Dispatch to DICOM or image pipeline; return (label, confidence, probs, dicom_meta)."""
    import numpy as np
    from src.inference.predict import load_model_and_predict, MODEL_INPUT_SIZES

    classes = _get_class_names()
    size = MODEL_INPUT_SIZES.get(model_name, (224, 224))
    dicom_meta = None

    is_dicom = (
        filename.lower().endswith(".dcm")
        or filename.lower().endswith(".dicom")
        or (content_type or "").lower() in ("application/dicom", "application/dicom+xml")
    )

    if is_dicom:
        from src.data.dicom_loader import load_dicom_slice
        batch, dicom_meta = load_dicom_slice(bytes_data, target_size=size, normalize=True)
    else:
        from src.data.dataset import load_image_from_bytes
        batch = load_image_from_bytes(bytes_data, target_size=size, normalize=True)

    labels, probs = load_model_and_predict(model_name, batch, classes, _ROOT)
    if labels is None or probs is None:
        return None, None, None, dicom_meta
    idx = int(probs[0].argmax())
    label = labels[0]
    conf = float(probs[0][idx])
    prob_dict = {classes[i]: float(probs[0][i]) for i in range(len(classes))}
    return label, conf, prob_dict, dicom_meta


# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "service": "brain-tumor-mri-api"}


@app.post("/predict", response_model=PredictResponse)
async def predict(
    file: UploadFile = File(...),
    model: str = "custom_cnn",
):
    """
    Upload a brain MRI image (JPG, PNG) or DICOM. Returns predicted class and probabilities.
    """
    allowed = {"custom_cnn", "xception", "transfer"}
    if model not in allowed:
        raise HTTPException(400, detail=f"model must be one of {allowed}")
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(400, detail="Empty file")
    filename = file.filename or "image"
    content_type = file.content_type or ""

    label, conf, probs, dicom_meta = _run_predict(bytes_data, model, filename, content_type)
    if label is None:
        raise HTTPException(503, detail="Model not available or load failed")
    return PredictResponse(
        label=label,
        confidence=conf,
        probabilities=probs,
        model=model,
        dicom_meta=dicom_meta,
    )


def _image_bytes_for_llm(bytes_data: bytes, filename: str, content_type: str) -> bytes:
    """Return image bytes suitable for LLM (PIL-compatible). For DICOM, convert slice to PNG bytes."""
    is_dicom = (
        filename.lower().endswith(".dcm")
        or filename.lower().endswith(".dicom")
        or (content_type or "").lower() in ("application/dicom", "application/dicom+xml")
    )
    if is_dicom:
        from src.data.dicom_loader import load_dicom_slice
        import io
        from PIL import Image
        batch, _ = load_dicom_slice(bytes_data, target_size=(224, 224), normalize=True)
        arr = (batch[0] * 255).clip(0, 255).astype("uint8")
        img = Image.fromarray(arr)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    return bytes_data


@app.post("/report", response_model=ReportResponse)
async def report(
    file: UploadFile = File(...),
    model: str = "custom_cnn",
):
    """
    Same as /predict, plus LLM-generated report draft (requires GOOGLE_API_KEY).
    """
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(400, detail="Empty file")
    filename = file.filename or "image"
    content_type = file.content_type or ""
    label, conf, probs, _ = _run_predict(bytes_data, model, filename, content_type)
    if label is None:
        raise HTTPException(503, detail="Model not available or load failed")

    try:
        from src.llm.report import build_report
        image_for_llm = _image_bytes_for_llm(bytes_data, filename, content_type)
        report_text = build_report(image_for_llm, label, conf, provider="gemini")
        if not report_text:
            report_text = f"Prediction: {label} ({conf:.2%}). No LLM response."
    except Exception as e:
        report_text = f"Prediction: {label} ({conf:.2%}). Report generation failed: {e}"
    return ReportResponse(prediction=label, confidence=conf, report_text=report_text)
