"""Report logic for healthtech dashboard: status from prediction, recommended next steps."""
from typing import Any

# Display labels for classes
CLASS_DISPLAY = {
    "glioma": "Glioma",
    "meningioma": "Meningioma",
    "pituitary": "Pituitary",
    "notumor": "No tumor",
}


def status_from_prediction(label: str, confidence: float) -> str:
    """
    Map prediction + confidence to status pill: normal | follow | refer | review.
    - notumor + high conf -> normal
    - tumor + high conf -> refer (or follow for pituitary/meningioma)
    - low confidence -> review
    """
    label_lower = (label or "").lower().replace(" ", "").replace("_", "")
    if "notumor" in label_lower or "no_tumor" in label_lower or label_lower == "notumor":
        if confidence >= 0.85:
            return "normal"
        return "review"
    # Tumor type
    if confidence >= 0.9:
        return "refer"
    if confidence >= 0.7:
        return "follow"
    return "review"


def recommended_next_steps(label: str, confidence: float) -> list[str]:
    """
    Return short, actionable next steps based on classification.
    Used for "Recommended next steps" panel.
    """
    label_lower = (label or "").lower().replace(" ", "").replace("_", "")
    steps = []

    if "notumor" in label_lower or label_lower == "notumor":
        steps = [
            "Routine follow-up per clinical indication",
            "No further imaging unless symptoms change",
        ]
    elif "glioma" in label_lower:
        steps = [
            "Refer to neuro-oncology for further evaluation",
            "Consider contrast MRI and multidisciplinary review",
            "Tissue diagnosis may be indicated per guidelines",
        ]
    elif "meningioma" in label_lower:
        steps = [
            "Consider neurosurgery referral for size/symptom assessment",
            "Surveillance imaging per institutional protocol",
        ]
    elif "pituitary" in label_lower:
        steps = [
            "Endocrine and ophthalmology evaluation if not yet done",
            "Consider dedicated pituitary MRI if clinically indicated",
        ]
    else:
        steps = [
            "Review AI classification with radiologist",
            "Correlate with clinical history and prior imaging",
        ]

    if confidence < 0.8:
        steps.insert(0, "AI confidence moderate — recommend radiologist overread")
    return steps


def build_findings_rows(
    primary_label: str,
    primary_confidence: float,
    model_results: dict[str, Any],
    class_names: list[str],
) -> list[tuple[str, str, str]]:
    """
    Build list of (label, value, status) for findings card.
    Primary finding first, then model agreement / secondary.
    """
    display_label = CLASS_DISPLAY.get(
        primary_label.lower().replace(" ", "").replace("_", ""), primary_label
    )
    status = status_from_prediction(primary_label, primary_confidence)
    rows = [
        ("Classification", f"{display_label} ({primary_confidence:.0%})", status),
    ]
    # Add "Model agreement" if multiple models
    if len(model_results) > 1:
        labels = [r["label"] for r in model_results.values()]
        agree = "Yes" if len(set(labels)) == 1 else "No — review models"
        rows.append(("Model agreement", agree, "normal" if agree == "Yes" else "review"))
    return rows
