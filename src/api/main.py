"""
REST API for brain tumor MRI: predict and optional report draft.
Deploy with: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Phase 1 roadmap: API-first for PACS/RIS and cloud deployment (Cloud Run, Lambda).

Optional auth: set API_KEY or API_KEYS (comma-separated) in environment; clients send X-API-Key.
If unset, requests are accepted without a key (development only).
"""
import os
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

from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

app = FastAPI(
    title="Brain Tumor MRI API",
    description="Classification and optional report draft for brain MRI (2D slice). Supports JPG/PNG and DICOM. "
    "Optional partner auth via X-API-Key when API_KEY(s) are set in the environment.",
    version="0.2.0",
)

# CORS for browser-based frontend
allowed_origins = [o.strip() for o in (os.environ.get("CORS_ALLOW_ORIGINS") or "").split(",") if o.strip()]
if not allowed_origins:
    # Dev-friendly default for local Vite/React
    allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _load_api_keys() -> set:
    raw = os.environ.get("API_KEYS") or os.environ.get("API_KEY") or ""
    if not raw.strip():
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(x_api_key: Optional[str] = Security(api_key_header)):
    """Require X-API-Key when API_KEY / API_KEYS is configured; otherwise allow (dev)."""
    keys = _load_api_keys()
    if not keys:
        return None
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Send header X-API-Key.",
        )
    return x_api_key


# --- Response models ---
class PredictResponse(BaseModel):
    label: str
    confidence: float
    probabilities: dict
    model: str
    dicom_meta: Optional[dict] = None
    study_instance_uid: Optional[str] = None
    site_id: Optional[str] = None
    shadow_mode: bool = False


class ReportResponse(BaseModel):
    prediction: str
    confidence: float
    report_text: str
    study_instance_uid: Optional[str] = None
    site_id: Optional[str] = None
    shadow_mode: bool = False


class ClinicalFeedbackBody(BaseModel):
    """Radiologist or researcher feedback on a prior inference (design-partner workflow)."""

    study_instance_uid: str = Field(..., description="Study / case identifier (must match prior request)")
    site_id: Optional[str] = None
    feedback: str = Field(..., description="One of: agree, wrong_class, unclear")
    corrected_class: Optional[str] = Field(
        None,
        description="If feedback is wrong_class, the clinician's preferred class label",
    )
    notes: Optional[str] = None
    model: Optional[str] = None


class CaseSummary(BaseModel):
    study_instance_uid: str
    site_id: Optional[str] = None
    model: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    shadow_mode: bool = False
    timestamp: Optional[str] = None
    feedback_status: str = "pending"
    feedback_timestamp: Optional[str] = None


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


def _log_api_clinical(
    event_type: str,
    study_instance_uid: Optional[str],
    site_id: Optional[str],
    shadow_mode: bool,
    extra: Dict[str, Any],
) -> None:
    raise RuntimeError("legacy _log_api_clinical should not be called anymore")


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


async def _log_api_clinical(
    event_type: str,
    study_instance_uid: Optional[str],
    site_id: Optional[str],
    shadow_mode: bool,
    extra: Dict[str, Any],
) -> None:
    """
    Write inference/report events to JSONL (optional) and MongoDB (optional).
    """
    jsonl_audit_enabled = _env_bool("ENABLE_JSONL_AUDIT", True)
    mongo_enabled = bool((os.environ.get("MONGODB_URI") or "").strip())

    event_payload: Dict[str, Any] = {
        "event_type": event_type,
        "study_instance_uid": study_instance_uid,
        "site_id": site_id,
        "shadow_mode": shadow_mode,
        **extra,
    }

    if jsonl_audit_enabled:
        try:
            from src.app.audit import log_event

            log_event(
                event_type,
                {
                    "study_instance_uid": study_instance_uid,
                    "site_id": site_id,
                    "shadow_mode": shadow_mode,
                    **extra,
                },
            )
        except Exception:
            pass

    if mongo_enabled:
        try:
            from src.db.repositories import insert_inference_event

            await insert_inference_event(event_payload)
        except Exception:
            pass


