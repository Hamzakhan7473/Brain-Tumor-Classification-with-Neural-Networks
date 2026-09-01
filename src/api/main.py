"""REST API for brain tumor MRI: predict and optional report draft.
Deploy with: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Phase 1 roadmap: API-first for PACS/RIS and cloud deployment (Cloud Run, Lambda).

Optional auth: set API_KEY, APP_API_KEY, or API_KEYS (comma-separated); clients send X-API-Key.
If unset, requests are accepted without a key (development only).
"""
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
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

from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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
    try:
        from src.llm.versions import log_startup_versions

        log_startup_versions()
    except Exception as exc:
        print(f"LLM version pin: (unavailable: {exc})")
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


class ClinicalValidation(BaseModel):
    passed: bool = True
    invented_numbers: list[str] = Field(default_factory=list)
    invented_entities: list[str] = Field(default_factory=list)
    omitted_findings: list[str] = Field(default_factory=list)
    contradicted_claims: list[str] = Field(default_factory=list)
    unaddressed_claims: list[str] = Field(default_factory=list)
    independent_visual_claims: list[str] = Field(default_factory=list)
    used_fallback: bool = False
    regenerated: bool = False
    violations: list[dict] = Field(default_factory=list)
    contextual_grounding: Optional[dict] = None
    chain_of_verification: Optional[dict] = None


class ContentProvenance(BaseModel):
    generated_by: str
    prompt_template_version: str
    grounding_score: Optional[float] = None
    validator_status: str = "passed"
    validator_warnings: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    prediction: str
    confidence: float
    report_text: str
    study_instance_uid: Optional[str] = None
    site_id: Optional[str] = None
    shadow_mode: bool = False
    validation: Optional[ClinicalValidation] = None
    provenance: Optional[ContentProvenance] = None


class ExplanationResponse(BaseModel):
    prediction: str
    confidence: float
    explanation: str
    study_instance_uid: Optional[str] = None
    site_id: Optional[str] = None
    shadow_mode: bool = False
    validation: Optional[ClinicalValidation] = None
    provenance: Optional[ContentProvenance] = None


STRUCTURED_FEEDBACK_ERROR_CATEGORIES = frozenset(
    {
        "wrong_class",
        "confidence_too_high",
        "confidence_too_low",
        "saliency_wrong_region",
        "missed_finding",
        "out_of_distribution",
        "image_quality",
        "sequence_mismatch",
    }
)
STRUCTURED_SEVERITY_LABELS = frozenset({"Normal", "Mild", "Moderate", "Severe"})


class StructuredClinicalFeedbackSubmit(BaseModel):
    """Structured radiologist verdict for retraining / IRB workflows (schema v1.0)."""

    case_id: str = Field(..., min_length=4)
    verdict: Literal["agree", "partial", "disagree"]
    ground_truth: Optional[dict] = None
    error_categories: list[str] = Field(default_factory=list)
    clinical_notes: Optional[str] = Field(None, max_length=500)
    time_spent_s: int = Field(..., ge=0, le=86400)
    reviewer_display_name: Optional[str] = Field(None, max_length=200)
    reviewer_role: Optional[str] = Field(None, max_length=120)
    credentials: Optional[str] = Field(None, max_length=32)


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


class DocsQueryRequest(BaseModel):
    question: str
    doc_filter: Optional[list[str]] = None
    max_nodes: int = Field(8, ge=1, le=32)


class DocsAssistantCitation(BaseModel):
    doc_id: str
    doc_name: str
    section: str
    page: int | str
    node_id: str = ""
    snippet: str
    relevance: float


class DocsQueryResponse(BaseModel):
    answer: str
    citations: list[DocsAssistantCitation]
    confidence: str
    reasoning_trace: list[str] = Field(default_factory=list)
    latency_ms: int
    tokens_used: int = 0
    audit_id: str
    timestamp: str


class DocsFeedbackBody(BaseModel):
    audit_id: str = Field(..., min_length=8)
    reason: str = Field(..., min_length=1)
    question: str = ""


class ShadowFeedbackBody(BaseModel):
    verdict: str
    ground_truth: Optional[dict] = None
    notes: Optional[str] = Field(None, max_length=500)


class ShadowAssignBody(BaseModel):
    radiologist_id: str = Field(..., min_length=1)
    radiologist_name: str = Field(..., min_length=1)


class ShadowFlagBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class ShadowIngestBody(BaseModel):
    """Authenticated ingest for pilot hospitals (no live PACS required)."""

    study_uid: str = Field(..., min_length=4)
    site_id: str = Field("site-001", min_length=1)
    site_name: Optional[str] = None
    modality: str = "MR"
    sequence: str = "FLAIR"
    slice_count: int = 0
    patient: Optional[dict] = None
    ingest_source: str = Field("api", description="pacs_listener | manual_upload | api")
    model_run: Optional[dict] = None
    flags: list[dict] = Field(default_factory=list)


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


class CreateReportDraftBody(BaseModel):
    """Start a structured RSNA-style report from a study id and optional frozen model output."""

    case_id: str = Field(..., min_length=4, description="StudyInstanceUID or internal case id")
    template_id: str = Field(..., min_length=3)
    model_run: Optional[dict] = Field(
        None,
        description="Full inference payload (audit_id, wmh, confidence, …). Required when no Mongo inference row exists.",
    )
    clinical_context: Optional[dict] = None
    scanner_field_strength: Optional[str] = None
    prior_studies: Optional[str] = None
    prior_model_run: Optional[dict] = Field(
        None,
        description="Prior timepoint inference payload (wmh metrics) for longitudinal comparison.",
    )


class ReportDraftSectionUpdateBody(BaseModel):
    text: Optional[str] = None
    findings: Optional[list[dict]] = None
    impressions: Optional[list[dict]] = None


