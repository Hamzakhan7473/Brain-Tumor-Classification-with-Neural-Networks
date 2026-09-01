"""
Pinned LLM configuration for auditability.

Model IDs come from BEDROCK_MODEL_ID (env) and must never resolve to
``latest``. Prompt template versions are bumped here by hand when the
corresponding prompt text changes. Guardrail id/version are env-pinned.

Read this snapshot at call time (not import time) so an env change is
picked up without a code edit.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

# Fallback pin when BEDROCK_MODEL_ID is unset (local/dev). This is a concrete
# model ID, never an alias. Production should set BEDROCK_MODEL_ID explicitly.
DEFAULT_PINNED_MODEL = "us.anthropic.claude-sonnet-4-6"

# Bump when any shared prompt wording changes. Per-template versions below
# can move independently of this umbrella pin.
PROMPT_TEMPLATE_VERSION = "v1.0"

PROMPT_TEMPLATE_VERSIONS: dict[str, str] = {
    "report": "v1.0",
    "explanation": "v1.0",
    "report_draft": "v1.0",
    "docs_assistant": "v1.0",
    "chain_of_verification": "v1.0",
    "claim_verification": "v1.0",
}

_UNPINNED_ALIASES = frozenset({"latest", "current", "newest"})
_OUTPUT_INLINE_CHARS = 2_000
_GROUNDING_INLINE_CHARS = 8_000


def _reject_unpinned(model_id: str) -> None:
    mid = (model_id or "").strip()
    tail = mid.rsplit(":", 1)[-1].lower() if mid else ""
    if mid.lower() in _UNPINNED_ALIASES or tail in _UNPINNED_ALIASES:
        raise ValueError(
            f"BEDROCK_MODEL_ID must be a pinned model ID, not an alias ({model_id!r}). "
            "Set a concrete ID such as us.anthropic.claude-sonnet-4-6."
        )


def pinned_bedrock_model_id(explicit: Optional[str] = None) -> str:
    """
    Resolve the Bedrock model pin from ``explicit`` or ``BEDROCK_MODEL_ID``.

    Equivalent to BEDROCK_MODEL_VERSION = os.environ['BEDROCK_MODEL_ID'], but
    evaluated at call time and refused when the value is ``latest``.
    """
    raw = (explicit if explicit is not None else os.environ.get("BEDROCK_MODEL_ID") or "").strip()
    if not raw:
        raw = DEFAULT_PINNED_MODEL
    _reject_unpinned(raw)
    return raw


def bedrock_model_version(explicit: Optional[str] = None) -> str:
    """The model ID *is* the version pin (no separate :latest resolution)."""
    return pinned_bedrock_model_id(explicit)


def prompt_template_version(name: str) -> str:
    return PROMPT_TEMPLATE_VERSIONS.get(name, PROMPT_TEMPLATE_VERSION)


def guardrail_id() -> str:
    return (os.environ.get("BEDROCK_GUARDRAIL_ID") or "").strip()


def guardrail_version() -> str:
    gid = guardrail_id()
    if not gid:
        return ""
    return (os.environ.get("BEDROCK_GUARDRAIL_VERSION") or "DRAFT").strip()


def llm_version_manifest(
    prompt_template_name: str = "report",
    *,
    model_id: Optional[str] = None,
) -> dict[str, str]:
    """Call-time snapshot: model, prompt template, guardrail. Safe to put in audit JSON."""
    mid = pinned_bedrock_model_id(model_id)
    return {
        "model_id": mid,
        "model_version": mid,
        "prompt_template_name": prompt_template_name,
        "prompt_template_version": prompt_template_version(prompt_template_name),
        "guardrail_id": guardrail_id(),
        "guardrail_version": guardrail_version(),
        "prompt_template_version_umbrella": PROMPT_TEMPLATE_VERSION,
    }


def startup_version_lines() -> list[str]:
    """Human-readable pin dump for FastAPI / Cloud Run logs."""
    configured = bool((os.environ.get("BEDROCK_MODEL_ID") or "").strip())
    try:
        snap = llm_version_manifest("report")
        model_line = snap["model_id"]
    except ValueError as exc:
        model_line = f"INVALID PIN ({exc})"
        snap = {
            "guardrail_id": guardrail_id(),
            "guardrail_version": guardrail_version(),
        }
    templates = ", ".join(f"{k}={v}" for k, v in sorted(PROMPT_TEMPLATE_VERSIONS.items()))
    gid = snap.get("guardrail_id") or "(unset)"
    gver = snap.get("guardrail_version") or "(n/a)"
    source = "BEDROCK_MODEL_ID" if configured else f"default {DEFAULT_PINNED_MODEL}"
    return [
        "LLM version pin:",
        f"  model_id: {model_line}  [{source}]",
        f"  prompt templates: {templates}  (umbrella {PROMPT_TEMPLATE_VERSION})",
        f"  guardrail: id={gid} version={gver}",
    ]


def log_startup_versions() -> None:
    for line in startup_version_lines():
        print(line)


def compact_grounding(payload: Optional[dict]) -> dict[str, Any]:
    """Inline the deterministic payload when small; otherwise store a hash only."""
    src = payload or {}
    blob = json.dumps(src, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    if len(blob) <= _GROUNDING_INLINE_CHARS:
        return {"sha256": digest, "payload": src}
    return {"sha256": digest, "omitted": True, "chars": len(blob)}


def compact_output(text: Optional[str]) -> dict[str, Any]:
    """Never persist full images; hash the output and keep a short prefix."""
    raw = text or ""
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if len(raw) <= _OUTPUT_INLINE_CHARS:
        return {"sha256": digest, "text": raw, "chars": len(raw)}
    return {
        "sha256": digest,
        "text": raw[:_OUTPUT_INLINE_CHARS] + "…",
        "chars": len(raw),
        "truncated": True,
    }


def validator_snapshot(gate: Any = None) -> dict[str, Any]:
    """Prompts 1 (deterministic), 2 (Guardrails scores), 4 (chain-of-verification)."""
    if gate is None:
        return {
            "prompt_1_deterministic": {"skipped": True},
            "prompt_2_contextual_grounding": {"skipped": True},
            "prompt_4_chain_of_verification": {"skipped": True},
        }
    to_dict = getattr(gate, "to_dict", None)
    details = to_dict() if callable(to_dict) else {}
    p2 = getattr(gate, "contextual_grounding", None) or details.get("contextual_grounding")
    p4 = getattr(gate, "chain_of_verification", None) or details.get("chain_of_verification")
    return {
        "prompt_1_deterministic": {
            "passed": bool(getattr(gate, "passed", False)),
            "invented_numbers": list(getattr(gate, "invented_numbers", None) or []),
            "invented_entities": list(getattr(gate, "invented_entities", None) or []),
            "omitted_findings": list(getattr(gate, "omitted_findings", None) or []),
            "contradicted_claims": list(getattr(gate, "contradicted_claims", None) or []),
            "used_fallback": bool(getattr(gate, "used_fallback", False)),
            "regenerated": bool(getattr(gate, "regenerated", False)),
        },
        "prompt_2_contextual_grounding": p2 if isinstance(p2, dict) else {"skipped": True},
        "prompt_4_chain_of_verification": p4 if isinstance(p4, dict) else {"skipped": True},
    }


def audit_llm_generation(
    *,
    prompt_template_name: str,
    output_text: str,
    grounding_payload: Optional[dict] = None,
    gate: Any = None,
    user_id: str = "system",
    model_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    """Write one llm_generation audit row with the version pin + validator snapshot."""
    from src.inference.audit_log import log_llm_generation

    return log_llm_generation(
        user_id=user_id,
        prompt_template_name=prompt_template_name,
        grounding_payload=grounding_payload,
        gate=gate,
        output_text=output_text,
        model_id=model_id,
        extra=extra,
    )
