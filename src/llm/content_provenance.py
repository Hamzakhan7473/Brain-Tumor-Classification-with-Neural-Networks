"""AI-content provenance snapshot for API responses and the clinician UI."""
from __future__ import annotations

from typing import Any, Literal, Optional

from src.llm.versions import llm_version_manifest, prompt_template_version

ValidatorStatus = Literal["passed", "warnings", "failed"]


def generated_by_slug(model_id: str) -> str:
    """us.anthropic.claude-sonnet-4-6 → claude-sonnet-4-6 (UI/API provenance id)."""
    mid = (model_id or "").strip()
    for prefix in ("us.anthropic.", "anthropic.", "us."):
        if mid.startswith(prefix):
            mid = mid[len(prefix) :]
            break
    if ":" in mid:
        mid = mid.split(":", 1)[0]
    return mid or "claude-sonnet-4-6"


def build_content_provenance(
    *,
    prompt_template_name: str,
    gate: Any = None,
    model_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Provenance block for /report and report drafts.

    validator_status is informational for the clinician. Prompt 1 still
    withholds unvalidated LLM prose; this label does not replace that gate.
    """
    snap = llm_version_manifest(prompt_template_name, model_id=model_id)
    status, warnings = _status_from_gate(gate)
    gmeta = getattr(gate, "contextual_grounding", None) if gate is not None else None
    if not isinstance(gmeta, dict):
        gmeta = {}
    score = gmeta.get("grounding_score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    return {
        "generated_by": generated_by_slug(snap["model_id"]),
        "prompt_template_version": snap.get("prompt_template_version")
        or prompt_template_version(prompt_template_name),
        "grounding_score": score_f,
        "validator_status": status,
        "validator_warnings": warnings,
    }


def _status_from_gate(gate: Any) -> tuple[ValidatorStatus, list[str]]:
    if gate is None:
        return "passed", []
    warnings: list[str] = []
    passed = bool(getattr(gate, "passed", True))
    used_fallback = bool(getattr(gate, "used_fallback", False))
    if used_fallback:
        warnings.append("template_fallback")
    if getattr(gate, "regenerated", False):
        warnings.append("regenerated_after_gate")
    unaddressed = list(getattr(gate, "unaddressed_claims", None) or [])
    if unaddressed:
        warnings.append("claims_not_addressed_by_payload")
    gmeta = getattr(gate, "contextual_grounding", None)
    if isinstance(gmeta, dict) and (gmeta.get("human_review") or gmeta.get("below_threshold")):
        warnings.append("contextual_grounding_review")
    if not passed and not used_fallback:
        return "failed", warnings
    if warnings:
        return "warnings", warnings
    return "passed", []