def _maybe_shadow_store(
    shadow_mode: bool,
    study_instance_uid: Optional[str],
    site_id: Optional[str],
    model: str,
    label: str,
    confidence: float,
    probabilities: dict,
    endpoint: str,
) -> None:
    if not shadow_mode:
        return
    try:
        from src.clinical.shadow_store import append_shadow_result

        if _env_bool("ENABLE_JSONL_SHADOW", True):
            append_shadow_result(
                {
                    "study_instance_uid": study_instance_uid,
                    "site_id": site_id,
                    "model": model,
                    "label": label,
                    "confidence": confidence,
                    "probabilities": probabilities,
                    "endpoint": endpoint,
                    "source": "api",
                }
            )
    except Exception:
        pass


# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "service": "brain-tumor-mri-api", "auth_required": bool(_load_api_keys())}


@app.post("/predict", response_model=PredictResponse)
@limiter.limit("120/minute")
async def predict(
    request: Request,
    file: UploadFile = File(...),
    model: str = "custom_cnn",
    study_instance_uid: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    shadow_mode: bool = Form(False),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Upload a brain MRI image (JPG, PNG) or DICOM. Returns predicted class and probabilities.

    Optional form fields for clinical / partner workflows:
    - study_instance_uid: DICOM StudyInstanceUID or internal case id
    - site_id: hospital or site code
    - shadow_mode: if true, append result to logs/shadow_results.jsonl (research / shadow deployment)
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

    await _log_api_clinical(
        "api_predict",
        study_instance_uid,
        site_id,
        shadow_mode,
        {"model": model, "label": label, "confidence": conf, "probabilities": probs},
    )
    _maybe_shadow_store(shadow_mode, study_instance_uid, site_id, model, label, conf, probs, "/predict")

    return PredictResponse(
        label=label,
        confidence=conf,
        probabilities=probs,
        model=model,
        dicom_meta=dicom_meta,
        study_instance_uid=study_instance_uid,
        site_id=site_id,
        shadow_mode=shadow_mode,
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
@limiter.limit("60/minute")
async def report(
    request: Request,
    file: UploadFile = File(...),
    model: str = "custom_cnn",
    study_instance_uid: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    shadow_mode: bool = Form(False),
    _api_key: Optional[str] = Depends(verify_api_key),
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
        from src.rag.retrieval import retrieve_evidence
        image_for_llm = _image_bytes_for_llm(bytes_data, filename, content_type)

        # Retrieve grounding evidence (MongoDB Atlas Vector Search) before generating the report.
        evidence_context = ""
        try:
            evidence = await retrieve_evidence(
                f"Brain MRI classification context: {label}. Model confidence: {conf:.2%}. "
                "Provide clinical workflow and next steps guidance grounded in retrieved sources.",
                top_k=int(os.environ.get("RAG_TOP_K", "5")),
            )
            # Truncate each chunk to keep prompt size bounded.
            blocks = []
            for i, e in enumerate(evidence, start=1):
                chunk_text = (e.text or "").strip()
                if len(chunk_text) > 900:
                    chunk_text = chunk_text[:900] + "…"
                blocks.append(f"[{i}] (chunk_id: {e.chunk_id})\n{chunk_text}")
            evidence_context = "\n\n".join(blocks)
        except Exception:
            evidence_context = ""

        report_text = build_report(
            image_for_llm,
            label,
            conf,
            provider="gemini",
            evidence_context=evidence_context,
        )
        if not report_text:
            report_text = f"Prediction: {label} ({conf:.2%}). No LLM response."
    except Exception as e:
        report_text = f"Prediction: {label} ({conf:.2%}). Report generation failed: {e}"

    await _log_api_clinical(
        "api_report",
        study_instance_uid,
        site_id,
        shadow_mode,
        {"model": model, "label": label, "confidence": conf, "probabilities": probs},
    )
    _maybe_shadow_store(shadow_mode, study_instance_uid, site_id, model, label, conf, probs, "/report")

    return ReportResponse(
        prediction=label,
        confidence=conf,
        report_text=report_text,
        study_instance_uid=study_instance_uid,
        site_id=site_id,
        shadow_mode=shadow_mode,
    )


@app.post("/clinical/feedback")
@limiter.limit("120/minute")
async def clinical_feedback(
    request: Request,
    body: ClinicalFeedbackBody,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Record clinician feedback for a case (agree / wrong_class / unclear). Appends to logs/clinical_feedback.jsonl.
    """
    fb = body.feedback.lower().strip()
    allowed_fb = {"agree", "wrong_class", "unclear"}
    if fb not in allowed_fb:
        raise HTTPException(400, detail=f"feedback must be one of {allowed_fb}")

    try:
        from src.app.audit import log_event
        from src.clinical.shadow_store import append_clinical_feedback

        log_event(
            "clinical_feedback",
            {
                "study_instance_uid": body.study_instance_uid,
                "site_id": body.site_id,
                "feedback": fb,
                "corrected_class": body.corrected_class,
                "model": body.model,
            },
        )
        if _env_bool("ENABLE_JSONL_CLINICAL_FEEDBACK", True):
            append_clinical_feedback(
                {
                    "study_instance_uid": body.study_instance_uid,
                    "site_id": body.site_id,
                    "feedback": fb,
                    "corrected_class": body.corrected_class,
                    "notes": body.notes,
                    "model": body.model,
                    "source": "api",
                }
            )
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to store feedback: {e}") from e

    # MongoDB persistence (optional)
    try:
        if _env_bool("MONGO_ENABLE", True) and os.environ.get("MONGODB_URI"):
            from src.db.repositories import insert_clinical_feedback

            await insert_clinical_feedback(
                {
                    "study_instance_uid": body.study_instance_uid,
                    "site_id": body.site_id,
                    "feedback": fb,
                    "corrected_class": body.corrected_class,
                    "notes": body.notes,
                    "model": body.model,
                    "source": "api",
                }
            )
    except Exception:
        pass

    return JSONResponse({"status": "ok", "received": True})


@app.get("/cases", response_model=list[CaseSummary])
@limiter.limit("120/minute")
async def list_cases(
    request: Request,
    limit: int = 25,
    site_id: Optional[str] = None,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    List recent cases from MongoDB (if enabled) including latest feedback status per study.
    """
    from src.db.repositories import get_feedback_map_for_studies, get_recent_inference_events

    events = await get_recent_inference_events(limit=limit)
    if site_id:
        events = [e for e in events if (e.get("site_id") or "") == site_id]

    # One row per study UID (latest event only)
    seen = set()
    summaries = []
    for e in events:
        uid = e.get("study_instance_uid")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        summaries.append(e)

    fb_map = await get_feedback_map_for_studies([s.get("study_instance_uid") for s in summaries if s.get("study_instance_uid")])

    out: list[CaseSummary] = []
    for s in summaries:
        uid = s.get("study_instance_uid")
        fb = fb_map.get(uid) if uid else None
        fb_status = (fb.get("feedback") if fb else None) or "pending"
        out.append(
            CaseSummary(
                study_instance_uid=uid,
                site_id=s.get("site_id"),
                model=s.get("model"),
                label=s.get("label"),
                confidence=s.get("confidence"),
                shadow_mode=bool(s.get("shadow_mode")),
                timestamp=s.get("timestamp"),
                feedback_status=fb_status,
                feedback_timestamp=fb.get("timestamp") if fb else None,
            )
        )
    return out


@app.get("/cases/{study_instance_uid}")
@limiter.limit("120/minute")
async def get_case(
    request: Request,
    study_instance_uid: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Get latest inference event + latest feedback for a single study UID.
    """
    from src.db.repositories import get_latest_feedback_for_study, get_latest_inference_for_study

    inf = await get_latest_inference_for_study(study_instance_uid)
    fb = await get_latest_feedback_for_study(study_instance_uid)
    if not inf:
        raise HTTPException(status_code=404, detail="Case not found")

    return {
        "study_instance_uid": study_instance_uid,
        "inference": inf,
        "feedback": fb,
    }


@app.get("/metrics")
@limiter.limit("120/minute")
async def metrics(
    request: Request,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Basic dashboard metrics from MongoDB (if enabled).
    """
    from src.db.repositories import get_basic_metrics

    return await get_basic_metrics()