class ReportDraftSignBody(BaseModel):
    signer_name: str = Field(..., min_length=1, max_length=200)
    signer_role: str = Field(..., min_length=1, max_length=120)
    npi_or_license: Optional[str] = Field(None, max_length=64)
    acknowledged_disclaimer: bool = Field(..., description="Must be true to sign")


class ReportAttestBody(BaseModel):
    attested_by: str = Field(..., min_length=1, max_length=200)
    attestation_text: str = Field(..., min_length=1)


class ContentAttestBody(BaseModel):
    """Attestation for free-text /report or explanation output (no draft id)."""

    attested_by: str = Field(..., min_length=1, max_length=200)
    attestation_text: str = Field(..., min_length=1)
    content_kind: Literal["report", "explanation"] = "report"
    content_sha256: Optional[str] = Field(None, max_length=64)


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


def _inference_event_to_model_run(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal model_run dict from a Mongo inference_events row."""
    ts = str(ev.get("timestamp") or "")
    uid = str(ev.get("study_instance_uid") or "")
    aid = hashlib.sha256(f"{ts}{uid}".encode()).hexdigest()[:16]
    return {
        "audit_id": aid,
        "model_name": str(ev.get("model") or "unknown"),
        "model_version": str(ev.get("model_version") or "mongo"),
        "confidence": float(ev.get("confidence") or 0.0),
        "label": ev.get("label"),
        "probabilities": dict(ev.get("probabilities") or {}),
        "wmh": ev.get("wmh") if isinstance(ev.get("wmh"), dict) else None,
    }


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


def _docs_manifest_path() -> Path:
    return _ROOT / "data" / "doc_trees" / "manifest.json"


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


@app.post("/docs/ask", response_model=DocsQueryResponse)
@limiter.limit("60/minute")
async def docs_ask(
    request: Request,
    body: DocsQueryRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    """
    NeuroSight Docs Assistant: PageIndex (primary) with Mongo vector RAG fallback.
    Every query is audit-logged (JSONL + optional MongoDB ``audit_log``).
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question too long (max 500 chars)")

    manifest_path = _docs_manifest_path()
    if not manifest_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Document index not built. Run scripts/index_clinical_docs.py",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Invalid document manifest") from exc

    doc_rows = manifest.get("documents") or []
    doc_ids = [str(d.get("doc_id")) for d in doc_rows if d.get("doc_id")]
    if body.doc_filter:
        allowed = set(body.doc_filter)
        doc_ids = [d for d in doc_ids if d in allowed]
    if not doc_ids:
        raise HTTPException(status_code=404, detail="No documents match filter")

    user_id = (x_user_id or api_key_user or "anonymous")[:128]

    from src.rag import pageindex_client as pi_mod

    result: Dict[str, Any]
    engine = "pageindex"
    try:
        if not getattr(pi_mod, "PAGEINDEX_API_KEY", ""):
            raise RuntimeError("PAGEINDEX_API_KEY not set")
        indexer = pi_mod.get_indexer()
        result = indexer.query(question=question, doc_ids=doc_ids, max_nodes=body.max_nodes)
    except Exception as exc:
        engine = "vector_rag"
        try:
            from src.rag.fallback import vector_rag_query

            result = await vector_rag_query(question, top_k=body.max_nodes)
        except Exception:
            raise HTTPException(
                status_code=502,
                detail=f"Docs retrieval failed: PageIndex ({exc!r}); vector fallback also failed.",
            ) from exc

    citations_raw = result.get("citations") or []
    citations_out: list[DocsAssistantCitation] = []
    for c in citations_raw:
        if not isinstance(c, dict):
            continue
        citations_out.append(
            DocsAssistantCitation(
                doc_id=str(c.get("doc_id") or ""),
                doc_name=str(c.get("doc_name") or ""),
                section=str(c.get("section") or "—"),
                page=c.get("page") if c.get("page") is not None else "—",
                node_id=str(c.get("node_id") or ""),
                snippet=str(c.get("snippet") or ""),
                relevance=float(c.get("relevance") or 0.0),
            )
        )

    answer_text = str(result.get("answer") or "").strip()
    if not citations_out and "no relevant source found" not in answer_text.lower():
        answer_text = "No relevant source found in knowledge base."

    from src.inference.audit_log import log_docs_assistant_query

    answer_hash = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()[:16]
    audit_id, _ts = log_docs_assistant_query(
        user_id=user_id,
        question=question,
        doc_filter=body.doc_filter,
        answer_hash=answer_hash,
        citation_count=len(citations_out),
        confidence=str(result.get("confidence") or "low"),
        engine=engine,
    )

    try:
        from src.db.repositories import insert_audit_log_event

        await insert_audit_log_event(
            {
                "audit_id": audit_id,
                "event_type": "docs_query",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {
                    "question": question[:500],
                    "doc_filter": body.doc_filter,
                    "answer_hash": answer_hash,
                    "citation_count": len(citations_out),
                    "confidence": str(result.get("confidence") or "low"),
                    "engine": engine,
                },
            }
        )
    except Exception:
        pass

    ts_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return DocsQueryResponse(
        answer=answer_text,
        citations=citations_out,
        confidence=str(result.get("confidence") or "low"),
        reasoning_trace=list(result.get("reasoning_trace") or []),
        latency_ms=int(result.get("latency_ms") or 0),
        tokens_used=int(result.get("tokens_used") or 0),
        audit_id=audit_id,
        timestamp=ts_iso,
    )


@app.get("/docs/manifest")
@limiter.limit("120/minute")
async def docs_manifest(request: Request, _api_key: Optional[str] = Depends(verify_api_key)):
    """List indexed PageIndex documents (from on-disk manifest)."""
    manifest_path = _docs_manifest_path()
    if not manifest_path.exists():
        return {"documents": [], "indexed": False, "total": 0}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"documents": [], "indexed": False, "total": 0}
    data.setdefault("indexed", True)
    return data


