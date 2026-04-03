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

from src.api.features import FeaturesResponse, build_features_response

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


class PriorAuthCreate(BaseModel):
    patient: Optional[str] = None
    payer: Optional[str] = None
    service_line: Optional[str] = None
    status: str = "draft"  # draft|submitted|pending|approved|denied
    sla_hours_remaining: Optional[int] = None
    notes: Optional[str] = None


class InboxMessageCreate(BaseModel):
    patient: Optional[str] = None
    subject: str
    message: str
    message_type: str = "clinical"  # admin|clinical
    risk: str = "low"  # low|medium|high
    draft_reply: Optional[str] = None


class AgentTraceCreate(BaseModel):
    workflow: str
    status: str = "success"  # success|error
    risk: str = "low"  # low|medium|high
    steps: Optional[list[dict]] = None
    evidence: Optional[list[dict]] = None


class DocsAskBody(BaseModel):
    question: str


class DocsCitation(BaseModel):
    id: str
    title: Optional[str] = None
    source: Optional[str] = None
    snippet: str
    score: Optional[float] = None


class DocsAnswerResponse(BaseModel):
    answer: str
    citations: list[DocsCitation]

class Predict3DResponse(BaseModel):
    label: str
    confidence: float
    probabilities: dict
    model: str

class TrialCreate(BaseModel):
    name: str
    sponsor: Optional[str] = None
    condition: Optional[str] = None
    nct_id: Optional[str] = None
    sites: Optional[list[str]] = None
    inclusion_tags: Optional[list[str]] = None
    exclusion_tags: Optional[list[str]] = None
    status: str = "active"  # active|paused|closed
    notes: Optional[str] = None


class TrialCandidateCreate(BaseModel):
    trial_id: str
    patient_label: Optional[str] = None  # avoid PHI; use a local label like "MRN hash" or "Case 102"
    study_instance_uid: Optional[str] = None
    site_id: Optional[str] = None
    status: str = "screened"  # screened|eligible|ineligible|contacted|consented|enrolled|declined
    reason: Optional[str] = None
    evidence: Optional[list[dict]] = None
    notes: Optional[str] = None


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


@app.get("/features", response_model=FeaturesResponse)
@limiter.limit("120/minute")
def public_features(request: Request):
    """
    Product feature list for marketing UI, merged with live capabilities (models on disk, MongoDB, LLM).
    No API key required so public landing pages can show accurate availability.
    """
    return build_features_response()


@app.get("/models")
def list_models():
    """
    List model names that are available on disk.
    Uses MODEL_DIR (if set) or defaults to models/saved/.
    """
    try:
        from src.inference.predict import list_available_models

        return {"models": list_available_models(_ROOT)}
    except Exception:
        return {"models": []}


