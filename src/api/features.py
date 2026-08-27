"""
Public marketing/catalog payload: product features + live backend capabilities.
Used by GET /features in main.py (no API key required for landing pages).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class FeatureItem(BaseModel):
    id: str
    title: str
    description: str
    available: bool = True


class Capabilities(BaseModel):
    models_2d: list[str] = Field(default_factory=list)
    models_3d: list[str] = Field(default_factory=list)
    mongo_configured: bool = False
    llm_configured: bool = False
    llm_provider: str = ""
    bedrock_configured: bool = False
    auth_required_globally: bool = False


class FeaturesResponse(BaseModel):
    service: str = "brain-tumor-mri-api"
    version: str = "0.2.0"
    features: list[FeatureItem]
    capabilities: Capabilities


# Canonical copy aligned with frontend marketing (MarketingLanding #features).
_CATALOG: list[dict[str, str]] = [
    {
        "id": "shadow-mode",
        "title": "Shadow-mode ready",
        "description": (
            "Every prediction can be run in shadow mode with study UID and site ID, so you can audit performance "
            "before AI impacts clinical decisions."
        ),
    },
    {
        "id": "clinical-feedback",
        "title": "Feedback at the point of read",
        "description": (
            "Simple agree / correct / unclear flow with optional corrected class and reasons, wired into dashboards "
            "and safety views."
        ),
    },
    {
        "id": "report-drafts",
        "title": "Report drafts with evidence",
        "description": (
            "Drafts are designed to sit next to your structured templates, with an evidence drawer to show what the "
            "model was grounded on."
        ),
    },
    {
        "id": "agent-traces",
        "title": "Agent traces",
        "description": (
            "A dedicated view for seeing how AI assistants worked together on a case – evidence retrieved, policies "
            "checked, and decisions proposed."
        ),
    },
]


def _capabilities() -> Capabilities:
    models_2d: list[str] = []
    models_3d: list[str] = []
    try:
        from src.inference.predict import list_available_models

        models_2d = list(list_available_models(_ROOT))
    except Exception:
        models_2d = []
    try:
        from src.inference.predict_3d import list_available_models_3d

        models_3d = list(list_available_models_3d(_ROOT))
    except Exception:
        models_3d = []

    mongo_configured = bool((os.environ.get("MONGODB_URI") or "").strip())
    bedrock_configured = bool((os.environ.get("BEDROCK_MODEL_ID") or "").strip())
    gemini_configured = bool((os.environ.get("GOOGLE_API_KEY") or "").strip())
    llm_configured = bedrock_configured or gemini_configured
    llm_provider = ""
    if llm_configured:
        try:
            from src.llm.client import resolve_default_provider

            llm_provider = resolve_default_provider()
        except Exception:
            llm_provider = "bedrock" if bedrock_configured else "gemini"
    raw_keys = os.environ.get("API_KEYS") or os.environ.get("API_KEY") or ""
    auth_required = bool(raw_keys.strip())

    return Capabilities(
        models_2d=models_2d,
        models_3d=models_3d,
        mongo_configured=mongo_configured,
        llm_configured=llm_configured,
        llm_provider=llm_provider,
        bedrock_configured=bedrock_configured,
        auth_required_globally=auth_required,
    )


def _availability(cap: Capabilities) -> dict[str, bool]:
    has_2d = len(cap.models_2d) > 0
    return {
        "shadow-mode": has_2d,
        "clinical-feedback": has_2d,
        "report-drafts": has_2d and cap.llm_configured,
        "agent-traces": cap.mongo_configured,
    }


def build_features_response() -> FeaturesResponse:
    ver = os.environ.get("APP_VERSION", "0.2.0")
    cap = _capabilities()
    avail = _availability(cap)
    items = [
        FeatureItem(
            id=c["id"],
            title=c["title"],
            description=c["description"],
            available=avail.get(c["id"], False),
        )
        for c in _CATALOG
    ]
    return FeaturesResponse(version=str(ver), features=items, capabilities=cap)


def catalog_for_tests() -> list[dict[str, Any]]:
    """Expose raw catalog for tests or docs without building a response."""
    return list(_CATALOG)
