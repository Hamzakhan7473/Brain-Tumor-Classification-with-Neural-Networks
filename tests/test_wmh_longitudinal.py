"""WMH comparison only after this repo's registration job writes passed."""

from __future__ import annotations

import numpy as np
import pytest

from src.inference.registration import JOB_SOURCE, job_wrote_passed, run_registration_job
from src.inference.wmh_longitudinal import compare_wmh_timepoints
from src.llm.report_builder import ReportBuilder
from src.llm.validation import validate_comparison_language, validate_draft


_DELTA_KEYS = (
    "volume_delta_cc",
    "delta_cc",
    "volume_pct_change",
    "pct_change",
    "direction",
    "comparison_summary",
    "regional",
)


def _blob(shape=(24, 24, 24), center=(12, 12, 12), radius=5.5) -> np.ndarray:
    z, y, x = np.ogrid[: shape[0], : shape[1], : shape[2]]
    mask = (z - center[0]) ** 2 + (y - center[1]) ** 2 + (x - center[2]) ** 2 <= radius**2
    vol = np.full(shape, 4.0, dtype=np.float32)
    vol[mask] = 120.0
    return vol


def test_no_prior_returns_no_comparison_row():
    assert compare_wmh_timepoints({"volume_cc": 10.0}, None) is None
    assert compare_wmh_timepoints({"volume_cc": 10.0}, {}) is None


def test_incompatible_protocol_no_comparison_object():
    vol = _blob()
    assert (
        compare_wmh_timepoints(
            {"volume_cc": 10.0, "patient_key": "a", "flair_volume": vol, "sequence": "FLAIR"},
            {"volume_cc": 8.0, "patient_key": "b", "flair_volume": vol, "sequence": "FLAIR"},
        )
        is None
    )
    assert (
        compare_wmh_timepoints(
            {"volume_cc": 10.0, "patient_key": "a", "flair_volume": vol, "sequence": "T1"},
            {"volume_cc": 8.0, "patient_key": "a", "flair_volume": vol, "sequence": "FLAIR"},
        )
        is None
    )


def test_always_incomparable_no_delta_keys_when_job_not_run():
    out = compare_wmh_timepoints(
        {"volume_cc": 12.0, "volume_cc_periventricular": 5.0},
        {"volume_cc": 8.0, "volume_cc_periventricular": 3.0},
        prior_label="2024-01-15 MRI",
    )
    assert out is not None
    assert out["status"] == "incomparable"
    assert out["reason_code"] == "QC_NO_REGISTRATION"
    assert out["qc"]["registration"]["status"] == "not_run"
    assert out["prior_label"] == "2024-01-15 MRI"
    assert out["current_volume_cc"] == 12.0
    assert out["prior_volume_cc"] == 8.0
    for key in _DELTA_KEYS:
        assert key not in out


def test_does_not_invent_passed_registration():
    out = compare_wmh_timepoints(
        {"volume_cc": 12.0},
        {"volume_cc": 8.0},
        registration={"status": "passed", "mask_overlap": 0.91, "ncc": 0.62, "source": JOB_SOURCE},
    )
    assert out is not None
    assert out["status"] == "incomparable"
    assert out["reason_code"] == "QC_NO_REGISTRATION"
    assert out["qc"]["registration"]["status"] != "passed"
    for key in _DELTA_KEYS:
        assert key not in out


def test_spoofed_passed_ignored_unless_this_job_wrote_it():
    fake = {"status": "passed", "source": "caller", "mask_overlap": 0.99, "ncc": 0.9, "com_shift_mm": 0.1}
    assert job_wrote_passed(fake) is False
    out = compare_wmh_timepoints(
        {"volume_cc": 12.0, "registration": fake},
        {"volume_cc": 8.0},
        registration=fake,
    )
    assert out is not None
    assert out["qc"]["registration"].get("source") != "caller" or out["status"] == "incomparable"
    assert out["qc"]["registration"]["status"] != "passed"


def test_failed_qc_incomparable_no_delta(monkeypatch):
    job = {
        "status": "failed",
        "source": JOB_SOURCE,
        "reason_code": "QC_REGISTRATION",
        "mask_overlap": 0.40,
        "ncc": 0.21,
        "com_shift_mm": 22.0,
    }
    monkeypatch.setattr(
        "src.inference.wmh_longitudinal.run_registration_job",
        lambda **_k: job,
    )
    out = compare_wmh_timepoints(
        {"volume_cc": 12.0, "patient_key": "p", "flair_volume": _blob()},
        {"volume_cc": 8.0, "patient_key": "p", "flair_volume": _blob(center=(4, 4, 4))},
    )
    assert out is not None
    assert out["status"] == "incomparable"
    assert out["reason_code"] == "QC_REGISTRATION"
    assert out["qc"]["registration"]["status"] == "failed"
    for key in _DELTA_KEYS:
        assert key not in out


