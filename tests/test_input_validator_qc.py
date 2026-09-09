"""Pre-inference QC: wrong-sequence 2D must not emit a trusted class."""

from __future__ import annotations

from src.inference.input_validator import ValidationResult, validate_for_model


def test_2d_dicom_t2_is_rejected(monkeypatch):
    def _fake(file_bytes: bytes):
        return "T2", 0.88, {"series_desc": "T2 TSE"}

    monkeypatch.setattr("src.inference.input_validator._validate_dicom_2d", _fake)
    vr = validate_for_model(b"dicom-bytes", "series.dcm", "custom_cnn")
    assert isinstance(vr, ValidationResult)
    assert vr.accepted is False
    assert vr.trusted is False
    assert vr.sequence == "T2"
    assert any("will not infer" in e for e in vr.errors)


def test_2d_dicom_flair_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._validate_dicom_2d",
        lambda _b: ("FLAIR", 0.92, {"series_desc": "T2 FLAIR"}),
    )
    vr = validate_for_model(b"dicom-bytes", "flair.dcm", "custom_cnn")
    assert vr.accepted is False
    assert vr.trusted is False
    assert vr.sequence == "FLAIR"


def test_2d_dicom_t1_still_accepted(monkeypatch):
    monkeypatch.setattr(
        "src.inference.input_validator._validate_dicom_2d",
        lambda _b: ("T1", 0.89, {"series_desc": "T1 SE"}),
    )
    vr = validate_for_model(b"dicom-bytes", "t1.dcm", "custom_cnn")
    assert vr.accepted is True
    assert vr.trusted is False
    assert vr.sequence == "T1"
