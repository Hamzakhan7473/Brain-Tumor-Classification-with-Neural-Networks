"""Longitudinal WMH comparison tests."""

from __future__ import annotations

from src.inference.wmh_longitudinal import compare_wmh_timepoints
from src.llm.report_builder import ReportBuilder


def test_compare_increased():
    out = compare_wmh_timepoints(
        {"volume_cc": 12.0, "volume_cc_periventricular": 5.0},
        {"volume_cc": 8.0, "volume_cc_periventricular": 3.0},
        prior_label="2024-01-15 MRI",
    )
    assert out["volume_delta_cc"] == 4.0
    assert out["volume_pct_change"] == 50.0
    assert out["direction"] == "increased"
    assert "2024-01-15 MRI" in out["comparison_summary"]


def test_compare_stable():
    out = compare_wmh_timepoints({"volume_cc": 10.2}, {"volume_cc": 10.0})
    assert out["direction"] == "stable"
    assert abs(out["volume_delta_cc"]) == 0.2


def test_report_draft_includes_longitudinal():
    builder = ReportBuilder("brain_mri_wmh_svd")
    draft = builder.build_draft(
        case={
            "case_id": "cur",
            "study_uid": "cur",
            "longitudinal": compare_wmh_timepoints(
                {"volume_cc": 10.9, "volume_cc_periventricular": 4.2},
                {"volume_cc": 8.0, "volume_cc_periventricular": 3.0},
                prior_label="prior MRI",
            ),
        },
        model_run={
            "audit_id": "aud1",
            "model_name": "unet_3d_wmh",
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
    ids = {m["id"] for m in draft["measurements"]}
    assert "wmh_volume_delta_cc" in ids
    assert "wmh_volume_pct_change" in ids
    comparison = next(s for s in draft["sections"] if s["name"] == "comparison")
    assert "prior MRI" in comparison["text"]
    impression = next(s for s in draft["sections"] if s["name"] == "impression")
    lon_lines = [im for im in impression["impressions"] if "Longitudinal" in im["text"]]
    assert len(lon_lines) == 1
