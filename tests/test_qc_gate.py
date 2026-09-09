"""QC gate: wrong-sequence / untrusted 2D must not emit trusted measurements."""

from __future__ import annotations

from src.inference.input_validator import ValidationResult, validate_for_model
from src.inference.qc import LIMITED_EXAM_SENTENCE, build_qc
from src.ingest.path import has_trusted_volume, wmh_volume_is_trusted
from src.llm.report_builder import ReportBuilder
from src.llm.validation import validate_no_invented_numbers


def _triage_run(**extra):
    run = {
        "audit_id": "qcaudit123456789",
        "model_name": "custom_cnn",
        "model_version": "v1",
        "confidence": 0.91,
        "label": "glioma",
        "probabilities": {"glioma": 0.91, "meningioma": 0.05, "pituitary": 0.03, "notumor": 0.01},
    }
    run.update(extra)
    return run


def test_2d_dicom_t2_not_trusted_measurement(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._validate_dicom_2d",
        lambda _b: ("T2", 0.88, {"series_desc": "T2 TSE", "modality": "MR", "image_type": ["ORIGINAL"]}),
    )
    vr = validate_for_model(b"dicom-bytes", "series.dcm", "custom_cnn")
    assert vr.accepted is False
    assert vr.trusted is False
    qc = build_qc(model_name="custom_cnn", filename="series.dcm", vr=vr, ran_inference=False)
    assert qc["overall"] == "fail"
    assert qc["engines"]["research.triage"]["run"] is False
    assert qc["engines"]["wmh_3d"]["run"] is False
    assert qc["engines"]["research.triage"].get("trusted") is False
    draft = ReportBuilder("brain_mri_tumor").build_draft(
        {"study_uid": "1.2.3.qc.t2"},
        _triage_run(qc=qc, wmh={"volume_cc": 8.1, "status": "omitted"}),
    )
    mids = {m["id"] for m in draft.get("measurements") or []}
    assert "wmh_volume_cc" not in mids
    assert not has_trusted_volume(draft)


def test_2d_not_mr_and_localizer_fail_series_checks(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._validate_dicom_2d",
        lambda _b: ("unknown", 0.3, {"modality": "CT", "image_type": []}),
    )
    vr = validate_for_model(b"x", "head.dcm", "custom_cnn")
    assert vr.accepted is False
    assert vr.trusted is False

    monkeypatch.setattr(
        "src.inference.input_validator._validate_dicom_2d",
        lambda _b: ("T1", 0.89, {"modality": "MR", "image_type": ["ORIGINAL", "LOCALIZER"]}),
    )
    loc = validate_for_model(b"x", "scout.dcm", "custom_cnn")
    assert loc.accepted is False
    assert loc.trusted is False


def test_jpg_demo_is_untrusted_triage_with_motion_indeterminate(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._validate_image_2d",
        lambda _b: (True, []),
    )
    vr = validate_for_model(b"raster", "slice.jpg", "custom_cnn")
    assert vr.accepted is True
    assert vr.trusted is False
    assert any("MOTION_INDETERMINATE" in w for w in vr.warnings)
    qc = build_qc(model_name="custom_cnn", filename="slice.jpg", vr=vr, ran_inference=True)
    assert qc["overall"] == "degraded"
    assert qc["engines"]["research.triage"] == {"run": True, "trusted": False}
    assert qc["engines"]["wmh_3d"]["run"] is False
    codes = {f["code"] for f in qc["flags"]}
    assert "MOTION_INDETERMINATE" in codes
    assert "RASTER_DEMO" in codes


def test_unknown_sequence_warns_but_is_not_trusted(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._validate_dicom_2d",
        lambda _b: ("unknown", 0.32, {"modality": "MR", "image_type": ["ORIGINAL", "PRIMARY"]}),
    )
    vr = validate_for_model(b"x", "series.dcm", "custom_cnn")
    assert vr.accepted is True
    assert vr.trusted is False
    qc = build_qc(model_name="custom_cnn", filename="series.dcm", vr=vr, ran_inference=True)
    assert qc["overall"] == "degraded"
    assert qc["engines"]["research.triage"]["trusted"] is False


def test_non_flair_does_not_produce_trusted_wmh_cc(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._detect_3d_sequence",
        lambda _b, _n: ("T1", 0.89, {"voxel_volume_mm3": 1.0, "voxel_dims_mm": [1.0, 1.0, 1.0]}),
    )
    vr = validate_for_model(b"nii-bytes", "t1w.nii", "unet_3d_wmh")
    assert isinstance(vr, ValidationResult)
    assert vr.accepted is False
    assert vr.trusted is False
    assert vr.sequence == "T1"
    qc = build_qc(model_name="unet_3d_wmh", filename="t1w.nii", vr=vr, ran_inference=False)
    assert qc["overall"] == "fail"
    assert qc["engines"]["wmh_3d"] == {"run": False, "reason": "QC_FAIL"}
    stuffed = {
        "audit_id": "wmhqc1234567890",
        "model_name": "unet_3d_wmh",
        "confidence": 0.4,
        "wmh": {"volume_cc": 12.4, "status": "omitted"},
        "qc": qc,
    }
    assert wmh_volume_is_trusted(stuffed) is False
    draft = ReportBuilder("brain_mri_wmh_svd").build_draft({"study_uid": "1.2.3.qc.nflair"}, stuffed)
    mids = {m["id"] for m in draft.get("measurements") or []}
    assert "wmh_volume_cc" not in mids
    prose = " ".join(
        (row.get("text") or "")
        for sec in draft.get("sections") or []
        for row in (sec.get("findings") or []) + (sec.get("impressions") or [])
    )
    assert LIMITED_EXAM_SENTENCE in prose
    assert "12.4" not in prose
    assert has_trusted_volume(draft) is False


def test_omitted_engine_number_in_draft_still_rejected():
    payload = {
        "wmh": {"volume_cc": 4.2, "status": "omitted"},
        "qc": {
            "overall": "fail",
            "flags": [{"code": "MISSING_FLAIR", "severity": "fail", "engine": "wmh_3d"}],
            "engines": {"wmh_3d": {"run": False, "reason": "QC_FAIL"}},
        },
    }
    result = validate_no_invented_numbers("WMH measures 4.2 cc.", payload)
    assert result.passed is False
    assert "REJECT_OMITTED_NUMBER_USED" in result.rejection_codes
