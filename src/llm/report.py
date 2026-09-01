"""
Clinical-style report draft from deterministic model output (Challenge 5).

FDA Non-Device CDS Criterion 1 — the CNN / U-Net perform all image
analysis. Claude only narrates structured labels, probabilities, and
optional Grad-CAM overlay. Never attach raw diagnostic scan bytes.
"""
from typing import Optional

from .cds_constraint import CDS_NARRATION_PREAMBLE, MODEL_OVERLAY_CAPTION
from .client import generate_clinical_prose
from .validation import (
    ValidationResult,
    enforce_clinical_gate,
    grounding_from_prediction,
    log_grounding_assessment,
)


def _template_report(prediction: str, confidence: float) -> str:
    return (
        f"Prediction: {prediction} ({confidence:.2%}). "
        "LLM draft withheld after the clinical faithfulness/recall gate. "
        "This template restates the classifier output only — no additional narrative."
    )


def build_report(
    prediction: str,
    confidence: float,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    *,
    evidence_context: Optional[str] = None,
    probabilities: Optional[dict] = None,
    visual_overlay: Optional[bytes] = None,
) -> tuple[str, ValidationResult]:
    """Draft a report from structured model output, then run the clinical gate.

    ``visual_overlay`` is Grad-CAM / saliency only — never a raw scan.
    """
    evidence_block = evidence_context.strip() if evidence_context else ""
    overlay_note = (
        f"{MODEL_OVERLAY_CAPTION}\n\n"
        if visual_overlay
        else "No medical image is attached. Do not invent visual findings.\n\n"
    )
    prompt = (
        f"{CDS_NARRATION_PREAMBLE}\n\n"
        f"{overlay_note}"
        "Generate a concise clinical-style report that narrates the deterministic "
        "AI classification result. Use these sections:\n"
        "1. **Prediction summary**: Restate the prediction and confidence from the structured data.\n"
        "2. **Additional insights**: What the structured probabilities and (if present) "
        "saliency overlay imply — not what you perceive in a scan.\n"
        "3. **Historical/analogous cases**: One or two short, anonymized analogies "
        "(e.g. 'similar model outputs have been associated with...').\n"
        "4. **Next steps for patient and doctors**: Suggested follow-up "
        "(e.g. further imaging, specialist referral).\n"
        "Use clear headings and plain language. Do not make a definitive diagnosis. "
        "You MUST mention the model prediction class. "
        "Do NOT name findings, anatomy, or severity grades that are not in the structured data.\n\n"
        f"Structured model output:\n"
        f"Model prediction: {prediction} (confidence: {confidence:.2%})."
    )

    if evidence_block:
        prompt += (
            "\n\n"
            "Retrieved evidence (grounding): Use ONLY the information in the evidence block below "
            "to support workflow statements. "
            "If the evidence does not cover a claim, say 'insufficient evidence from retrieved sources'.\n\n"
            f"{evidence_block}\n"
        )

    payload = grounding_from_prediction(prediction, confidence, probabilities)
    fallback = _template_report(prediction, confidence)
    overlay = visual_overlay if visual_overlay else None

    try:
        raw, gmeta = generate_clinical_prose(
            prompt,
            query="Narrate a clinical-style report from the structured model prediction.",
            grounding_payload=payload,
            max_tokens=1024,
            visual_overlay=overlay,
            provider=provider,
            model_id=model_id,
        )
    except Exception:
        raw, gmeta = "", {}

    def _retry(corrective: str) -> str:
        retry_text, retry_meta = generate_clinical_prose(
            prompt + "\n\n" + corrective,
            query="Rewrite the model-output report after a safety-gate rejection.",
            grounding_payload=payload,
            max_tokens=1024,
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
            prompt_template_name="report",
            output_text=fallback,
            grounding_payload=payload,
            gate=gate,
        )
        return fallback, gate

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
        prompt_template_name="report",
        output_text=text,
        grounding_payload=payload,
        gate=gate,
    )
    return text, gate