@app.post("/feedback/docs")
@limiter.limit("30/minute")
async def feedback_docs(
    request: Request,
    body: DocsFeedbackBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    """Flag an inaccurate docs assistant answer for review (append-only audit)."""
    user_id = (x_user_id or api_key_user or "anonymous")[:128]
    rec = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_id": user_id,
        "audit_id": body.audit_id,
        "question": (body.question or "")[:500],
        "reason": body.reason[:2000],
    }
    log_dir = _ROOT / "logs" / "audit"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "docs_feedback.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
    try:
        from src.db.repositories import insert_audit_log_event

        await insert_audit_log_event(
            {
                "audit_id": body.audit_id,
                "event_type": "docs_feedback",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "payload": {"reason": body.reason[:2000], "question": (body.question or "")[:500]},
            }
        )
    except Exception:
        pass
    return {"status": "received"}


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

def _saliency_overlay_bytes(saliency_b64: Optional[str]) -> Optional[bytes]:
    """Decode Grad-CAM / saliency PNG bytes. Never used for raw diagnostic pixels."""
    raw = (saliency_b64 or "").strip()
    if not raw:
        return None
    import base64

    try:
        return base64.b64decode(raw)
    except Exception:
        return None


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
    Same as /predict, plus an LLM narration of the classifier output.

    The uploaded file is used only for Keras inference. Raw scan bytes are
    never sent to Claude (FDA Non-Device CDS Criterion 1). Optional visual
    context is the Grad-CAM overlay only.
    """
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(400, detail="Empty file")
    if shadow_mode:
        raise HTTPException(
            status_code=400,
            detail="Clinical reports cannot be generated for shadow-mode uploads. "
            "Use the shadow queue for retrospective QA only — findings must not enter the clinical record.",
        )
    if study_instance_uid:
        from src.shadow.db import is_shadow_study

        if await is_shadow_study(study_instance_uid):
            raise HTTPException(
                status_code=400,
                detail="Cannot generate clinical report for a shadow queue case. "
                "This study is enrolled in Phase B shadow QA only.",
            )
    filename = file.filename or "image"
    content_type = file.content_type or ""
    try:
        from src.inference.inference_exceptions import InputValidationFailed

        label, conf, probs, _, infer_meta, _ = _run_predict(bytes_data, model, filename, content_type)
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
        from src.llm.validation import ValidationResult
        from src.rag.retrieval import retrieve_evidence

        visual_overlay = _saliency_overlay_bytes((infer_meta or {}).get("saliency_map_b64"))

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

        report_text, gate = build_report(
            label,
            conf,
            evidence_context=evidence_context,
            probabilities=probs,
            visual_overlay=visual_overlay,
        )
        if not report_text:
            report_text = f"Prediction: {label} ({conf:.2%}). No LLM response."
            gate = ValidationResult(passed=True, used_fallback=True)
    except Exception as e:
        from src.llm.validation import ValidationResult as _VR

        report_text = f"Prediction: {label} ({conf:.2%}). Report generation failed: {e}"
        gate = _VR(passed=True, used_fallback=True)

    await _log_api_clinical(
        "api_report",
        study_instance_uid,
        site_id,
        shadow_mode,
        {
            "model": model,
            "label": label,
            "confidence": conf,
            "probabilities": probs,
            "validation": gate.to_dict(),
        },
    )
    _maybe_shadow_store(shadow_mode, study_instance_uid, site_id, model, label, conf, probs, "/report")

    from src.llm.content_provenance import build_content_provenance

    prov = build_content_provenance(prompt_template_name="report", gate=gate)
    return ReportResponse(
        prediction=label,
        confidence=conf,
        report_text=report_text,
        study_instance_uid=study_instance_uid,
        site_id=site_id,
        shadow_mode=shadow_mode,
        validation=ClinicalValidation(**{k: v for k, v in gate.to_dict().items() if k in ClinicalValidation.model_fields}),
        provenance=ContentProvenance(**prov),
    )


@app.post("/explain", response_model=ExplanationResponse)
@limiter.limit("60/minute")
async def explain_scan(
    request: Request,
    file: UploadFile = File(...),
    model: str = "custom_cnn",
    study_instance_uid: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    shadow_mode: bool = Form(False),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Narrate the CNN/U-Net result. Raw scan bytes are used only for Keras
    inference — they are never sent to Claude (FDA Non-Device CDS Criterion 1).
    """
    bytes_data = await file.read()
    if not bytes_data:
        raise HTTPException(400, detail="Empty file")
    filename = file.filename or "image"
    content_type = file.content_type or ""
    try:
        from src.inference.inference_exceptions import InputValidationFailed

        label, conf, probs, _, infer_meta, _ = _run_predict(bytes_data, model, filename, content_type)
    except InputValidationFailed as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if label is None:
        raise HTTPException(503, detail="Model not available or load failed")

    try:
        from src.llm.explanations import explain_image

        visual_overlay = _saliency_overlay_bytes((infer_meta or {}).get("saliency_map_b64"))
        explanation, gate, prov = explain_image(
            label,
            confidence=conf,
            probabilities=probs,
            visual_overlay=visual_overlay,
        )
    except Exception as e:
        from src.llm.content_provenance import build_content_provenance
        from src.llm.validation import ValidationResult as _VR

        explanation = f"Model prediction: {label}. Explanation unavailable: {e}"
        gate = _VR(passed=True, used_fallback=True)
        prov = build_content_provenance(prompt_template_name="explanation", gate=gate)

    return ExplanationResponse(
        prediction=label,
        confidence=conf,
        explanation=explanation,
        study_instance_uid=study_instance_uid,
        site_id=site_id,
        shadow_mode=shadow_mode,
        validation=ClinicalValidation(
            **{k: v for k, v in gate.to_dict().items() if k in ClinicalValidation.model_fields}
        ),
        provenance=ContentProvenance(**prov),
    )


# --- Structured report drafts (RSNA JSON sections, provenance, sign-off) ---


def _report_draft_user(x_user_id: Optional[str], api_key_user: Optional[str]) -> str:
    return ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]