def test_failed_qc_on_unrelated_volumes():
    pytest.importorskip("SimpleITK")
    rng = np.random.default_rng(0)
    prior = _blob(center=(8, 8, 8), radius=4)
    current = rng.random((24, 24, 24), dtype=np.float32) * 3.0
    job = run_registration_job(
        current_volume=current,
        prior_volume=prior,
        patient_key="p",
        prior_patient_key="p",
        current_sequence="FLAIR",
        prior_sequence="FLAIR",
        current_spacing_mm=(1.0, 1.0, 1.0),
        prior_spacing_mm=(1.0, 1.0, 1.0),
    )
    assert job["status"] != "passed"
    assert job["reason_code"] == "QC_REGISTRATION"
    out = compare_wmh_timepoints(
        {"volume_cc": 12.0, "patient_key": "p", "flair_volume": current, "spacing_mm": (1, 1, 1)},
        {"volume_cc": 8.0, "patient_key": "p", "flair_volume": prior, "spacing_mm": (1, 1, 1)},
    )
    assert out is not None
    assert out["status"] == "incomparable"
    assert out["reason_code"] == "QC_REGISTRATION"
    for key in _DELTA_KEYS:
        assert key not in out


def test_passed_synthetic_translation_emits_delta():
    pytest.importorskip("SimpleITK")
    prior = _blob(center=(12, 12, 12))
    current = _blob(center=(12, 12, 9))
    out = compare_wmh_timepoints(
        {
            "volume_cc": 12.0,
            "patient_key": "p",
            "audit_id": "cur_audit_01",
            "study_uid": "1.2.cur",
            "flair_volume": current,
            "spacing_mm": (1.0, 1.0, 1.0),
            "sequence": "FLAIR",
            "acquired_at": "2026-06-01T00:00:00Z",
        },
        {
            "volume_cc": 8.0,
            "patient_key": "p",
            "audit_id": "pri_audit_01",
            "study_uid": "1.2.pri",
            "flair_volume": prior,
            "spacing_mm": (1.0, 1.0, 1.0),
            "sequence": "FLAIR",
            "acquired_at": "2025-12-01T00:00:00Z",
        },
        prior_label="prior FLAIR",
    )
    assert out is not None
    assert out["status"] == "comparable"
    assert out["qc"]["registration"]["status"] == "passed"
    assert out["qc"]["registration"]["source"] == JOB_SOURCE
    assert job_wrote_passed(out["qc"]["registration"])
    assert out["prior_cc"] == 8.0
    assert out["current_cc"] == 12.0
    assert out["delta_cc"] == 4.0
    assert out["pct_change"] == 50.0
    assert out["direction"] == "increased"
    assert out["days_between"] == 182
    assert out["volume_delta_cc"] == 4.0


def test_recorded_qc_pass_from_this_job_emits_delta(monkeypatch):
    job = {
        "status": "passed",
        "source": JOB_SOURCE,
        "reason_code": None,
        "mask_overlap": 0.93,
        "ncc": 0.71,
        "com_shift_mm": 2.4,
    }
    monkeypatch.setattr("src.inference.wmh_longitudinal.run_registration_job", lambda **_k: job)
    out = compare_wmh_timepoints(
        {"volume_cc": 10.9, "patient_key": "p", "flair_volume": _blob()},
        {"volume_cc": 8.0, "patient_key": "p", "flair_volume": _blob()},
    )
    assert out is not None
    assert out["status"] == "comparable"
    assert out["delta_cc"] == pytest.approx(2.9)
    assert out["qc"]["registration"]["source"] == JOB_SOURCE


def test_report_draft_omits_naked_delta_and_change_copy():
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
    lon = draft["case_snapshot"]["longitudinal"]
    assert lon["status"] == "incomparable"
    for key in ("direction", "comparison_summary", "volume_delta_cc"):
        assert key not in lon
    ids = {m["id"] for m in draft["measurements"]}
    assert "wmh_volume_delta_cc" not in ids
    assert "wmh_volume_pct_change" not in ids
    comparison = next(s for s in draft["sections"] if s["name"] == "comparison")
    low = (comparison["text"] or "").lower()
    assert "prior not comparable" in low
    for word in ("increased", "decreased", "stable"):
        assert word not in low
    impression = next(s for s in draft["sections"] if s["name"] == "impression")
    lon_lines = [im for im in impression["impressions"] if "Longitudinal" in im["text"]]
    assert lon_lines == []


def test_validate_draft_rejects_change_words_without_comparable_row():
    payload = {
        "wmh": {"volume_cc": 10.9},
        "longitudinal": compare_wmh_timepoints({"volume_cc": 10.9}, {"volume_cc": 8.0}),
    }
    slight = validate_comparison_language("There is a slight increase in WMH.", payload)
    assert slight.passed is False
    interval = validate_draft("Interval change in white-matter hyperintensity burden.", payload)
    assert interval.passed is False
    assert "REJECT_COMPARISON_LANGUAGE" in interval.contradicted_claims


def test_nibabel_affine_alignment_is_not_qc_pass():
    """Matching world affines are not registration.status=passed."""
    out = compare_wmh_timepoints(
        {
            "volume_cc": 12.0,
            "affine": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "registration": {"status": "passed", "reason": "affines_match"},
        },
        {
            "volume_cc": 8.0,
            "affine": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        },
        registration={"status": "passed"},
    )
    assert out is not None
    assert out["status"] == "incomparable"
    assert out["qc"]["registration"]["status"] != "passed"
