"""
Multimodal LLM client — Amazon Bedrock (HIPAA-eligible) or Google Gemini.

Provider selection:
    1. Explicit ``provider`` argument ("bedrock", "gemini", ...).
    2. ``LLM_PROVIDER`` env var.
    3. Auto: Bedrock when BEDROCK_MODEL_ID is set, else Gemini when
       GOOGLE_API_KEY is set.
"""
import io
import os
from typing import Any, Optional

# Default to newest generally-available Gemini
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

# All Gemini provider ids use the same Google backend; model_id selects the version
GEMINI_PROVIDER_IDS = frozenset({
    "gemini", "gemini_2_flash", "gemini_2_flash_lite", "gemini_2_pro",
    "gemini_15_flash", "gemini_15_pro",
})

BEDROCK_PROVIDER_IDS = frozenset({"bedrock", "aws", "aws_bedrock"})


def resolve_default_provider() -> str:
    """Pick the provider when a call site does not force one."""
    explicit = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if explicit:
        return explicit
    from src.llm.bedrock import is_bedrock_configured

    if is_bedrock_configured():
        return "bedrock"
    return "gemini"


def is_llm_configured() -> bool:
    """True when any generative provider is usable (Bedrock or Gemini)."""
    from src.llm.bedrock import is_bedrock_configured

    return is_bedrock_configured() or bool((os.environ.get("GOOGLE_API_KEY") or "").strip())


def get_llm_client(provider: Optional[str] = None, model_id: Optional[str] = None):
    """Return a client for the given provider. Uses model_id if provided, else default for provider."""
    provider = (provider or resolve_default_provider()).strip().lower()

    if provider in BEDROCK_PROVIDER_IDS or provider.startswith("bedrock"):
        from src.llm.bedrock import BedrockClient

        return BedrockClient(model_id=model_id)

    if provider in GEMINI_PROVIDER_IDS or provider.startswith("gemini"):
        import google.generativeai as genai
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_id or DEFAULT_GEMINI_MODEL)
        return model
    raise ValueError(f"Unknown provider: {provider}")


def generate_with_image(client, image_bytes_or_path, prompt: str, **kwargs):
    """Low-level image+text helper.

    Clinical report/explanation paths must not call this with raw MRI /
    DICOM pixels (FDA Non-Device CDS Criterion 1). Use
    ``generate_clinical_prose(..., visual_overlay=gradcam_png)`` instead.
    """
    # Bedrock client accepts raw bytes / paths / PIL images directly.
    from src.llm.bedrock import BedrockClient

    if isinstance(client, BedrockClient):
        response = client.generate_content([prompt, image_bytes_or_path], generation_config=kwargs)
        return response.text if response else ""

    if hasattr(client, "generate_content"):
        import PIL.Image
        if isinstance(image_bytes_or_path, str):
            img = PIL.Image.open(image_bytes_or_path)
        elif isinstance(image_bytes_or_path, bytes):
            img = PIL.Image.open(io.BytesIO(image_bytes_or_path))
        else:
            img = image_bytes_or_path
        response = client.generate_content([prompt, img], generation_config=kwargs)
        return response.text if response else ""
    return ""


def generate_clinical_prose(
    prompt: str,
    *,
    query: str,
    grounding_payload: dict,
    max_tokens: int = 200,
    visual_overlay: Any = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Generate report/explanation prose, using Bedrock contextual grounding when a
    guardrail is configured. Always returns (text, grounding_meta); meta is empty
    when Guardrails are unset so local dev keeps working.

    Clinical paths never attach image bytes. ``visual_overlay`` may be
    heatmap metadata ``{present, bbox_ids}`` only — PNG / tensors are dropped.
    """
    from src.llm.bedrock import BedrockClient, serialize_grounding_source
    from src.llm.cds_constraint import CDS_NARRATION_PREAMBLE
    from src.llm.pixel_leak import (
        PayloadRejected,
        REJECT_PIXEL_LEAK,
        heatmap_metadata_only,
        prompt_has_pixel_leak,
        validate_payload,
    )

    validate_payload(grounding_payload or {})
    overlay_meta = heatmap_metadata_only(visual_overlay)
    visual_overlay = None

    if CDS_NARRATION_PREAMBLE not in (prompt or ""):
        prompt = f"{CDS_NARRATION_PREAMBLE}\n\n{prompt}"
    if overlay_meta is not None:
        prompt = (
            f"{prompt}\n\nHeatmap metadata only (no image attached): "
            f"present={overlay_meta['present']} bbox_ids={overlay_meta['bbox_ids']}."
        )
    if prompt_has_pixel_leak(prompt):
        raise PayloadRejected(REJECT_PIXEL_LEAK, "prompt")

    meta: dict = {}
    try:
        client = get_llm_client(provider=provider, model_id=model_id)
    except Exception:
        return "", meta

    gen_cfg = {"max_output_tokens": max_tokens}
    use_grounded = isinstance(client, BedrockClient) and bool(getattr(client, "guardrail_id", ""))
    if use_grounded:
        try:
            source = serialize_grounding_source(grounding_payload)
            grounded = client.generate_grounded_content(
                query=query,
                grounding_source=source,
                prompt=prompt,
                generation_config=gen_cfg,
                image=None,
            )
            return (grounded.text or "").strip(), grounded.to_meta()
        except ValueError:
            raise
        except Exception:
            # Guardrail path failed; fall through to ungrounded generate.
            pass

    try:
        if hasattr(client, "generate_content"):
            resp = client.generate_content(prompt, generation_config=gen_cfg)
            text = (getattr(resp, "text", None) or "").strip()
        else:
            text = ""
    except Exception:
        text = ""
    return text, meta
