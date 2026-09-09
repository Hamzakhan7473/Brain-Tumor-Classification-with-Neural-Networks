"""
FDA Non-Device CDS Criterion 1 constraint.

Software remains non-device CDS only if it does not acquire, process, or
analyze a medical image. In this app the deterministic CNN / 3D U-Net
perform all image analysis. Claude (and any other LLM) may only narrate
already-computed labels, confidences, saliency/Grad-CAM visualizations,
and WMH measurements.

Do not reintroduce raw-scan-to-LLM interpretation as a "feature
improvement." If a future product needs Claude to look at diagnostic
pixels, that is a regulatory classification change, not a prompt tweak.
"""

CDS_NARRATION_PREAMBLE = (
    "You are narrating results from a deterministic clinical model. "
    "You must not independently interpret medical images. "
    "Every clinical claim you make must derive from the structured data "
    "provided, not from visual inspection."
)

MODEL_OVERLAY_CAPTION = (
    "The following image is a visualization of the AI model's output "
    "(saliency / Grad-CAM), not the raw scan — do not describe or "
    "interpret anatomy beyond what is stated in the structured data below."
)
