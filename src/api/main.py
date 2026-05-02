"""REST API for brain tumor MRI: predict and optional report draft.
Deploy with: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Phase 1 roadmap: API-first for PACS/RIS and cloud deployment (Cloud Run, Lambda).

Optional auth: set API_KEY, APP_API_KEY, or API_KEYS (comma-separated); clients send X-API-Key.
If unset, requests are accepted without a key (development only).
"""
import json
import os
import sys
import time
from contextlib import asynccontextmanager
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

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.features import FeaturesResponse, build_features_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load every Keras checkpoint once at startup (TensorFlow only)."""
    from src.inference.model_registry import registry

    print("=" * 60)
    print("NeuroSight API starting…")
    registry.load_all()
    if not getattr(registry, "models", {}):
        print("ERROR: No models loaded!")
        raise RuntimeError("No models loaded — check models/saved/")
    print(f"Loaded {len(registry.models)} model(s):")
    for name in sorted(registry.models.keys()):
        cfg = registry.configs[name]
        ish = cfg.get("input_shape")
        task = cfg.get("task", "classification")
        print(f"  - {name}: input {ish}, task {task}")
    print("API ready at http://127.0.0.1:8000")
    print("=" * 60)
    yield


app = FastAPI(
    title="Brain Tumor MRI API",
    description="Classification and optional report draft for brain MRI (2D slice). Supports JPG/PNG and DICOM. "
    "Optional partner auth via X-API-Key when API_KEY(s) are set in the environment.",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS for browser-based frontend
allowed_origins = [o.strip() for o in (os.environ.get("CORS_ALLOW_ORIGINS") or "").split(",") if o.strip()]
if not allowed_origins:
    # Dev-friendly default for local Vite/React and `vite preview`
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
frontend_url = (os.environ.get("FRONTEND_URL") or "").strip()
if frontend_url and frontend_url not in allowed_origins:
    allowed_origins.append(frontend_url)

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
    raw = os.environ.get("API_KEYS") or os.environ.get("API_KEY") or os.environ.get("APP_API_KEY") or ""
    if not raw.strip():
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(x_api_key: Optional[str] = Security(api_key_header)):
    """Require X-API-Key when API_KEY / API_KEYS is configured; otherwise allow (dev)."""
    keys = _load_api_keys()
    if not keys:
        return None
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send header X-API-Key.",
        )
    if x_api_key not in keys:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key.",
        )
    return x_api_key


# --- Response models ---
class PredictResponse(BaseModel):
    label: str
    confidence: float
    probabilities: dict
    model: str
    prediction: str = Field(..., description="Same as label (alias for newer clients)")
    class_probabilities: dict = Field(..., description="Same as probabilities")
    dicom_meta: Optional[dict] = None
    study_instance_uid: Optional[str] = None
    site_id: Optional[str] = None
    shadow_mode: bool = False
    # Optional enrichment for clients (backward compatible)
    model_version: Optional[str] = Field(None, description="API or deployment bundle version")
    input_shape: Optional[list[int]] = Field(None, description="Batch tensor shape e.g. [1,H,W,C]")
    preprocessing_applied: Optional[list[str]] = Field(None, description="Ordered preprocessing steps")
    saliency_url: Optional[str] = Field(None, description="Optional saliency map URL when available")
    saliency_map_b64: Optional[str] = Field(None, description="Optional Grad-CAM PNG as base64")
    inference_time_s: Optional[float] = Field(None, description="Wall time for this request (seconds)")
    # Defense-in-depth / radiologist workflow (optional for older clients)
    warnings: list[str] = Field(default_factory=list)
    disposition: Optional[str] = None
    display_prediction: Optional[str] = None
    radiologist_action_required: Optional[str] = None
    uncertainty: Optional[dict] = None
    validation: Optional[dict] = None
    clinical_context: Optional[dict] = None
    audit_id: Optional[str] = None
    audit_timestamp: Optional[str] = None


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
    """WMH segmentation (and future 3D tasks). Maps ``run_predict_3d`` output."""

    label: str
    prediction: Optional[str] = None
    confidence: float
    probabilities: dict
    model: str
    task: Optional[str] = None
    wmh: Optional[dict] = None
    inference_time_s: Optional[float] = None
    saliency_map_b64: Optional[str] = None
    input_shape: Optional[list[int]] = Field(None)
    risk_level: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    uncertainty: Optional[dict] = None
    validation: Optional[dict] = None
    clinical_context: Optional[dict] = None
    audit_id: Optional[str] = None
    audit_timestamp: Optional[str] = None


class ReportSignBody(BaseModel):
    audit_id: str = Field(..., min_length=8, description="Correlation id returned by inference")
    agreed: bool
    override: Optional[str] = Field(None, description="Corrected narrative when agreed is false")
    radiologist_id: Optional[str] = None


class ReportDeferBody(BaseModel):
    audit_id: str = Field(..., min_length=8)
    reason: str = Field(..., min_length=1)


class FindingsDisagreeBody(BaseModel):
    """Capture radiologist override / disagreement for model improvement datasets."""

    audit_id: str
    notes: str = Field(..., min_length=1)
    radiologist_id: Optional[str] = None

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


def _parse_optional_context_form(raw: Optional[str]) -> Dict[str, Any]:
    if raw is None or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_context_json", "message": str(exc)},
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_context_json", "message": "context must be a JSON object"},
        )
    return parsed


def _run_predict(bytes_data: bytes, model_name: str, filename: str, content_type: str):
    """Keras classification only; returns legacy 6-tuple for /report helpers."""
    from src.inference.inference_exceptions import InputValidationFailed
    from src.inference.predict import predict_legacy_tuple

    try:
        return predict_legacy_tuple(bytes_data, filename, model_name, content_type)
    except InputValidationFailed:
        raise
    except ValueError as e:
        raise ValueError(str(e)) from e


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
    """All checkpoints loaded into the Keras inference registry (2D + 3D)."""
    from src.inference.model_registry import registry

    return registry.list_models()


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
    model: str = Form("custom_cnn"),
    model_name: Optional[str] = Query(None, description="Alias for model (query param; overrides form model)"),
    study_instance_uid: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    shadow_mode: bool = Form(False),
    context: Optional[str] = Form(None, description="JSON clinical context (age, sex, indication, …)"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Upload a brain MRI image (JPG, PNG) or DICOM. Returns predicted class and probabilities.

    Optional form fields for clinical / partner workflows:
    - study_instance_uid: DICOM StudyInstanceUID or internal case id
    - site_id: hospital or site code
    - shadow_mode: if true, append result to logs/shadow_results.jsonl (research / shadow deployment)
    """
    from src.inference.audit_log import log_inference
    from src.inference.inference_exceptions import InputValidationFailed
    from src.inference.predict import list_available_models, run_predict_2d

    effective_model = (model_name or model).strip() or "custom_cnn"
    allowed = set(list_available_models(_ROOT)) or {"custom_cnn", "xception", "transfer"}
    if effective_model not in allowed:
        raise HTTPException(400, detail=f"Unknown model '{effective_model}'. Available: {sorted(allowed)}")
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(400, detail="Empty file")
    filename = file.filename or "image"
    content_type = file.content_type or ""
    ctx = _parse_optional_context_form(context)

    try:
        out = run_predict_2d(bytes_data, filename, effective_model, content_type, clinical_context=ctx)
    except InputValidationFailed as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    probs = dict(out["class_probabilities"])
    disp = out.get("disposition") or "predicted"
    if disp == "indeterminate":
        lbl = "indeterminate"
    else:
        lbl = str(
            out["display_prediction"] if out.get("display_prediction") is not None else out["prediction"]
        )
    cf = float(out["confidence"])
    pred_argmax = str(out["prediction"])

    await _log_api_clinical(
        "api_predict",
        study_instance_uid,
        site_id,
        shadow_mode,
        {
            "model": effective_model,
            "label": pred_argmax,
            "display_label": lbl,
            "disposition": disp,
            "confidence": cf,
            "probabilities": probs,
        },
    )
    _maybe_shadow_store(
        shadow_mode, study_instance_uid, site_id, effective_model, pred_argmax, cf, probs, "/predict"
    )

    api_ver = (os.environ.get("API_MODEL_VERSION") or "").strip() or app.version

    audit_payload = {
        "label": lbl,
        "confidence": cf,
        "probabilities": probs,
        "disposition": disp,
        "warnings": out.get("warnings") or [],
        "uncertainty": out.get("uncertainty"),
        "validation": out.get("validation"),
    }
    audit_id, audit_ts = log_inference(
        bytes_data,
        filename,
        effective_model,
        api_ver,
        ctx,
        {"endpoint": "/predict", "study_instance_uid": study_instance_uid, "site_id": site_id},
        audit_payload,
        x_user_id,
    )

    return PredictResponse(
        label=lbl,
        prediction=lbl,
        confidence=cf,
        probabilities=probs,
        class_probabilities=probs,
        model=effective_model,
        dicom_meta=out.get("dicom_meta"),
        study_instance_uid=study_instance_uid,
        site_id=site_id,
        shadow_mode=shadow_mode,
        model_version=api_ver,
        input_shape=out.get("input_shape"),
        preprocessing_applied=out.get("preprocessing_applied"),
        saliency_url=None,
        saliency_map_b64=out.get("saliency_map_b64"),
        inference_time_s=out.get("inference_time_s"),
        warnings=list(out.get("warnings") or []),
        disposition=disp,
        display_prediction=out.get("display_prediction"),
        radiologist_action_required=out.get("radiologist_action_required"),
        uncertainty=out.get("uncertainty"),
        validation=out.get("validation"),
        clinical_context=ctx or None,
        audit_id=audit_id,
        audit_timestamp=audit_ts,
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
    model: str = Form("unet_3d_wmh"),
    model_name: Optional[str] = Query(None, description="Overrides form `model` when set."),
    context: Optional[str] = Form(None, description="JSON object; patient age is required for WMH grading"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Upload NIfTI (.nii / .nii.gz): **WMH U-Net** segmentation (Keras registry).
    """
    effective = (model_name or model).strip() or "unet_3d_wmh"

    filename = file.filename or "volume.nii.gz"
    if not (filename.lower().endswith(".nii") or filename.lower().endswith(".nii.gz")):
        raise HTTPException(status_code=400, detail="file must be a NIfTI volume (.nii or .nii.gz)")
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(status_code=400, detail="Empty file")

    from src.inference.audit_log import log_inference
    from src.inference.inference_exceptions import ClinicalContextRequired, InputValidationFailed
    from src.inference.predict_3d import list_available_models_3d, run_predict_3d

    allowed = set(list_available_models_3d(_ROOT)) or {"unet_3d_wmh"}
    if effective not in allowed:
        raise HTTPException(400, detail=f"Unknown 3D model '{effective}'. Available: {sorted(allowed)}")
    ctx = _parse_optional_context_form(context)
    try:
        raw = run_predict_3d(bytes_data, filename, effective, clinical_context=ctx)
    except InputValidationFailed as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except ClinicalContextRequired as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    risk = raw.get("wmh", {}).get("risk_level") if raw.get("wmh") else None
    api_ver = (os.environ.get("API_MODEL_VERSION") or "").strip() or app.version
    audit_id, audit_ts = log_inference(
        bytes_data,
        filename,
        effective,
        api_ver,
        ctx,
        {"endpoint": "/predict-3d"},
        raw,
        x_user_id,
    )

    return Predict3DResponse(
        label=str(raw["label"]),
        prediction=raw.get("prediction"),
        confidence=float(raw["confidence"]),
        probabilities=dict(raw["probabilities"]),
        model=str(raw["model"]),
        task=raw.get("task"),
        wmh=raw.get("wmh"),
        inference_time_s=raw.get("inference_time_s"),
        saliency_map_b64=raw.get("saliency_map_b64"),
        input_shape=raw.get("input_shape"),
        risk_level=risk,
        warnings=list(raw.get("warnings") or []),
        uncertainty=raw.get("uncertainty"),
        validation=raw.get("validation"),
        clinical_context=raw.get("clinical_context") or ctx,
        audit_id=audit_id,
        audit_timestamp=audit_ts,
    )


@app.post("/report/sign")
@limiter.limit("60/minute")
async def report_sign(
    request: Request,
    body: ReportSignBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.inference.audit_log import append_signoff_event, audit_record_exists

    aid = body.audit_id.strip()
    if not audit_record_exists(aid):
        raise HTTPException(status_code=404, detail="audit_id not found in local inference logs")
    if body.agreed and (body.override or "").strip():
        raise HTTPException(status_code=400, detail="omit override when agreed is true")
    if not body.agreed and not (body.override or "").strip():
        raise HTTPException(status_code=400, detail="override narrative required when agreed is false")
    rad = (body.radiologist_id or x_user_id or "").strip() or None
    sid = append_signoff_event(
        aid,
        "sign",
        {"agreed": body.agreed, "override": body.override},
        rad,
    )
    return {
        "ok": True,
        "signoff_id": sid,
        "audit_id": aid,
        "fhir_diagnostic_report_reference": None,
        "pdf_url": None,
        "notice": "FHIR Resource and PDF issuance are not wired in this research build.",
    }


@app.post("/report/defer")
@limiter.limit("60/minute")
async def report_defer(
    request: Request,
    body: ReportDeferBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.inference.audit_log import append_signoff_event, audit_record_exists

    aid = body.audit_id.strip()
    if not audit_record_exists(aid):
        raise HTTPException(status_code=404, detail="audit_id not found")
    sid = append_signoff_event(aid, "defer", {"reason": body.reason.strip()}, x_user_id)
    return {"ok": True, "defer_id": sid, "audit_id": aid}


@app.post("/clinical/findings-disagree")
@limiter.limit("60/minute")
async def findings_disagree_endpoint(
    request: Request,
    body: FindingsDisagreeBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.inference.audit_log import append_signoff_event, audit_record_exists

    aid = body.audit_id.strip()
    if not audit_record_exists(aid):
        raise HTTPException(status_code=404, detail="audit_id not found")
    rad = (body.radiologist_id or x_user_id or "").strip() or None
    rid = append_signoff_event(aid, "findings_disagree", {"notes": body.notes.strip()}, rad)
    return {"ok": True, "feedback_id": rid, "audit_id": aid}


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
    try:
        from src.inference.inference_exceptions import InputValidationFailed

        label, conf, probs, _, _, _ = _run_predict(bytes_data, model, filename, content_type)
    except InputValidationFailed as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
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
