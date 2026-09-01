"""Typed narrative slots: LLM text only, numbers from the grounding payload."""

from __future__ import annotations

import pytest

from src.llm.narrative_schema import (
    ReportNarrative,
    StructuredNarrativeError,
    assemble_report_narratives,
    double_substituted_numbers,
    interpolate_narrative,
    leaked_numeric_literals,
)
from src.llm.report_builder import ReportBuilder


MEASUREMENTS = [
    {"id": "wmh_volume_cc", "value": 10.9, "unit": "cc", "label": "WMH volume"},
    {"id": "wmh_volume_periventricular_cc", "value": 4.2, "unit": "cc"},
    {"id": "wmh_volume_deep_subcortical_cc", "value": 5.1, "unit": "cc"},
    {"id": "wmh_volume_infratentorial_cc", "value": 1.6, "unit": "cc"},
]

_SLOT_FINDINGS = (
    "White matter hyperintensities measure {wmh_volume_cc} cc "
    "with periventricular {wmh_volume_periventricular_cc} cc, "
    "deep subcortical {wmh_volume_deep_subcortical_cc} cc, "
    "and infratentorial {wmh_volume_infratentorial_cc} cc."
)


def test_interpolate_narrative_uses_grounding_payload_only():
    rendered = interpolate_narrative(
        "WMH volume measured at {wmh_volume_cc} cc",
        MEASUREMENTS,
    )
    assert rendered == "WMH volume measured at 10.9 cc"
    assert rendered.count("10.9") == 1

    rendered_alt = interpolate_narrative(
        "WMH volume measured at {{measure:wmh_volume_cc}} cc ({{wmh_volume_cc}} cc).",
        MEASUREMENTS,
    )
    assert rendered_alt == "WMH volume measured at 10.9 cc (10.9 cc)."


def test_assemble_report_narratives_merges_slots_from_payload():
    narrative = ReportNarrative(
        findings_narrative="WMH volume measured at {wmh_volume_cc} cc",
        impression_narrative="Burden measures {{measure:wmh_volume_cc}} cc.",
    )
    out = assemble_report_narratives(narrative, MEASUREMENTS)
    assert out["findings_narrative"] == "WMH volume measured at 10.9 cc"
    assert out["impression_narrative"] == "Burden measures 10.9 cc."
    assert "10.9" in out["findings_narrative"]
    assert "{wmh_volume_cc}" not in out["findings_narrative"]


def test_assemble_rejects_embedded_numbers_before_interpolation(monkeypatch):
    logged: list[dict] = []

    def _capture(*, event_type, user_id, payload):
        logged.append({"event_type": event_type, "payload": payload})
        return "audit"

    monkeypatch.setattr("src.llm.narrative_schema.log_report_draft_event", _capture)

    narrative = ReportNarrative(
        findings_narrative="WMH volume 10.9 cc measured at {wmh_volume_cc} cc",
        impression_narrative="Stable.",
    )
    with pytest.raises(StructuredNarrativeError, match="numeric literals"):
        assemble_report_narratives(narrative, MEASUREMENTS)

    assert logged
    assert logged[0]["event_type"] == "llm_structured_number_leak"
    assert "llm_hallucination_blocked" not in {e["event_type"] for e in logged}

    # Interpolating anyway would double the payload number — that path is blocked.
    leaked_raw = narrative.findings_narrative
    would_double = interpolate_narrative(leaked_raw, MEASUREMENTS)
    assert would_double.count("10.9") >= 2
    assert double_substituted_numbers(leaked_raw, would_double, MEASUREMENTS)


def test_finding_row_interpolates_structured_slots(monkeypatch):
    def _fake(self, prompt, payload, region, relevant):
        if region.get("id") == "white_matter":
            return _SLOT_FINDINGS, {}
        return "Ventricles are normal in size and configuration.", {}

    monkeypatch.setattr(ReportBuilder, "_llm_region_narrative", _fake)
    draft = ReportBuilder("brain_mri_wmh_svd").build_draft(
        case={"case_id": "x", "study_uid": "1.2.3"},
        model_run={
            "audit_id": "aud1",
            "model_name": "unet_3d_wmh",
            "model_version": "v1",
            "confidence": 0.5,
            "wmh": {
                "volume_cc": 10.9,
                "lesion_voxels": 1200,
                "volume_cc_periventricular": 4.2,
                "volume_cc_deep_subcortical": 5.1,
                "volume_cc_infratentorial": 1.6,
            },
        },
    )
    findings = next(s for s in draft["sections"] if s["name"] == "findings")["findings"]
    white = next(r for r in findings if r["region"] == "White matter")
    assert "10.9" in white["text"]
    assert white["text"].count("10.9") == 1
    assert "{wmh_volume_cc}" not in white["text"]
    assert "{{" not in white["text"]
    for token in ("4.2", "5.1", "1.6"):
        assert token in white["text"]
        assert white["text"].count(token) == 1
    impression = next(s for s in draft["sections"] if s["name"] == "impression")
    imp_text = impression["impressions"][0]["text"]
    assert "10.9" in imp_text
    assert "{{wmh_volume_cc}}" not in imp_text
    assert leaked_numeric_literals(_SLOT_FINDINGS) == []


def test_finding_row_does_not_ship_double_numbers_on_literal_leak(monkeypatch):
    def _fake(self, prompt, payload, region, relevant):
        if region.get("id") == "white_matter":
            return "WMH volume 10.9 cc measured at {wmh_volume_cc} cc.", {}
        return "", {}

    monkeypatch.setattr(ReportBuilder, "_llm_region_narrative", _fake)
    draft = ReportBuilder("brain_mri_wmh_svd").build_draft(
        case={"case_id": "x", "study_uid": "1.2.3"},
        model_run={
            "audit_id": "aud1",
            "model_name": "unet_3d_wmh",
            "model_version": "v1",
            "confidence": 0.5,
            "wmh": {"volume_cc": 10.9, "lesion_voxels": 100},
        },
    )
    findings = next(s for s in draft["sections"] if s["name"] == "findings")["findings"]
    white = next(r for r in findings if r["region"] == "White matter")
    assert white["text"].count("10.9") < 2
    assert "measured at 10.9" not in white["text"]
    assert white["validation"]["used_fallback"] is True
