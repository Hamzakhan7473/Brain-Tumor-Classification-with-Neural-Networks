"""
Amazon Bedrock LLM client (Converse API).

Exposes the same duck-typed interface as the Gemini client used across the
codebase — ``generate_content(prompt_or_parts, generation_config=...)``
returning an object with ``.text`` — so existing call sites work unchanged
when ``get_llm_client`` returns a Bedrock client.

Configuration (env):
    BEDROCK_MODEL_ID           e.g. "us.anthropic.claude-sonnet-4-20250514-v1:0"
    AWS_REGION                 Bedrock region (default us-east-1)
    BEDROCK_GUARDRAIL_ID       optional Guardrail identifier
    BEDROCK_GUARDRAIL_VERSION  optional Guardrail version (default "DRAFT")

AWS credentials resolve through the standard boto3 chain (env vars, shared
config, instance/task role). Bedrock is HIPAA-eligible under the AWS BAA;
the Gemini consumer API path is kept only as a research fallback.
"""
from __future__ import annotations

import io
import os
from typing import Any, Optional

DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"


def is_bedrock_configured() -> bool:
    """Bedrock is opted in by setting BEDROCK_MODEL_ID (credentials come from the boto3 chain)."""
    return bool((os.environ.get("BEDROCK_MODEL_ID") or "").strip())


class BedrockResponse:
    """Minimal response shim matching the Gemini response surface we rely on."""

    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage_metadata = _UsageShim(usage or {})


class _UsageShim:
    def __init__(self, usage: dict):
        self.total_token_count = int(usage.get("totalTokens") or 0)
        self.total_tokens = self.total_token_count


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

        self.model_id = (model_id or os.environ.get("BEDROCK_MODEL_ID") or DEFAULT_BEDROCK_MODEL).strip()
        self.guardrail_id = (guardrail_id or os.environ.get("BEDROCK_GUARDRAIL_ID") or "").strip()
        self.guardrail_version = (
            guardrail_version or os.environ.get("BEDROCK_GUARDRAIL_VERSION") or "DRAFT"
        ).strip()
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region or os.environ.get("AWS_REGION") or "us-east-1",
        )

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

        cfg = generation_config or {}
        inference_config: dict[str, Any] = {
            "maxTokens": int(cfg.get("max_output_tokens") or cfg.get("maxTokens") or 1024),
        }
        if cfg.get("temperature") is not None:
            inference_config["temperature"] = float(cfg["temperature"])
        if cfg.get("top_p") is not None:
            inference_config["topP"] = float(cfg["top_p"])

        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": inference_config,
        }
        if self.guardrail_id:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
            }

        resp = self._client.converse(**kwargs)
        blocks = (((resp or {}).get("output") or {}).get("message") or {}).get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()
        return BedrockResponse(text, usage=resp.get("usage"))
