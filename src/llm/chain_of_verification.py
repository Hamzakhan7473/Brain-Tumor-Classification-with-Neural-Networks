"""
Chain-of-verification (CoV): decompose narrative into atomic claims and
check each against the deterministic grounding payload.

This is an optional second pass after Prompts 1–3 (deterministic gate,
Guardrails contextual grounding, structured narrative slots). It targets
subtler unfaithfulness that entity/number matching can miss — e.g. a
numbers-correct sentence that misstates severity or clinical significance.

Enable with ENABLE_CHAIN_OF_VERIFICATION=true. Default off (dev). Recommended
on for pilot/production. CONTRADICTED claims are Tier 0 (same handling as
Prompt 1). NOT_ADDRESSED_BY_PAYLOAD is a human-review warning, not a hard fail.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from src.inference.audit_log import log_report_draft_event

ClaimStatus = Literal["SUPPORTED", "CONTRADICTED", "NOT_ADDRESSED_BY_PAYLOAD"]
CompleteFn = Callable[..., str]

_TRUE = {"1", "true", "yes", "on"}
_STATUS_ORDER = ("CONTRADICTED", "SUPPORTED", "NOT_ADDRESSED_BY_PAYLOAD")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

CLAIMS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Independent factual claims, one per item.",
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

VERDICT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["SUPPORTED", "CONTRADICTED", "NOT_ADDRESSED_BY_PAYLOAD"],
        },
        "rationale": {"type": "string"},
    },
    "required": ["status"],
    "additionalProperties": False,
}


@dataclass
class ClaimVerification:
    claim: str
    status: ClaimStatus
    rationale: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"claim": self.claim, "status": self.status, "rationale": self.rationale}


@dataclass
class ChainOfVerificationResult:
    claims: list[ClaimVerification] = field(default_factory=list)
    passed: bool = True
    contradicted: list[str] = field(default_factory=list)
    not_addressed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "human_review_required": bool(self.not_addressed),
            "tier_0_failure": not self.passed,
            "claims": [c.to_dict() for c in self.claims],
            "contradicted_claims": list(self.contradicted),
            "not_addressed_claims": list(self.not_addressed),
        }


def chain_of_verification_enabled() -> bool:
    return (os.environ.get("ENABLE_CHAIN_OF_VERIFICATION") or "").strip().lower() in _TRUE


def complete_text(
    prompt: str,
    max_tokens: int = 256,
    *,
    json_schema: Optional[dict] = None,
    tool_name: str = "structured_result",
) -> str:
    """
    Single LLM completion used by decompose/verify.

    Tests patch this symbol so CoV can be exercised with zero network.
    """
    try:
        from src.llm.bedrock import BedrockClient
        from src.llm.client import get_llm_client

        client = get_llm_client()
    except Exception:
        return ""
    gen_cfg = {"max_output_tokens": max_tokens, "temperature": 0}
    try:
        if isinstance(client, BedrockClient) and json_schema is not None:
            data = client.generate_tool_json(
                prompt,
                json_schema,
                tool_name=tool_name,
                generation_config=gen_cfg,
            )
            return json.dumps(data, ensure_ascii=False)
        if hasattr(client, "generate_content"):
            resp = client.generate_content(prompt, generation_config=gen_cfg)
            return (getattr(resp, "text", None) or "").strip()
    except Exception:
        return ""
    return ""


def decompose_into_claims(
    generated_text: str,
    *,
    complete_fn: Optional[CompleteFn] = None,
) -> list[str]:
    """
    Split narrative text into independent factual claims.

    Prefers a cheap constrained LLM call; falls back to sentence splitting
    when the model returns nothing parseable.
    """
    text = (generated_text or "").strip()
    if not text:
        return []
    raw = ""
    try:
        raw = _call_complete(
            complete_fn or complete_text,
            _decompose_prompt(text),
            max_tokens=400,
            json_schema=CLAIMS_JSON_SCHEMA,
            tool_name="claims_list",
        )
    except Exception:
        raw = ""
    claims = _parse_claim_list(raw)
    if claims:
        return claims
    return _heuristic_decompose(text)


def verify_claim(
    claim: str,
    grounding_payload: dict,
    *,
    complete_fn: Optional[CompleteFn] = None,
) -> ClaimVerification:
    """
    Classify one claim strictly against the grounding payload.

    Status: SUPPORTED | CONTRADICTED | NOT_ADDRESSED_BY_PAYLOAD.
    Does not use general medical knowledge — only the provided payload.
    """
    claim = (claim or "").strip()
    if not claim:
        return ClaimVerification(claim="", status="NOT_ADDRESSED_BY_PAYLOAD", rationale="empty claim")
    raw = ""
    try:
        raw = _call_complete(
            complete_fn or complete_text,
            _verify_prompt(claim, grounding_payload or {}),
            max_tokens=80,
            json_schema=VERDICT_JSON_SCHEMA,
            tool_name="claim_verdict",
        )
    except Exception:
        raw = ""
    status, rationale = _parse_verdict(raw)
    return ClaimVerification(claim=claim, status=status, rationale=rationale)


def run_chain_of_verification(
    generated_text: str,
    grounding_payload: dict,
    *,
    user_id: str = "system",
    complete_fn: Optional[CompleteFn] = None,
) -> ChainOfVerificationResult:
    """Decompose, verify each claim, and write the full audit trail."""
    claims_text = decompose_into_claims(generated_text, complete_fn=complete_fn)
    verifications: list[ClaimVerification] = []
    for claim in claims_text:
        verifications.append(verify_claim(claim, grounding_payload, complete_fn=complete_fn))
    contradicted = [v.claim for v in verifications if v.status == "CONTRADICTED"]
    not_addressed = [v.claim for v in verifications if v.status == "NOT_ADDRESSED_BY_PAYLOAD"]
    result = ChainOfVerificationResult(
        claims=verifications,
        passed=not contradicted,
        contradicted=contradicted,
        not_addressed=not_addressed,
    )
    log_report_draft_event(
        event_type=(
            "llm_chain_of_verification_failed"
            if contradicted
            else "llm_chain_of_verification_review"
            if not_addressed
            else "llm_chain_of_verification"
        ),
        user_id=user_id,
        payload={
            **result.to_dict(),
            "text": (generated_text or "")[:500],
            "note": (
                "Tier 0: CONTRADICTED claims fail the gate (same as Prompt 1). "
                "NOT_ADDRESSED_BY_PAYLOAD is a human-review warning, not a hard failure."
            ),
        },
    )
    return result


def apply_chain_of_verification(
    generated_text: str,
    grounding_payload: dict,
    *,
    user_id: str = "system",
    complete_fn: Optional[CompleteFn] = None,
) -> Optional[ChainOfVerificationResult]:
    """No-op when the feature flag is off — zero LLM calls."""
    if not chain_of_verification_enabled():
        return None
    try:
        return run_chain_of_verification(
            generated_text,
            grounding_payload,
            user_id=user_id,
            complete_fn=complete_fn,
        )
    except Exception as exc:
        log_report_draft_event(
            event_type="llm_chain_of_verification_error",
            user_id=user_id,
            payload={"error": str(exc)[:400], "text": (generated_text or "")[:300]},
        )
        return None


def _call_complete(
    fn: CompleteFn,
    prompt: str,
    *,
    max_tokens: int,
    json_schema: Optional[dict],
    tool_name: str,
) -> str:
    try:
        return fn(
            prompt,
            max_tokens=max_tokens,
            json_schema=json_schema,
            tool_name=tool_name,
        )
    except TypeError:
        try:
            return fn(prompt, max_tokens=max_tokens)
        except TypeError:
            return fn(prompt)


def _decompose_prompt(text: str) -> str:
    return (
        "Split the clinical narrative into independent factual claims. "
        "One claim per item. Do not add information that is not in the narrative. "
        "Do not merge unrelated assertions.\n\n"
        f"NARRATIVE:\n{text}\n"
    )


def _verify_prompt(claim: str, payload: dict) -> str:
    from src.llm.bedrock import serialize_grounding_source

    try:
        source = serialize_grounding_source(payload)
    except ValueError:
        source = json.dumps(payload, default=str, ensure_ascii=False)[:8000]
    return (
        "You are a clinical faithfulness checker. Classify the CLAIM using ONLY "
        "the GROUNDING PAYLOAD. Do not use general medical knowledge.\n\n"
        "SUPPORTED — the payload entails the claim (including numbers, severity, "
        "and clinical significance).\n"
        "CONTRADICTED — the payload contradicts the claim (wrong severity, wrong "
        "significance, wrong finding, or a characterization the data do not support).\n"
        "NOT_ADDRESSED_BY_PAYLOAD — the payload neither supports nor contradicts "
        "(e.g. generic follow-up advice or survey anatomy).\n\n"
        f"GROUNDING PAYLOAD:\n{source}\n\n"
        f"CLAIM:\n{claim}\n"
    )


def _heuristic_decompose(text: str) -> list[str]:
    parts = [p.strip(" \t-•") for p in _SENTENCE_SPLIT.split((text or "").strip()) if p.strip()]
    return [p for p in parts if p]


def _parse_claim_list(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    parsed: Any = None
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("claims"), list):
        items = parsed["claims"]
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = [ln.strip(" \t-•0123456789.)") for ln in text.splitlines() if ln.strip()]
        items = [x for x in items if x and x.upper() not in {"CLAIMS", "CLAIM"}]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        claim = item.strip()
        if len(claim) < 3 or claim in seen:
            continue
        seen.add(claim)
        out.append(claim)
    return out


def _parse_verdict(raw: str) -> tuple[ClaimStatus, str]:
    text = (raw or "").strip()
    rationale = ""
    status: Optional[ClaimStatus] = None
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            rationale = str(data.get("rationale") or "")
            status = _match_status(str(data.get("status") or ""))
    if status is None:
        status = _match_status(text)
    if status is None:
        return "NOT_ADDRESSED_BY_PAYLOAD", rationale or "unparseable verifier output"
    return status, rationale


def _match_status(text: str) -> Optional[ClaimStatus]:
    blob = (text or "").upper().replace(" ", "_")
    for status in _STATUS_ORDER:
        if status in blob:
            return status  # type: ignore[return-value]
    return None
