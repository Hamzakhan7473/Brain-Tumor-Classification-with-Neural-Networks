"""Clinical output gate: numbers, entity faithfulness, and recall."""

from __future__ import annotations

from src.llm.validation import (
    ValidationResult,
    enforce_clinical_gate,
    grounding_from_prediction,
    validate_clinical_output,
    validate_faithfulness,
    validate_no_independent_image_interpretation,
    validate_no_invented_numbers,
    validate_recall,
)


GLIOMA_PAYLOAD = grounding_from_prediction(
    "glioma",
    0.91,
    {"glioma": 0.91, "meningioma": 0.05, "pituitary": 0.03, "notumor": 0.01},
)


def test_invented_anatomical_finding_is_flagged():
    text = (
        "The classifier output is noted. There is also a left frontal hemorrhage "
        "with mass effect, which is not supported by the model payload."
    )
    result = validate_faithfulness(text, GLIOMA_PAYLOAD)
    assert result.passed is False
    assert result.invented_entities
    assert any("hemorrhage" in e or "frontal" in e for e in result.invented_entities)


def test_omitted_high_confidence_tumor_is_flagged():
    text = "The submitted slice was reviewed. No additional narrative is provided."
    result = validate_recall(text, GLIOMA_PAYLOAD)
    assert result.passed is False
    assert result.omitted_findings
    assert any("glioma" in f for f in result.omitted_findings)


def test_clean_prose_matching_payload_passes():
    text = (
        "Prediction summary: the classifier favors glioma with confidence 0.91 "
        "(91%). Additional insights: appearance is consistent with glioma. "
        "No other findings are stated."
    )
    result = validate_clinical_output(text, GLIOMA_PAYLOAD)
    assert result.passed is True
    assert result.invented_entities == []
    assert result.invented_numbers == []
    assert result.omitted_findings == []


def test_invented_number_still_fails():
    payload = {"measurements": [{"id": "wmh_volume_cc", "value": 10.9, "label": "WMH volume"}]}
    text = "WMH volume 99.5 cc detected"
    numbers = validate_no_invented_numbers(text, payload)
    assert numbers.passed is False
    assert "99.5" in numbers.invented_numbers
    combined = validate_clinical_output(text, payload)
    assert combined.passed is False
    assert "99.5" in combined.invented_numbers


def test_wmh_recall_requires_mention():
    payload = {
        "wmh": {
            "volume_cc": 10.9,
            "volume_cc_periventricular": 4.2,
            "volume_cc_deep_subcortical": 5.1,
            "volume_cc_infratentorial": 1.6,
            "severity_grade": "Moderate",
        }
    }
    silent = "The study is otherwise unremarkable."
    recall = validate_recall(silent, payload)
    assert recall.passed is False
    assert any("wmh_volume_cc" in f for f in recall.omitted_findings)

    mentioned = (
        "WMH measures 10.9 cc with periventricular, deep subcortical, "
        "and infratentorial involvement."
    )
    ok = validate_clinical_output(mentioned, payload)
    assert ok.passed is True


def test_gate_falls_back_and_does_not_ship_unvalidated_text():
    bad = "Left frontal hemorrhage measuring 12 cc, consistent with abscess."
    fallback = "Prediction: glioma (91.00%). Template only."
    calls = {"n": 0}

    def retry(_corrective: str) -> str:
        calls["n"] += 1
        return "Still inventing a temporal infarct."

    text, result = enforce_clinical_gate(
        bad,
        GLIOMA_PAYLOAD,
        fallback_text=fallback,
        retry_fn=retry,
    )
    assert calls["n"] == 1
    assert text == fallback
    assert result.used_fallback is True
    assert result.regenerated is True
    assert result.passed is False


def test_combine_aggregates_violation_types():
    a = ValidationResult(passed=False, invented_numbers=["12"])
    b = ValidationResult(passed=False, invented_entities=["hemorrhage"])
    c = ValidationResult(passed=False, omitted_findings=["glioma (confidence 0.91)"])
    merged = ValidationResult.combine(a, b, c)
    assert merged.passed is False
    assert merged.invented_numbers == ["12"]
    assert merged.invented_entities == ["hemorrhage"]
    assert merged.omitted_findings == ["glioma (confidence 0.91)"]
    types = {v["type"] for v in merged.violations}
    assert types == {"invented_number", "invented_entity", "omitted_finding"}


def test_independent_visual_language_fails_gate():
    result = validate_no_independent_image_interpretation(
        "I can see edema along the cortex.",
        GLIOMA_PAYLOAD,
    )
    assert result.passed is False
    ok = validate_no_independent_image_interpretation(
        "The model measured 10.9cc WMH. The highlighted region corresponds to elevated signal per the saliency map.",
        {"measurements": [{"id": "wmh_volume_cc", "value": 10.9}]},
    )
    assert ok.passed is True
