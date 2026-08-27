"""Unit tests for geometric regional WMH volume zoning."""

from __future__ import annotations

import numpy as np

from src.inference.wmh_regional import regional_wmh_volumes_cc
from src.llm.report_builder import ReportBuilder


def test_regional_volumes_sum_to_total():
    mask = np.zeros((32, 32, 32), dtype=bool)
    # Central (should lean periventricular) + peripheral + inferior
    mask[20:24, 14:18, 14:18] = True  # center-ish superior
    mask[20:22, 2:5, 2:5] = True  # peripheral superior → deep
    mask[1:4, 14:18, 14:18] = True  # inferior → infratentorial
    flair = np.ones((32, 32, 32), dtype=np.float32)
    out = regional_wmh_volumes_cc(mask, voxel_vol_mm3=1.0, flair_volume=flair)
    total = out["volume_cc_total"]
    parts = (
        out["volume_cc_periventricular"]
        + out["volume_cc_deep_subcortical"]
        + out["volume_cc_infratentorial"]
    )
    assert abs(parts - total) < 1e-3
    assert out["volume_cc_infratentorial"] > 0
    assert out["method"] == "geometric_heuristic_v1"


def test_empty_mask_zeros():
    mask = np.zeros((16, 16, 16), dtype=bool)
    out = regional_wmh_volumes_cc(mask, voxel_vol_mm3=8.0)
    assert out["volume_cc_total"] == 0.0
    assert out["volume_cc_periventricular"] == 0.0
    assert out["volume_cc_deep_subcortical"] == 0.0
    assert out["volume_cc_infratentorial"] == 0.0


def test_report_builder_extracts_regional_measurements():
    builder = ReportBuilder("brain_mri_wmh_svd")
    draft = builder.build_draft(
        case={"case_id": "x", "study_uid": "1.2.3"},
        model_run={
            "audit_id": "aud1",
            "model_name": "unet_3d_wmh",
            "model_version": "v1",
            "confidence": 0.5,
            "wmh": {
                "volume_cc": 10.9,
                "lesion_voxels": 1200,
                "age_matched_percentile": 75,
                "volume_cc_periventricular": 4.2,
                "volume_cc_deep_subcortical": 5.1,
                "volume_cc_infratentorial": 1.6,
            },
        },
    )
    ids = {m["id"]: m["value"] for m in draft["measurements"]}
    assert ids["wmh_volume_cc"] == 10.9
    assert ids["wmh_volume_periventricular_cc"] == 4.2
    assert ids["wmh_volume_deep_subcortical_cc"] == 5.1
    assert ids["wmh_volume_infratentorial_cc"] == 1.6
    impression = next(s for s in draft["sections"] if s["name"] == "impression")
    text = impression["impressions"][0]["text"]
    assert "4.2" in text
    assert "5.1" in text
    assert "1.6" in text