@app.post("/docs/ask", response_model=DocsAnswerResponse)
@limiter.limit("60/minute")
async def docs_ask(
    request: Request,
    body: DocsAskBody,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Ask a question over the project's clinical/workflow documentation using RAG.
    Returns an answer plus traceable citations (chunk ids + sources).
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    # Retrieve evidence from MongoDB Atlas Vector Search
    citations: list[DocsCitation] = []
    evidence_blocks: list[str] = []
    try:
        from src.rag.retrieval import retrieve_evidence

        evidence = await retrieve_evidence(question, top_k=int(os.environ.get("RAG_TOP_K", "5")))
        for i, e in enumerate(evidence, start=1):
            text = (e.text or "").strip()
            if len(text) > 900:
                text = text[:900] + "…"
            meta = e.metadata or {}
            source = str(meta.get("source") or meta.get("path") or meta.get("doc_id") or "")
            title = str(meta.get("title") or meta.get("heading") or meta.get("section") or "")
            citations.append(
                DocsCitation(
                    id=str(e.chunk_id),
                    title=title or None,
                    source=source or None,
                    snippet=text,
                    score=e.score,
                )
            )
            evidence_blocks.append(f"[{i}] (chunk_id: {e.chunk_id})\n{text}")
    except Exception:
        citations = []
        evidence_blocks = []

    # Generate a grounded answer if possible (LLM optional)
    evidence_context = "\n\n".join(evidence_blocks).strip()
    if not evidence_context:
        return DocsAnswerResponse(
            answer="No evidence was retrieved for this question yet. Please ingest your docs into the knowledge base and try again.",
            citations=[],
        )

    try:
        from src.llm.client import get_llm_client

        prompt = (
            "You are a clinical workflow assistant. Answer the user's question using ONLY the evidence provided. "
            "Cite sources inline using bracket numbers like [1], [2]. If the evidence does not support a claim, say "
            "'insufficient evidence from retrieved sources'. Keep the answer concise and operational.\n\n"
            f"Question: {question}\n\n"
            f"Evidence:\n{evidence_context}\n"
        )
        client = get_llm_client(provider="gemini")
        resp = client.generate_content(prompt)
        answer_text = (resp.text if resp else "") or ""
        answer_text = answer_text.strip() or "Insufficient evidence from retrieved sources."
    except Exception:
        # Safe fallback: return an evidence-only response
        answer_text = (
            "Retrieved evidence is shown in citations. Configure an LLM key to generate a narrative answer."
        )

    return DocsAnswerResponse(answer=answer_text, citations=citations)


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
    from src.inference.predict import list_available_models

    allowed = set(list_available_models(_ROOT)) or {"custom_cnn", "xception", "transfer"}
    if model not in allowed:
        raise HTTPException(400, detail=f"Unknown model '{model}'. Available: {sorted(allowed)}")
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


@app.get("/models/3d")
def list_models_3d():
    try:
        from src.inference.predict_3d import list_available_models_3d

        return {"models": list_available_models_3d(_ROOT)}
    except Exception:
        return {"models": []}


@app.post("/predict-3d", response_model=Predict3DResponse)
@limiter.limit("30/minute")
async def predict_3d(
    request: Request,
    file: UploadFile = File(...),
    model: str = "cnn_3d_best",
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Upload a NIfTI volume (.nii or .nii.gz) and run a 3D classifier.
    """
    filename = file.filename or "volume.nii.gz"
    if not (filename.lower().endswith(".nii") or filename.lower().endswith(".nii.gz")):
        raise HTTPException(status_code=400, detail="file must be a NIfTI volume (.nii or .nii.gz)")
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(status_code=400, detail="Empty file")

    from src.inference.predict_3d import list_available_models_3d, predict_volume_from_bytes

    allowed = set(list_available_models_3d(_ROOT)) or {"cnn_3d_best", "cnn_3d_final"}
    if model not in allowed:
        raise HTTPException(400, detail=f"Unknown 3D model '{model}'. Available: {sorted(allowed)}")

    classes = _get_class_names()
    shape_raw = (os.environ.get("VOLUME_3D_SHAPE") or "96,96,96").strip()
    try:
        target_shape = tuple(int(x.strip()) for x in shape_raw.split(","))
        if len(target_shape) != 3:
            raise ValueError("bad shape")
    except Exception:
        target_shape = (96, 96, 96)

    label, conf, probs = predict_volume_from_bytes(
        model_name=model,
        volume_bytes=bytes_data,
        filename=filename,
        class_names=classes,
        target_shape=target_shape,
        project_root=_ROOT,
    )
    if label is None:
        raise HTTPException(status_code=503, detail="3D model not available or load failed")

    return Predict3DResponse(label=label, confidence=float(conf), probabilities=probs, model=model)


# ----------------------------
# Clinical trials: minimal tracker APIs (no PHI)
# ----------------------------


@app.get("/trials")
@limiter.limit("120/minute")
async def list_trials_api(
    request: Request,
    limit: int = 50,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import list_trials

    docs = await list_trials(limit=limit)
    out = []
    for d in docs:
        d = dict(d)
        d["id"] = str(d.pop("_id", ""))
        out.append(d)
    return out


@app.post("/trials")
@limiter.limit("120/minute")
async def create_trial_api(
    request: Request,
    body: TrialCreate,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import insert_trial

    inserted_id = await insert_trial(body.model_dump())
    if not inserted_id:
        raise HTTPException(status_code=503, detail="MongoDB not enabled")
    return {"status": "ok", "id": inserted_id}


@app.get("/trials/{trial_id}")
@limiter.limit("120/minute")
async def get_trial_api(
    request: Request,
    trial_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_trial

    d = await get_trial(trial_id)
    if not d:
        raise HTTPException(status_code=404, detail="Trial not found")
    d = dict(d)
    d["id"] = str(d.pop("_id", ""))
    return d


@app.get("/trial-candidates")
@limiter.limit("120/minute")
async def list_trial_candidates_api(
    request: Request,
    limit: int = 50,
    trial_id: Optional[str] = None,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import list_trial_candidates

    docs = await list_trial_candidates(limit=limit, trial_id=trial_id)
    out = []
    for d in docs:
        d = dict(d)
        d["id"] = str(d.pop("_id", ""))
        out.append(d)
    return out


@app.post("/trial-candidates")
@limiter.limit("120/minute")
async def create_trial_candidate_api(
    request: Request,
    body: TrialCandidateCreate,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import insert_trial_candidate

    inserted_id = await insert_trial_candidate(body.model_dump())
    if not inserted_id:
        raise HTTPException(status_code=503, detail="MongoDB not enabled")
    return {"status": "ok", "id": inserted_id}


@app.get("/trial-candidates/{candidate_id}")
@limiter.limit("120/minute")
async def get_trial_candidate_api(
    request: Request,
    candidate_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_trial_candidate

    d = await get_trial_candidate(candidate_id)
    if not d:
        raise HTTPException(status_code=404, detail="Candidate not found")
    d = dict(d)
    d["id"] = str(d.pop("_id", ""))
    return d

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


# ----------------------------
# Product workflow endpoints (Auths / Inbox / Traces)
# ----------------------------


@app.get("/auths")
@limiter.limit("120/minute")
async def list_auths(
    request: Request,
    limit: int = 50,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import list_prior_auths

    docs = await list_prior_auths(limit=limit)
    out = []
    for d in docs:
        d = dict(d)
        d["id"] = str(d.pop("_id", ""))
        out.append(d)
    return out


@app.post("/auths")
@limiter.limit("120/minute")
async def create_auth(
    request: Request,
    body: PriorAuthCreate,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import insert_prior_auth

    inserted_id = await insert_prior_auth(body.model_dump())
    if not inserted_id:
        raise HTTPException(status_code=503, detail="MongoDB not enabled")
    return {"status": "ok", "id": inserted_id}


@app.get("/auths/{auth_id}")
@limiter.limit("120/minute")
async def get_auth(
    request: Request,
    auth_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_prior_auth

    d = await get_prior_auth(auth_id)
    if not d:
        raise HTTPException(status_code=404, detail="Auth not found")
    d = dict(d)
    d["id"] = str(d.pop("_id", ""))
    return d


@app.get("/inbox")
@limiter.limit("120/minute")
async def list_inbox(
    request: Request,
    limit: int = 50,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import list_inbox_messages

    docs = await list_inbox_messages(limit=limit)
    out = []
    for d in docs:
        d = dict(d)
        d["id"] = str(d.pop("_id", ""))
        out.append(d)
    return out


@app.post("/inbox")
@limiter.limit("120/minute")
async def create_inbox(
    request: Request,
    body: InboxMessageCreate,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import insert_inbox_message

    inserted_id = await insert_inbox_message(body.model_dump())
    if not inserted_id:
        raise HTTPException(status_code=503, detail="MongoDB not enabled")
    return {"status": "ok", "id": inserted_id}


@app.get("/inbox/{message_id}")
@limiter.limit("120/minute")
async def get_inbox(
    request: Request,
    message_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_inbox_message

    d = await get_inbox_message(message_id)
    if not d:
        raise HTTPException(status_code=404, detail="Message not found")
    d = dict(d)
    d["id"] = str(d.pop("_id", ""))
    return d


@app.get("/agent-traces")
@limiter.limit("120/minute")
async def list_traces(
    request: Request,
    limit: int = 50,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import list_agent_traces

    docs = await list_agent_traces(limit=limit)
    out = []
    for d in docs:
        d = dict(d)
        d["id"] = str(d.pop("_id", ""))
        out.append(d)
    return out


@app.post("/agent-traces")
@limiter.limit("120/minute")
async def create_trace(
    request: Request,
    body: AgentTraceCreate,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import insert_agent_trace

    inserted_id = await insert_agent_trace(body.model_dump())
    if not inserted_id:
        raise HTTPException(status_code=503, detail="MongoDB not enabled")
    return {"status": "ok", "id": inserted_id}


@app.get("/agent-traces/{trace_id}")
@limiter.limit("120/minute")
async def get_trace(
    request: Request,
    trace_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_agent_trace

    d = await get_agent_trace(trace_id)
    if not d:
        raise HTTPException(status_code=404, detail="Trace not found")
    d = dict(d)
    d["id"] = str(d.pop("_id", ""))
    return d
