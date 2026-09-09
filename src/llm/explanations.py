"""
Narrate deterministic CNN / U-Net findings in plain language.

FDA Non-Device CDS Criterion 1 — software must not acquire, process, or
analyze a medical image to remain non-device CDS. The Keras CNN and 3D
U-Net do all image analysis. Claude only narrates their structured
output (and, optionally, a Grad-CAM / saliency heatmap that is itself
a visualization of that output). Never attach raw diagnostic scan
bytes to the LLM call. Reintroducing raw-image-to-LLM interpretation
would be a regulatory classification change, not a prompt tweak.
"""
from typing import Any, Optional

from .cds_constraint import CDS_NARRATION_PREAMBLE, MODEL_OVERLAY_CAPTION
from .client import generate_clinical_prose
from .validation import (
    ValidationResult,
    enforce_clinical_gate,
    grounding_from_prediction,
    log_grounding_assessment,
)


def _explanation_provenance(gate: ValidationResult) -> dict[str, Any]:
    from src.llm.content_provenance import build_content_provenance

    return build_content_provenance(prompt_template_name="explanation", gate=gate)


def _template_explanation(model_prediction: str) -> str:
    return (
        f"Model prediction: {model_prediction}. "
        "LLM explanation withheld after the clinical faithfulness/recall gate. "
        "This template restates the classifier output only."
    )


def _explanation_prompt(model_prediction: str, payload: dict[str, Any], *, has_overlay: bool) -> str:
    overlay_note = (
        f"{MODEL_OVERLAY_CAPTION}\n\n"
        if has_overlay
        else "No image is attached. Do not invent visual findings.\n\n"
    )
    return (
        f"{CDS_NARRATION_PREAMBLE}\n\n"
        f"{overlay_note}"
        "Explain in plain language why the deterministic model produced this result "
        "and what the structured measurements mean. "
        "You MUST mention the model prediction class. "
        "Do NOT name findings or anatomy that are not present in the structured data. "
        "Do not diagnose. Do not describe what a scan 'looks like'.\n\n"
        f"Structured model output:\n"
        f"Model prediction: {model_prediction}\n"
        f"Confidence: {payload.get('confidence')}\n"
        f"Class probabilities: {payload.get('probabilities') or {}}"
    )


def explain_image(
    model_prediction: str,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    *,
    confidence: Optional[float] = None,
    probabilities: Optional[dict] = None,
    visual_overlay: Optional[dict] = None,
) -> tuple[str, ValidationResult, dict[str, Any]]:
    """Narrate a classifier/U-Net result. Does not accept raw scan pixels.

    ``visual_overlay`` is heatmap metadata ``{present, bbox_ids}`` only.

    Returns (text, clinical_gate, provenance).
    """
    conf = float(confidence) if confidence is not None else 1.0
    payload = grounding_from_prediction(model_prediction, conf, probabilities)
    overlay = visual_overlay if visual_overlay else None
    prompt = _explanation_prompt(model_prediction, payload, has_overlay=overlay is not None)
    fallback = _template_explanation(model_prediction)

    try:
        raw, gmeta = generate_clinical_prose(
            prompt,
            query="Narrate the structured model prediction for a clinician.",
            grounding_payload=payload,
            max_tokens=400,
            visual_overlay=overlay,
            provider=provider,
            model_id=model_id,
        )
    except Exception:
        raw, gmeta = "", {}

    def _retry(corrective: str) -> str:
        retry_text, retry_meta = generate_clinical_prose(
            prompt + "\n\n" + corrective,
            query="Rewrite the model-output narration after a safety-gate rejection.",
            grounding_payload=payload,
            max_tokens=400,
            visual_overlay=overlay,
            provider=provider,
            model_id=model_id,
        )
        if retry_meta:
            gmeta.update(retry_meta)
        return retry_text

    if not raw.strip():
        gate = ValidationResult(passed=True, used_fallback=True, contextual_grounding=gmeta or None)
        log_grounding_assessment(gmeta, gate)
        from src.llm.versions import audit_llm_generation

        audit_llm_generation(
            prompt_template_name="explanation",
            output_text=fallback,
            grounding_payload=payload,
            gate=gate,
        )
        return fallback, gate, _explanation_provenance(gate)

    text, gate = enforce_clinical_gate(
        raw,
        payload,
        fallback_text=fallback,
        retry_fn=_retry,
    )
    if gmeta:
        gate.contextual_grounding = gmeta
        log_grounding_assessment(gmeta, gate)
    from src.llm.versions import audit_llm_generation

    audit_llm_generation(
        prompt_template_name="explanation",
        output_text=text,
        grounding_payload=payload,
        gate=gate,
    )
    return text, gate, _explanation_provenance(gate)