@app.post("/report/draft")
@limiter.limit("30/minute")
async def create_report_draft(
    request: Request,
    body: CreateReportDraftBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_latest_inference_for_study, insert_report_draft
    from src.llm.report_builder import ReportBuilder

    case_id = body.case_id.strip()
    model_run = body.model_run
    if model_run is None:
        inf = await get_latest_inference_for_study(case_id)
        if inf:
            model_run = _inference_event_to_model_run(inf)
    if not model_run:
        raise HTTPException(
            status_code=404,
            detail="No inference record for case_id; include model_run in the request body.",
        )

    case: Dict[str, Any] = {
        "study_uid": case_id,
        "case_id": case_id,
        "clinical_context": body.clinical_context,
        "scanner_field_strength": body.scanner_field_strength,
        "prior_studies": body.prior_studies,
    }
    if body.prior_model_run and isinstance(model_run.get("wmh"), dict):
        from src.inference.wmh_longitudinal import compare_wmh_timepoints

        case["longitudinal"] = compare_wmh_timepoints(
            model_run,
            body.prior_model_run,
            prior_label=body.prior_studies or "prior study",
        )
    try:
        builder = ReportBuilder(body.template_id.strip())
        draft = builder.build_draft(case=case, model_run=model_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await insert_report_draft(draft)
    return draft


@app.get("/report/{report_id}")
@limiter.limit("120/minute")
async def get_report_draft(
    request: Request,
    report_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import get_report_draft

    doc = await get_report_draft(report_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    return doc


@app.patch("/report/{report_id}/section/{section_name}")
@limiter.limit("120/minute")
async def patch_report_draft_section(
    request: Request,
    report_id: str,
    section_name: str,
    body: ReportDraftSectionUpdateBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.inference.audit_log import log_report_draft_event
    from src.db.repositories import get_report_draft, replace_report_draft

    user = _report_draft_user(x_user_id, api_key_user)
    report = await get_report_draft(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("status") in ("signed", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot edit a {report['status']} report")

    section_idx = next((i for i, s in enumerate(report.get("sections") or []) if s.get("name") == section_name), None)
    if section_idx is None:
        raise HTTPException(status_code=404, detail=f"Section {section_name} not found")

    old_section = dict(report["sections"][section_idx])
    history_entry = {
        "version": len(old_section.get("history", [])) + 1,
        "snapshot": {k: v for k, v in old_section.items() if k != "history"},
        "edited_by": user,
        "edited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    updates = body.model_dump(exclude_unset=True)
    new_section = {**old_section, **updates, "source": "edited"}
    if section_name == "findings" and updates.get("text") and not updates.get("findings"):
        new_section["findings"] = [
            {"region": "Narrative", "text": updates["text"], "measurements": [], "citations": []}
        ]
        new_section["text"] = None
    new_section["last_edited"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_section["edited_by"] = user
    new_section["history"] = list(old_section.get("history") or []) + [history_entry]

    report["sections"][section_idx] = new_section
    report["last_modified"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["auto_saved_at"] = report["last_modified"]
    await replace_report_draft(report_id, report)

    log_report_draft_event(
        event_type="report_section_edited",
        user_id=user,
        payload={"report_id": report_id, "section": section_name, "version": history_entry["version"]},
    )
    return {"ok": True, "version": history_entry["version"]}


@app.post("/report/{report_id}/section/{section_name}/regenerate")
@limiter.limit("20/minute")
async def regenerate_report_draft_section(
    request: Request,
    report_id: str,
    section_name: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.inference.audit_log import log_report_draft_event
    from src.db.repositories import get_report_draft, replace_report_draft
    from src.llm.report_builder import ReportBuilder

    user = _report_draft_user(x_user_id, api_key_user)
    report = await get_report_draft(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("status") in ("signed", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot regenerate a {report['status']} report")

    if section_name not in ("findings", "impression", "recommendations"):
        raise HTTPException(status_code=400, detail="Section cannot be AI-regenerated")

    section_idx = next((i for i, s in enumerate(report.get("sections") or []) if s.get("name") == section_name), None)
    if section_idx is None:
        raise HTTPException(status_code=404, detail=f"Section {section_name} not found")

    old_section = dict(report["sections"][section_idx])
    history_entry = {
        "version": len(old_section.get("history", [])) + 1,
        "snapshot": {k: v for k, v in old_section.items() if k != "history"},
        "edited_by": user,
        "edited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    builder = ReportBuilder(str(report.get("template_id")))
    new_section = builder.regenerate_section(section_name, report)
    if not new_section:
        raise HTTPException(status_code=500, detail="Regeneration failed")
    new_section["history"] = list(old_section.get("history") or []) + [history_entry]
    new_section["last_edited"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_section["edited_by"] = user

    report["sections"][section_idx] = new_section
    report["last_modified"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    await replace_report_draft(report_id, report)

    log_report_draft_event(
        event_type="report_section_regenerated",
        user_id=user,
        payload={"report_id": report_id, "section": section_name},
    )
    return {"ok": True, "version": history_entry["version"]}


@app.post("/report/{report_id}/attest")
@limiter.limit("30/minute")
async def attest_report_draft(
    request: Request,
    report_id: str,
    body: ReportAttestBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    """
    Explicit clinician attestation — distinct from viewing and from e-sign.

    Required before PDF/FHIR export or POST /report/{id}/sign. Does not
    bypass Prompt 1/2/4 automated gates.
    """
    from src.api.attestation import (
        DEFAULT_ATTESTATION_TEXT,
        attestation_text_is_valid,
        report_is_attested,
    )
    from src.inference.audit_log import log_report_draft_event
    from src.db.repositories import get_report_draft, replace_report_draft

    user = _report_draft_user(x_user_id, api_key_user)
    if not str(body.attested_by or "").strip():
        raise HTTPException(status_code=422, detail="attested_by is required")
    if not str(body.attestation_text or "").strip():
        raise HTTPException(status_code=422, detail="attestation_text is required")
    if not attestation_text_is_valid(body.attestation_text):
        raise HTTPException(
            status_code=400,
            detail="attestation_text must be the required clinician attestation statement",
        )

    report = await get_report_draft(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("status") in ("signed", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot attest a {report['status']} report")
    if report_is_attested(report):
        return {
            "ok": True,
            "already_attested": True,
            "attested_by": report.get("attested_by"),
            "attested_at": report.get("attested_at"),
            "audit_id": report.get("attestation_audit_id"),
        }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_id = log_report_draft_event(
        event_type="report_attested",
        user_id=user,
        payload={
            "report_id": report_id,
            "study_uid": report.get("study_uid"),
            "attested_by": body.attested_by.strip(),
            "attestation_text": DEFAULT_ATTESTATION_TEXT,
            "timestamp_utc": now,
        },
    )
    report["attested_by"] = body.attested_by.strip()
    report["attested_at"] = now
    report["attestation_text"] = DEFAULT_ATTESTATION_TEXT
    report["attestation_audit_id"] = audit_id
    report["last_modified"] = now
    await replace_report_draft(report_id, report)
    return {
        "ok": True,
        "already_attested": False,
        "attested_by": report["attested_by"],
        "attested_at": now,
        "audit_id": audit_id,
    }


@app.post("/report/attest-content")
@limiter.limit("30/minute")
async def attest_free_text_content(
    request: Request,
    body: ContentAttestBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    """Attest a free-text /report or explanation when there is no draft id."""
    from src.api.attestation import DEFAULT_ATTESTATION_TEXT, attestation_text_is_valid
    from src.inference.audit_log import log_report_draft_event

    user = _report_draft_user(x_user_id, api_key_user)
    if not str(body.attested_by or "").strip() or not str(body.attestation_text or "").strip():
        raise HTTPException(status_code=422, detail="attested_by and attestation_text are required")
    if not attestation_text_is_valid(body.attestation_text):
        raise HTTPException(
            status_code=400,
            detail="attestation_text must be the required clinician attestation statement",
        )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_id = log_report_draft_event(
        event_type="content_attested",
        user_id=user,
        payload={
            "attested_by": body.attested_by.strip(),
            "attestation_text": DEFAULT_ATTESTATION_TEXT,
            "content_kind": body.content_kind,
            "content_sha256": body.content_sha256,
            "timestamp_utc": now,
        },
    )
    return {"ok": True, "audit_id": audit_id, "attested_at": now}


@app.post("/report/{report_id}/sign")
@limiter.limit("20/minute")
async def sign_report_draft(
    request: Request,
    report_id: str,
    body: ReportDraftSignBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.api.report_export import serialize_report_for_hash, sha256_text
    from src.inference.audit_log import log_report_draft_event
    from src.db.repositories import get_report_draft, replace_report_draft, insert_audit_log_event

    user = _report_draft_user(x_user_id, api_key_user)
    if not body.acknowledged_disclaimer:
        raise HTTPException(status_code=400, detail="Disclaimer must be acknowledged")

    report = await get_report_draft(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("status") == "signed":
        raise HTTPException(status_code=400, detail="Already signed")
    from src.api.attestation import require_attested

    require_attested(report)

    final_text = serialize_report_for_hash(report)
    text_hash = sha256_text(final_text)

    audit_id = log_report_draft_event(
        event_type="report_signed",
        user_id=user,
        payload={
            "report_id": report_id,
            "study_uid": report.get("study_uid"),
            "final_text_hash": text_hash,
            "signed_by_name": body.signer_name,
            "signed_by_role": body.signer_role,
            "npi_or_license": body.npi_or_license,
            "edits_made": sum(len(s.get("history") or []) for s in report.get("sections") or []),
            "model_confidence": report.get("model_confidence"),
        },
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["status"] = "signed"
    report["signed_by"] = f"{body.signer_name} ({body.signer_role})"
    report["signed_at"] = now
    report["signed_text_hash"] = text_hash
    report["signature_audit_id"] = audit_id
    report["last_modified"] = now
    await replace_report_draft(report_id, report)

    try:
        await insert_audit_log_event(
            {
                "audit_id": audit_id,
                "event_type": "report_signed",
                "user_id": user,
                "timestamp": datetime.now(timezone.utc),
                "payload": {"report_id": report_id, "text_hash": text_hash},
            }
        )
    except Exception:
        pass

    pdf_rel = f"/report/{report_id}/pdf"

    return {
        "ok": True,
        "audit_id": audit_id,
        "text_hash": text_hash,
        "fhir_url": f"/report/{report_id}/fhir",
        "pdf_url": pdf_rel,
    }


@app.get("/report/{report_id}/pdf")
@limiter.limit("30/minute")
async def export_report_draft_pdf(
    request: Request,
    report_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from fastapi.responses import Response
    from src.api.report_export import render_report_pdf_bytes
    from src.db.repositories import get_report_draft

    report = await get_report_draft(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    from src.api.attestation import require_attested

    require_attested(report)
    footer_audit = str(report.get("signature_audit_id") or report.get("report_id") or "")
    footer_hash = str(report.get("signed_text_hash") or "unsigned")
    try:
        pdf_bytes = render_report_pdf_bytes(report, footer_audit=footer_audit, footer_hash=footer_hash)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.pdf"'},
    )


@app.get("/report/{report_id}/fhir")
@limiter.limit("60/minute")
async def export_report_draft_fhir(
    request: Request,
    report_id: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.api.report_export import build_fhir_diagnostic_report
    from src.db.repositories import get_report_draft

    report = await get_report_draft(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    from src.api.attestation import require_attested

    require_attested(report)
    pdf_url = f"/report/{report_id}/pdf"
    dr = build_fhir_diagnostic_report(report, pdf_url=pdf_url)
    if report.get("status") != "signed":
        dr["status"] = "preliminary"
    return dr


@app.post("/clinical/feedback")
@limiter.limit("120/minute")
async def clinical_feedback(
    request: Request,
    body: StructuredClinicalFeedbackSubmit,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    """
    Submit structured radiologist verdict (v1.0) for retraining / IRB workflows.
    Persists to ``clinical_feedback`` Mongo collection (or in-memory when Mongo disabled),
    JSONL audit, and Mongo ``audit_log``. Shadow cases also update the shadow queue row.
    """
    import secrets

    from src.api.case_review import build_model_run_for_review, infer_task
    from src.db.repositories import (
        get_latest_inference_for_study,
        get_latest_structured_feedback_for_case,
        insert_audit_log_event,
        insert_structured_clinical_feedback,
    )
    from src.inference.audit_log import log_clinical_feedback_audit
    from src.shadow.db import get_shadow_case, submit_shadow_feedback

    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    case_id = body.case_id.strip()

    sc = await get_shadow_case(case_id)
    existing = await get_latest_structured_feedback_for_case(case_id)
    if existing:
        raise HTTPException(status_code=409, detail="Feedback already submitted for this case")
    if sc and (sc.get("feedback") or {}).get("status") not in (None, "pending", ""):
        raise HTTPException(status_code=409, detail="Feedback already submitted for this case")

    for ec in body.error_categories:
        if ec not in STRUCTURED_FEEDBACK_ERROR_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Unknown error category: {ec}")

    v = body.verdict.lower().strip()
    if v in ("partial", "disagree") and not body.ground_truth:
        raise HTTPException(status_code=400, detail="Ground truth required when verdict is partial or disagree")

    mr_shadow: Optional[Dict[str, Any]] = None
    inf: Dict[str, Any] = {}
    site_id: Optional[str] = None

    if sc and sc.get("shadow_mode"):
        mr_shadow = sc.get("model_run") or {}
        site_id = sc.get("site_id")
        inf = {
            "model": mr_shadow.get("model_name"),
            "label": mr_shadow.get("label"),
            "confidence": mr_shadow.get("confidence"),
            "probabilities": mr_shadow.get("class_probabilities") or mr_shadow.get("probabilities") or {},
            "timestamp": None,
            "study_instance_uid": case_id,
            "site_id": site_id,
        }
    else:
        inf = await get_latest_inference_for_study(case_id) or {}
        if not inf:
            raise HTTPException(status_code=404, detail="Case not found")
        site_id = inf.get("site_id")

    task = infer_task(inf, mr_shadow)
    probs = inf.get("probabilities") if isinstance(inf.get("probabilities"), dict) else {}
    allowed_classes = {str(k).lower() for k in probs.keys()} if probs else set()
    if not allowed_classes and task == "classification":
        allowed_classes = {c.lower() for c in _get_class_names()}

    if task == "classification" and v != "agree":
        cls = (body.ground_truth or {}).get("class")
        if not cls:
            raise HTTPException(status_code=400, detail="Ground truth class is required")
        if str(cls).lower() not in allowed_classes:
            raise HTTPException(status_code=400, detail=f"Class must be one of {sorted(allowed_classes)}")

    if task == "segmentation" and v != "agree":
        sev = (body.ground_truth or {}).get("severity")
        if not sev or str(sev) not in STRUCTURED_SEVERITY_LABELS:
            raise HTTPException(
                status_code=400,
                detail=f"severity must be one of {sorted(STRUCTURED_SEVERITY_LABELS)}",
            )

    model_run = build_model_run_for_review(study_uid=case_id, inf=inf, shadow_mr=mr_shadow)
    feedback_id = f"fb_{secrets.token_hex(8)}"
    ts_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_dt = datetime.now(timezone.utc)

    audit_id = log_clinical_feedback_audit(
        event_type="clinical_feedback",
        user_id=user,
        payload={
            "feedback_id": feedback_id,
            "case_id": case_id,
            "verdict": v,
            "model_label": model_run.get("label"),
            "model_confidence": model_run.get("confidence"),
            "error_categories": body.error_categories,
            "ground_truth": body.ground_truth,
            "time_spent_s": body.time_spent_s,
        },
    )

    legacy_mirror = "agree" if v == "agree" else ("unclear" if v == "partial" else "wrong_class")

    record: Dict[str, Any] = {
        "feedback_id": feedback_id,
        "case_id": case_id,
        "study_instance_uid": case_id,
        "model_run_id": model_run["audit_id"],
        "verdict": body.verdict,
        "ground_truth": body.ground_truth,
        "error_categories": body.error_categories,
        "clinical_notes": (body.clinical_notes or "")[:500] if body.clinical_notes else None,
        "reviewer": {
            "user_id": user,
            "display_name": body.reviewer_display_name or user,
            "role": body.reviewer_role or "neuroradiologist",
            "credentials": body.credentials or "MD",
        },
        "timing": {
            "case_opened_at": now_dt,
            "verdict_at": now_dt,
            "submitted_at": now_dt,
            "time_spent_s": int(body.time_spent_s),
        },
        "audit_id": audit_id,
        "schema_version": "1.0",
        "shadow_mode": True,
        "used_for_retraining": False,
        "timestamp": ts_iso,
        "feedback": legacy_mirror,
        "site_id": site_id,
    }

    if sc and sc.get("shadow_mode"):
        ok, _ = await submit_shadow_feedback(
            case_id,
            verdict=v,
            ground_truth=body.ground_truth,
            notes=body.clinical_notes,
            submitted_by=user,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update shadow case feedback")

    await insert_structured_clinical_feedback(record)

    try:
        await insert_audit_log_event(
            {
                "audit_id": audit_id,
                "event_type": "clinical_feedback",
                "user_id": user,
                "timestamp": now_dt,
                "payload": {
                    "feedback_id": feedback_id,
                    "case_id": case_id,
                    "verdict": body.verdict,
                },
            }
        )
    except Exception:
        pass

    return {"ok": True, "feedback_id": feedback_id, "audit_id": audit_id}


@app.get("/clinical/feedback/stats")
@limiter.limit("120/minute")
async def clinical_feedback_stats(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import aggregate_clinical_feedback_stats

    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    return await aggregate_clinical_feedback_stats(user)


@app.get("/clinical/feedback/recent")
@limiter.limit("120/minute")
async def clinical_feedback_recent(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.db.repositories import list_recent_structured_feedback

    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    items = await list_recent_structured_feedback(user, limit=limit)

    def _ser(x: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(x)
        out.pop("_id", None)
        return out

    return {"items": [_ser(i) for i in items]}


# --- BICR (Stage 2: dual-read + adjudication + time-point lock) ---

from src.bicr.http_handlers import (
    BicrAdjudicateBody,
    BicrEnrollBody,
    BicrLockBody,
    BicrReadSubmitBody,
    handle_bicr_adjudicate,
    handle_bicr_enroll,
    handle_bicr_get,
    handle_bicr_lock,
    handle_bicr_queue,
    handle_bicr_read,
)


@app.post("/bicr/cases/enroll")
@limiter.limit("60/minute")
async def bicr_enroll_case(
    request: Request,
    body: BicrEnrollBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    case_payload = await get_case(request, body.case_id.strip(), _api_key=api_key_user)
    case_review = case_payload.get("case_review")
    if not case_review:
        raise HTTPException(status_code=404, detail="Case review payload missing")
    return await handle_bicr_enroll(body, user, case_review)


@app.get("/bicr/cases/{case_id}")
@limiter.limit("120/minute")
async def bicr_get_case(
    request: Request,
    case_id: str,
    role: str = Query("reader1", pattern="^(reader1|reader2|adjudicator)$"),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    return await handle_bicr_get(case_id.strip(), role)  # type: ignore[arg-type]


@app.post("/bicr/cases/{case_id}/reads")
@limiter.limit("60/minute")
async def bicr_submit_read(
    request: Request,
    case_id: str,
    body: BicrReadSubmitBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    return await handle_bicr_read(case_id.strip(), body, user)


@app.post("/bicr/cases/{case_id}/adjudicate")
@limiter.limit("60/minute")
async def bicr_adjudicate_case(
    request: Request,
    case_id: str,
    body: BicrAdjudicateBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    return await handle_bicr_adjudicate(case_id.strip(), body, user)


@app.post("/bicr/cases/{case_id}/lock")
@limiter.limit("30/minute")
async def bicr_lock_timepoint(
    request: Request,
    case_id: str,
    body: BicrLockBody,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    user = ((x_user_id or api_key_user or "anonymous") or "anonymous")[:128]
    return await handle_bicr_lock(case_id.strip(), body, user)


@app.get("/bicr/queue")
@limiter.limit("120/minute")
async def bicr_queue(
    request: Request,
    role: str = Query("reader1", pattern="^(reader1|reader2|adjudicator)$"),
    limit: int = Query(50, ge=1, le=200),
    _api_key: Optional[str] = Depends(verify_api_key),
):
    return await handle_bicr_queue(role, limit)  # type: ignore[arg-type]


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
        fb_status = "pending"
        if fb:
            if fb.get("schema_version") == "1.0":
                fb_status = str(fb.get("verdict") or "pending")
            elif fb.get("feedback"):
                fb_status = str(fb.get("feedback"))
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
    If the study exists in the Phase B ``shadow_cases`` collection, that record wins
    (shadow_mode is always true there — never treated as clinical record).
    """
    from src.api.case_review import build_case_review
    from src.db.repositories import (
        get_latest_feedback_for_study,
        get_latest_inference_for_study,
        get_latest_structured_feedback_for_case,
    )
    from src.shadow.db import get_shadow_case, serialize_case

    sc = await get_shadow_case(study_instance_uid)
    if sc and sc.get("shadow_mode"):
        mr = sc.get("model_run") or {}
        fb = sc.get("feedback") or {}
        ts = sc.get("received_at")
        if hasattr(ts, "isoformat"):
            ts_out = ts.isoformat() if ts.tzinfo else ts.replace(tzinfo=timezone.utc).isoformat()
        else:
            ts_out = None
        structured = await get_latest_structured_feedback_for_case(study_instance_uid)
        prior_fb = structured
        if not prior_fb and (fb.get("status") or "") not in ("", "pending", None):
            prior_fb = {
                "schema_version": "1.0",
                "verdict": str(fb.get("verdict") or "agree"),
                "feedback_id": None,
                "timestamp": fb.get("submitted_at"),
                "error_categories": [],
                "ground_truth": fb.get("ground_truth"),
                "clinical_notes": fb.get("notes"),
                "timing": {"submitted_at": fb.get("submitted_at")},
            }
        inf_row = {
            "model": mr.get("model_name"),
            "label": mr.get("label"),
            "confidence": mr.get("confidence"),
            "probabilities": mr.get("class_probabilities") or mr.get("probabilities") or {},
            "timestamp": ts_out,
            "study_instance_uid": study_instance_uid,
            "site_id": sc.get("site_id"),
        }
        patient = sc.get("patient") if isinstance(sc.get("patient"), dict) else {}
        case_review = build_case_review(
            case_id=study_instance_uid,
            study_uid=study_instance_uid,
            received_at=ts_out,
            site_id=sc.get("site_id"),
            patient=patient,
            inf=inf_row,
            shadow_mr=mr,
            prior_feedback=prior_fb,
        )
        return {
            "study_instance_uid": study_instance_uid,
            "from_shadow_queue": True,
            "shadow_case": serialize_case(sc),
            "inference": {
                "label": mr.get("label") or "—",
                "confidence": float(mr.get("confidence") or 0.0),
                "model": mr.get("model_name"),
                "shadow_mode": True,
                "study_instance_uid": study_instance_uid,
                "site_id": sc.get("site_id"),
                "timestamp": ts_out,
                "filename": "shadow_case",
                "metrics": mr.get("metrics"),
            },
            "feedback": fb if fb else None,
            "case_review": case_review,
        }

    inf = await get_latest_inference_for_study(study_instance_uid)
    fb = await get_latest_feedback_for_study(study_instance_uid)
    if not inf:
        raise HTTPException(status_code=404, detail="Case not found")

    structured = await get_latest_structured_feedback_for_case(study_instance_uid)
    prior_fb = structured or (fb if isinstance(fb, dict) else None)
    patient_ctx = inf.get("clinical_context") if isinstance(inf.get("clinical_context"), dict) else {}
    case_review = build_case_review(
        case_id=study_instance_uid,
        study_uid=study_instance_uid,
        received_at=inf.get("timestamp"),
        site_id=inf.get("site_id"),
        patient=patient_ctx,
        inf=inf,
        shadow_mr=None,
        prior_feedback=prior_fb,
    )
    return {
        "study_instance_uid": study_instance_uid,
        "from_shadow_queue": False,
        "inference": inf,
        "feedback": fb,
        "case_review": case_review,
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
# Shadow queue (Phase B — retrospective QA only; never clinical record)
# ----------------------------


@app.get("/shadow/config")
@limiter.limit("60/minute")
async def shadow_config(request: Request, _api_key: Optional[str] = Depends(verify_api_key)):
    """Class list for structured disagree feedback (from ``configs/data.yaml``)."""
    return {
        "classes": _get_class_names(),
        "shadow_mode_disclaimer": "Shadow cases are never written to the clinical record.",
    }


@app.get("/shadow/queue")
@limiter.limit("60/minute")
async def shadow_queue(
    request: Request,
    status: Optional[List[str]] = Query(None),
    site_id: Optional[str] = None,
    feedback: Optional[str] = None,
    assigned_to: Optional[str] = None,
    flagged: Optional[bool] = None,
    search: Optional[str] = None,
    sort: str = "received_at",
    order: str = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_queue

    return await handle_shadow_queue(
        status=status,
        site_id=site_id,
        feedback=feedback,
        assigned_to=assigned_to,
        flagged=flagged,
        search=search,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


@app.get("/shadow/cases/{study_uid}")
@limiter.limit("120/minute")
async def shadow_get_case(
    request: Request,
    study_uid: str,
    _api_key: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_get_case

    return await handle_shadow_get_case(study_uid)


@app.post("/shadow/cases/{study_uid}/feedback")
@limiter.limit("120/minute")
async def shadow_submit_feedback(
    request: Request,
    study_uid: str,
    body: ShadowFeedbackBody,
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_feedback

    uid = (api_key_user or "anonymous")[:128]
    return await handle_shadow_feedback(
        study_uid=study_uid,
        verdict=body.verdict,
        ground_truth=body.ground_truth,
        notes=body.notes,
        user_id=uid,
    )


@app.post("/shadow/cases/{study_uid}/assign")
@limiter.limit("120/minute")
async def shadow_assign_case(
    request: Request,
    study_uid: str,
    body: ShadowAssignBody,
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_assign

    uid = (api_key_user or "anonymous")[:128]
    return await handle_shadow_assign(
        study_uid=study_uid,
        rad_id=body.radiologist_id,
        rad_name=body.radiologist_name,
        user_id=uid,
    )


@app.post("/shadow/cases/{study_uid}/flag")
@limiter.limit("120/minute")
async def shadow_flag_case(
    request: Request,
    study_uid: str,
    body: ShadowFlagBody,
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_flag

    uid = (api_key_user or "anonymous")[:128]
    return await handle_shadow_flag(study_uid=study_uid, reason=body.reason, user_id=uid)


@app.post("/shadow/cases/{study_uid}/retry")
@limiter.limit("30/minute")
async def shadow_retry_case(
    request: Request,
    study_uid: str,
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_retry

    uid = (api_key_user or "anonymous")[:128]
    return await handle_shadow_retry(study_uid=study_uid, user_id=uid)


@app.post("/shadow/ingest")
@limiter.limit("60/minute")
async def shadow_ingest(
    request: Request,
    body: ShadowIngestBody,
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_ingest

    uid = (api_key_user or "anonymous")[:128]
    return await handle_shadow_ingest(body.model_dump(), user_id=uid)


@app.get("/shadow/export")
@limiter.limit("30/minute")
async def shadow_export(
    request: Request,
    start: str = Query(..., description="ISO8601 start (inclusive)"),
    end: str = Query(..., description="ISO8601 end (inclusive)"),
    export_format: str = Query("csv", alias="format", description="csv or json"),
    api_key_user: Optional[str] = Depends(verify_api_key),
):
    from src.shadow.http_handlers import handle_shadow_export

    uid = (api_key_user or "anonymous")[:128]
    return await handle_shadow_export(start=start, end=end, fmt=export_format, user_id=uid)


@app.get("/shadow/analytics")
@limiter.limit("30/minute")
async def shadow_analytics(request: Request, _api_key: Optional[str] = Depends(verify_api_key)):
    from src.shadow.http_handlers import handle_shadow_analytics

    return await handle_shadow_analytics()


@app.get("/shadow/stream")
@limiter.limit("10/minute")
async def shadow_stream(
    request: Request,
    x_api_key: Optional[str] = Query(None, description="For EventSource clients that cannot set X-API-Key header"),
    header_key: Optional[str] = Security(api_key_header),
):
    """SSE KPI snapshots (~4s). Query ``x_api_key`` is accepted only when API keys are configured."""
    keys = _load_api_keys()
    if keys:
        provided = (x_api_key or header_key or "").strip()
        if provided not in keys:
            raise HTTPException(status_code=401, detail="Missing or invalid API key for shadow stream")

    from src.shadow.http_handlers import shadow_stream_body

    return StreamingResponse(shadow_stream_body(), media_type="text/event-stream")


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
