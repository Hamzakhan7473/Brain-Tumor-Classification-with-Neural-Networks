"""Slice 3: unit-aware number gate, pixel leak, recall, fail-closed."""

from __future__ import annotations

from src.llm.pixel_leak import PayloadRejected, heatmap_metadata_only, validate_payload
from src.llm.validation import (
    enforce_clinical_gate,
    fail_closed_template,
    validate_attestation_forged,
    validate_clinical_output,
    validate_comparison_language,
    validate_draft,
    validate_no_invented_numbers,
    validate_recall,
)


WMH_PAYLOAD = {
    "findings": [{"code": "wmh.volume.total_cc", "value": 12.4, "unit": "cc", "status": "ok"}],
    "wmh": {"volume_cc": 12.4},
    "days_between": 187,
    "qc": {"field_strength": "3T"},
    "longitudinal": {"status": "incomparable", "current_volume_cc": 12.4, "prior_volume_cc": 10.1},
    "model_version": "v1",
}


def test_invented_cc_rejected():
    result = validate_no_invented_numbers("WMH measures 14.1 cc.", WMH_PAYLOAD)
    assert result.passed is False
    assert any("14.1" in n for n in result.invented_numbers)
    assert "REJECT_INVENTED_NUMBER" in result.rejection_codes


def test_same_digits_wrong_unit_rejected():
    result = validate_no_invented_numbers("WMH measures 12.4 mm.", WMH_PAYLOAD)
    assert result.passed is False
    assert "REJECT_UNIT_MISMATCH" in result.rejection_codes


def test_omitted_finding_number_rejected():
    payload = {
        "findings": [{"code": "tumor.volume.et_cc", "value": 4.2, "unit": "cc", "status": "omitted"}],
    }
    result = validate_no_invented_numbers("Enhancing tumor 4.2 cc.", payload)
    assert result.passed is False
    assert "REJECT_OMITTED_NUMBER_USED" in result.rejection_codes


def test_slight_increase_and_interval_change_incomparable():
    slight = validate_comparison_language("There is a slight increase in WMH.", WMH_PAYLOAD)
    assert slight.passed is False
    interval = validate_draft("Interval change in white matter hyperintensities (12.4 cc).", WMH_PAYLOAD)
    assert interval.passed is False
    assert "REJECT_COMPARISON_LANGUAGE" in interval.rejection_codes


def test_tesla_and_days_are_not_invented():
    text = (
        "WMH volume is 12.4 cc on a 3T exam performed 187 days after the prior study. "
        "White matter hyperintensities are described. No change language is used."
    )
    result = validate_clinical_output(text, WMH_PAYLOAD)
    assert result.invented_numbers == []
    assert result.passed is True


def test_et_vol_recall():
    payload = {"ET_VOL": 4.2, "wmh": {"volume_cc": 0.2}}
    silent = "The structured measurements were reviewed."
    recall = validate_recall(silent, payload)
    assert recall.passed is False
    assert any("ET_VOL" in f for f in recall.omitted_findings)
    ok = validate_recall("Enhancing tumor measures 4.2 cc.", payload)
    assert ok.passed is True


def test_attestation_forged_rejected():
    result = validate_attestation_forged("I hereby attest that these findings are final.")
    assert result.passed is False
    assert "REJECT_ATTESTATION_FORGED" in result.rejection_codes


def test_gradcam_png_stripped_before_converse(fake_boto3_unused=None):
    assert heatmap_metadata_only(b"\x89PNG\r\n\x1a\nHEATMAP") is None
    try:
        validate_payload({"image_bytes": b"\x89PNG\r\n"})
        leaked = False
    except PayloadRejected as exc:
        leaked = exc.code == "REJECT_PIXEL_LEAK"
    assert leaked is True
    gate = validate_draft("WMH 12.4 cc.", {"wmh": {"volume_cc": 12.4}, "saliency_map_b64": "aaaa"})
    assert gate.passed is False
    assert "REJECT_PIXEL_LEAK" in gate.rejection_codes


def test_fail_closed_template_only_payload_numbers():
    closed = fail_closed_template(WMH_PAYLOAD)
    assert "FAIL_CLOSED" in closed
    assert "12.4" in closed
    assert "14.1" not in closed
    assert "99.5" not in closed

    def retry(_c: str) -> str:
        return "WMH now 99.5 cc with a slight increase."

    text, gate = enforce_clinical_gate(
        "WMH 99.5 cc.",
        WMH_PAYLOAD,
        fallback_text="should not be used if table exists",
        retry_fn=retry,
    )
    assert "FAIL_CLOSED" in text
    assert "99.5" not in text
    assert "12.4" in text
    assert gate.used_fallback is True
    assert "FAIL_CLOSED" in gate.rejection_codes


def test_triage_class_is_not_a_signed_finding():
    """2D class must not enter the measurement allowlist as a signed finding."""
    from src.llm.report_builder import ReportBuilder
    from src.llm.validation import grounding_from_measurements

    draft = ReportBuilder("brain_mri_tumor").build_draft(
        {"study_uid": "1.2.3.validator.triage"},
        {
            "audit_id": "triageallowlist12",
            "model_name": "custom_cnn",
            "confidence": 0.92,
            "label": "glioma",
            "probabilities": {
                "glioma": 0.92,
                "meningioma": 0.04,
                "pituitary": 0.03,
                "notumor": 0.01,
            },
        },
    )
    payload = grounding_from_measurements(draft["measurements"])
    assert not any(
        isinstance(m, dict) and m.get("id") == "predicted_label" for m in payload.get("measurements") or []
    )
    assert not payload.get("label")
    assert (draft.get("research") or {}).get("triage", {}).get("class") == "glioma"
