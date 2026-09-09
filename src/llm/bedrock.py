"""
Amazon Bedrock LLM client (Converse API).

Exposes the same duck-typed interface as the Gemini client used across the
codebase — ``generate_content(prompt_or_parts, generation_config=...)``
returning an object with ``.text`` — so existing call sites work unchanged
when ``get_llm_client`` returns a Bedrock client.

Configuration (env):
    BEDROCK_MODEL_ID           e.g. "us.anthropic.claude-sonnet-4-6"
    AWS_REGION                 Bedrock region (default us-east-1)
    BEDROCK_GUARDRAIL_ID       optional Guardrail identifier
    BEDROCK_GUARDRAIL_VERSION  optional Guardrail version (default "DRAFT")
    BEDROCK_GROUNDING_THRESHOLD   contextual grounding (default 0.75)
    BEDROCK_RELEVANCE_THRESHOLD   contextual relevance (default 0.75)

AWS credentials resolve through the standard boto3 chain (env vars, shared
config, instance/task role). Bedrock is HIPAA-eligible under the AWS BAA;
the Gemini consumer API path is kept only as a research fallback.

Model IDs are pinned via BEDROCK_MODEL_ID (see src/llm/versions.py) and are
never resolved to the alias "latest". Prompt template versions live in the
same manifest and are written into every llm_generation audit row.
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel

from src.llm.versions import (
    DEFAULT_PINNED_MODEL,
    PROMPT_TEMPLATE_VERSION,
    pinned_bedrock_model_id,
)

DEFAULT_BEDROCK_MODEL = DEFAULT_PINNED_MODEL


def bedrock_model_version() -> str:
    """BEDROCK_MODEL_VERSION = env BEDROCK_MODEL_ID, resolved at call time (never 'latest')."""
    return pinned_bedrock_model_id()


def prompt_template_version() -> str:
    """PROMPT_TEMPLATE_VERSION pin (bump in src/llm/versions.py when prompts change)."""
    return PROMPT_TEMPLATE_VERSION

# Bedrock contextual-grounding qualifier limits (Converse / ApplyGuardrail).
GROUNDING_SOURCE_MAX_CHARS = 100_000
QUERY_MAX_CHARS = 1_000
GUARDED_RESPONSE_MAX_CHARS = 5_000

_COMPACT_PAYLOAD_KEYS = (
    "label",
    "prediction",
    "predicted_label",
    "confidence",
    "model_confidence",
    "probabilities",
    "class_probabilities",
    "measurements",
    "wmh",
    "regions",
    "severity",
    "severity_grade",
)


def is_bedrock_configured() -> bool:
    """Bedrock is opted in by setting BEDROCK_MODEL_ID (credentials come from the boto3 chain)."""
    return bool((os.environ.get("BEDROCK_MODEL_ID") or "").strip())


def is_bedrock_guardrail_configured() -> bool:
    return bool((os.environ.get("BEDROCK_GUARDRAIL_ID") or "").strip())


def grounding_threshold() -> float:
    try:
        return float(os.environ.get("BEDROCK_GROUNDING_THRESHOLD") or 0.75)
    except ValueError:
        return 0.75


def relevance_threshold() -> float:
    try:
        return float(os.environ.get("BEDROCK_RELEVANCE_THRESHOLD") or 0.75)
    except ValueError:
        return 0.75


class BedrockResponse:
    """Minimal response shim matching the Gemini response surface we rely on."""

    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage_metadata = _UsageShim(usage or {})


class _UsageShim:
    def __init__(self, usage: dict):
        self.total_token_count = int(usage.get("totalTokens") or 0)
        self.total_tokens = self.total_token_count


@dataclass
class GroundedResponse:
    """Converse result plus optional Guardrail contextual-grounding scores."""

    text: str
    grounding_score: Optional[float] = None
    relevance_score: Optional[float] = None
    grounding_threshold: Optional[float] = None
    relevance_threshold: Optional[float] = None
    below_threshold: bool = False
    human_review: bool = False
    usage: dict = field(default_factory=dict)
    raw_trace: Optional[dict] = None

    def to_meta(self) -> dict[str, Any]:
        return {
            "grounding_score": self.grounding_score,
            "relevance_score": self.relevance_score,
            "grounding_threshold": self.grounding_threshold,
            "relevance_threshold": self.relevance_threshold,
            "below_threshold": self.below_threshold,
            "human_review": self.human_review,
        }


def serialize_grounding_source(payload: dict, max_chars: int = GROUNDING_SOURCE_MAX_CHARS) -> str:
    """
    Compact JSON of the deterministic measurement/classification payload.

    Raises ValueError if the compact form still exceeds Bedrock's 100k-char cap
    (callers must pass the relevant subset, not a whole case object).
    """
    compact: dict[str, Any] = {}
    src = payload or {}
    for key in _COMPACT_PAYLOAD_KEYS:
        if key in src and src[key] is not None:
            compact[key] = src[key]
    if "measurements" in compact and isinstance(compact["measurements"], list):
        compact["measurements"] = [
            {k: m.get(k) for k in ("id", "label", "value", "unit", "severity") if k in m}
            for m in compact["measurements"]
            if isinstance(m, dict)
        ]
    if "wmh" in compact and isinstance(compact["wmh"], dict):
        wmh = compact["wmh"]
        compact["wmh"] = {
            k: wmh[k]
            for k in (
                "volume_cc",
                "lesion_voxels",
                "volume_cc_periventricular",
                "volume_cc_deep_subcortical",
                "volume_cc_infratentorial",
                "severity_grade",
                "risk_level",
                "age_matched_percentile",
            )
            if k in wmh
        }
    text = json.dumps(compact, default=str, separators=(",", ":"), ensure_ascii=False)
    if len(text) > max_chars:
        raise ValueError(
            f"grounding_source is {len(text)} characters; Bedrock allows at most {max_chars}. "
            "Serialize only the relevant measurement/classification subset, not the full case."
        )
    return text


def truncate_query(query: str, max_chars: int = QUERY_MAX_CHARS) -> str:
    q = (query or "").strip()
    if len(q) <= max_chars:
        return q
    return q[: max_chars - 1].rstrip() + "…"


def parse_contextual_grounding(resp: Optional[dict]) -> dict[str, Optional[float]]:
    """Extract GROUNDING / RELEVANCE scores (and thresholds) from a Converse trace."""
    out: dict[str, Optional[float]] = {
        "grounding_score": None,
        "relevance_score": None,
        "grounding_threshold": None,
        "relevance_threshold": None,
    }
    filters: list[dict] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            policy = obj.get("contextualGroundingPolicy") or obj.get("contextual_grounding_policy")
            if isinstance(policy, dict) and isinstance(policy.get("filters"), list):
                filters.extend(f for f in policy["filters"] if isinstance(f, dict))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(resp or {})
    for item in filters:
        kind = str(item.get("type") or "").upper()
        score = item.get("score")
        threshold = item.get("threshold")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        try:
            thr_f = float(threshold) if threshold is not None else None
        except (TypeError, ValueError):
            thr_f = None
        if kind == "GROUNDING":
            out["grounding_score"] = score_f
            out["grounding_threshold"] = thr_f
        elif kind == "RELEVANCE":
            out["relevance_score"] = score_f
            out["relevance_threshold"] = thr_f
    return out


def _to_image_block(part: Any) -> Optional[dict]:
    """Convert bytes / file path / PIL image into a Converse image content block."""
    raw: Optional[bytes] = None
    fmt = "png"
    if isinstance(part, bytes):
        raw = part
        fmt = _sniff_format(part)
    elif isinstance(part, str) and os.path.exists(part):
        with open(part, "rb") as f:
            raw = f.read()
        fmt = _sniff_format(raw)
    elif hasattr(part, "save"):  # PIL image
        buf = io.BytesIO()
        part.save(buf, format="PNG")
        raw = buf.getvalue()
    if raw is None:
        return None
    return {"image": {"format": fmt, "source": {"bytes": raw}}}


def _sniff_format(raw: bytes) -> str:
    if raw[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return "png"


def _guard_text_block(text: str, qualifier: str) -> dict:
    return {
        "guardContent": {
            "text": {
                "text": text,
                "qualifiers": [qualifier],
            }
        }
    }


def _tool_json_schema(schema: type[BaseModel]) -> dict:
    """JSON Schema fragment for Converse toolSpec.inputSchema.json."""
    raw = schema.model_json_schema()
    for key in ("$defs", "definitions", "$schema"):
        raw.pop(key, None)
    return raw


class BedrockClient:
    """Thin wrapper over the Bedrock Converse API with optional Guardrails."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None,
    ):
        import boto3  # imported lazily so the dependency stays optional

        self.model_id = pinned_bedrock_model_id(model_id)
        self.guardrail_id = (guardrail_id or os.environ.get("BEDROCK_GUARDRAIL_ID") or "").strip()
        self.guardrail_version = (
            guardrail_version or os.environ.get("BEDROCK_GUARDRAIL_VERSION") or "DRAFT"
        ).strip()
        self.last_grounding_meta: dict[str, Any] = {}
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region or os.environ.get("AWS_REGION") or "us-east-1",
        )

    def _inference_config(self, generation_config: Optional[dict]) -> dict[str, Any]:
        cfg = generation_config or {}
        inference_config: dict[str, Any] = {
            "maxTokens": int(cfg.get("max_output_tokens") or cfg.get("maxTokens") or 1024),
        }
        if cfg.get("temperature") is not None:
            inference_config["temperature"] = float(cfg["temperature"])
        if cfg.get("top_p") is not None:
            inference_config["topP"] = float(cfg["top_p"])
        return inference_config

    def _extract_text(self, resp: Optional[dict]) -> str:
        blocks = (((resp or {}).get("output") or {}).get("message") or {}).get("content") or []
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()

    def generate_content(self, prompt_or_parts: Any, generation_config: Optional[dict] = None):
        """Accepts a string prompt or a [prompt, image] list (Gemini-style parts)."""
        parts = prompt_or_parts if isinstance(prompt_or_parts, (list, tuple)) else [prompt_or_parts]
        content: list[dict] = []
        for part in parts:
            if isinstance(part, str) and not os.path.exists(part):
                content.append({"text": part})
                continue
            block = _to_image_block(part)
            if block is not None:
                content.append(block)
            elif isinstance(part, str):
                content.append({"text": part})
        if not content:
            return BedrockResponse("")

        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": self._inference_config(generation_config),
        }
        if self.guardrail_id:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
            }

        resp = self._client.converse(**kwargs)
        return BedrockResponse(self._extract_text(resp), usage=(resp or {}).get("usage"))

    def generate_grounded_content(
        self,
        query: str,
        grounding_source: str,
        prompt: str,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None,
        generation_config: Optional[dict] = None,
        image: Any = None,
    ) -> GroundedResponse:
        """
        Converse with contextual-grounding qualifiers.

        Content blocks:
          - grounding_source → qualifiers=["grounding_source"]  (max 100k chars)
          - query            → qualifiers=["query"]             (max 1k chars)
          - prompt           → ordinary text, no qualifier
        Guardrail config is attached only when an id is set (constructor env or argument).
        Scores are advisory: they never override the deterministic clinical validator.
        """
        source = grounding_source if isinstance(grounding_source, str) else str(grounding_source or "")
        if len(source) > GROUNDING_SOURCE_MAX_CHARS:
            raise ValueError(
                f"grounding_source is {len(source)} characters; Bedrock allows at most "
                f"{GROUNDING_SOURCE_MAX_CHARS}. Serialize only the relevant measurement subset."
            )
        query_text = truncate_query(query)
        gid = (guardrail_id if guardrail_id is not None else self.guardrail_id or "").strip()
        gver = (guardrail_version if guardrail_version is not None else self.guardrail_version or "DRAFT").strip()

        content: list[dict] = [
            _guard_text_block(source, "grounding_source"),
            _guard_text_block(query_text, "query"),
            {"text": prompt or ""},
        ]
        if image is not None:
            # Overlay only — callers must not pass raw diagnostic pixels
            # (FDA Non-Device CDS Criterion 1). See src/llm/cds_constraint.py.
            from src.llm.cds_constraint import MODEL_OVERLAY_CAPTION

            content.append({"text": MODEL_OVERLAY_CAPTION})
            block = _to_image_block(image)
            if block is not None:
                content.append(block)

        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": self._inference_config(generation_config),
        }
        if gid:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": gid,
                "guardrailVersion": gver or "DRAFT",
                "trace": "enabled",
            }

        resp = self._client.converse(**kwargs) or {}
        scores = parse_contextual_grounding(resp)
        g_thr = scores["grounding_threshold"]
        r_thr = scores["relevance_threshold"]
        if g_thr is None:
            g_thr = grounding_threshold()
        if r_thr is None:
            r_thr = relevance_threshold()
        g_score = scores["grounding_score"]
        r_score = scores["relevance_score"]
        below = False
        if g_score is not None and g_score < g_thr:
            below = True
        if r_score is not None and r_score < r_thr:
            below = True
        return GroundedResponse(
            text=self._extract_text(resp),
            grounding_score=g_score,
            relevance_score=r_score,
            grounding_threshold=g_thr,
            relevance_threshold=r_thr,
            below_threshold=below,
            human_review=below,
            usage=resp.get("usage") or {},
            raw_trace=resp.get("trace") if isinstance(resp.get("trace"), dict) else None,
        )

    def generate_tool_json(
        self,
        prompt: str,
        json_schema: dict,
        tool_name: str = "structured_result",
        generation_config: Optional[dict] = None,
    ) -> dict:
        """
        Force a JSON object via Converse strict tool use.

        Unlike generate_structured_narrative this does not apply the
        text-only / no-numeric-literal narrative checks — callers such as
        chain-of-verification may need to mention payload numbers.
        """
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": [{"text": prompt or ""}]}],
            "inferenceConfig": self._inference_config(generation_config),
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool_name,
                            "description": "Return the structured result only.",
                            "inputSchema": {"json": json_schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": tool_name}},
            },
        }
        if self.guardrail_id:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
            }
        resp = self._client.converse(**kwargs) or {}
        data = _extract_tool_input(resp, tool_name)
        if not isinstance(data, dict):
            raise ValueError("Model did not return structured tool JSON.")
        return data

    def generate_structured_narrative(
        self,
        grounding_payload: dict,
        schema: type[BaseModel],
        prompt: Optional[str] = None,
        query: Optional[str] = None,
        generation_config: Optional[dict] = None,
        tool_name: str = "report_narrative",
    ) -> BaseModel:
        """
        Force Claude into a text-only Pydantic schema via Converse strict tool use.

        Numeric measurement fields must not appear in ``schema``; they are merged
        from ``grounding_payload`` at render time. Raises StructuredNarrativeError
        if the model emits a numeric field or a numeric literal in a text field.
        """
        from src.llm.narrative_schema import (
            StructuredNarrativeError,
            assert_schema_text_only,
            validate_parsed_narrative,
        )

        assert_schema_text_only(schema)
        source = serialize_grounding_source(grounding_payload or {})
        slot_ids = []
        for m in (grounding_payload or {}).get("measurements") or []:
            if isinstance(m, dict) and m.get("id"):
                slot_ids.append(str(m["id"]))
        slot_hint = ", ".join(f"{{{sid}}}" for sid in slot_ids) or "(none)"
        instruction = prompt or (
            "Fill the report_narrative tool. Write clinical prose only. "
            "Never write numeric literals. Insert quantities only as placeholders "
            f"from this slot list: {slot_hint}."
        )
        user_query = truncate_query(query or "Draft the report narrative from the grounding measurements.")
        json_schema = _tool_json_schema(schema)
        content: list[dict] = [
            _guard_text_block(source, "grounding_source"),
            _guard_text_block(user_query, "query"),
            {"text": instruction},
        ]
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": self._inference_config(generation_config),
            # Strict tool use: Claude must fill this schema. Numeric fields are
            # forbidden by the schema itself (text strings only).
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool_name,
                            "description": (
                                "Narrative-only radiology fields. All properties are strings. "
                                "Do not add measurement numbers; use {slot_id} placeholders."
                            ),
                            "inputSchema": {"json": json_schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": tool_name}},
            },
        }
        if self.guardrail_id:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
                "trace": "enabled",
            }
        resp = self._client.converse(**kwargs) or {}
        scores = parse_contextual_grounding(resp)
        g_score = scores.get("grounding_score")
        r_score = scores.get("relevance_score")
        g_thr = scores.get("grounding_threshold")
        if g_thr is None:
            g_thr = grounding_threshold()
        r_thr = scores.get("relevance_threshold")
        if r_thr is None:
            r_thr = relevance_threshold()
        below = False
        if g_score is not None and g_score < g_thr:
            below = True
        if r_score is not None and r_score < r_thr:
            below = True
        self.last_grounding_meta = GroundedResponse(
            text="",
            grounding_score=g_score,
            relevance_score=r_score,
            grounding_threshold=g_thr,
            relevance_threshold=r_thr,
            below_threshold=below,
            human_review=below,
        ).to_meta()
        data = _extract_tool_input(resp, tool_name)
        if data is None:
            raise StructuredNarrativeError("Model did not return structured tool input for the narrative schema.")
        return validate_parsed_narrative(data, schema)


def _extract_tool_input(resp: dict, tool_name: str) -> Optional[dict]:
    blocks = (((resp or {}).get("output") or {}).get("message") or {}).get("content") or []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        tu = block.get("toolUse") or block.get("tool_use")
        if isinstance(tu, dict):
            if tool_name and tu.get("name") not in (None, tool_name):
                continue
            raw = tu.get("input")
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        text = block.get("text")
        if isinstance(text, str) and text.strip().startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None
