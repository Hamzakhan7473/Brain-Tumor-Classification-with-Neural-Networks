"""Honest DICOM folder ingest: one study, series grouped, clinical only when grouping succeeds."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from src.ingest.dicom_dir import (
    assemble_series_volume,
    can_assemble_volume,
    classify_series,
    group_dicom_dir,
)
from src.ingest.path import classify_upload, resolve_ingest_path
from src.ingest.watcher import scan_drop_dir, study_drop_roots

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

HEADERS = {"X-API-Key": "test-key"}


def _ensure_dummy_keras_weights() -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / "models" / "saved" / "custom_cnn_best.keras"
    if target.exists():
        return
    import tensorflow as tf
    from tensorflow import keras

    tf.keras.backend.clear_session()
    inp = keras.layers.Input(shape=(224, 224, 3))
    x = keras.layers.Conv2D(8, 3, padding="same", activation="relu")(inp)
    x = keras.layers.GlobalAveragePooling2D()(x)
    out = keras.layers.Dense(4, activation="softmax")(x)
    model = keras.Model(inp, out)
    model.compile(optimizer="adam", loss="categorical_crossentropy")
    target.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(target))


_ensure_dummy_keras_weights()


def _write_dcm(
    path: Path,
    *,
    study: str,
    series: str,
    instance: int,
    modality: str = "MR",
    desc: str = "",
    image_type: list[str] | None = None,
    inversion_time: float | None = None,
    echo_time: float = 10.0,
    thickness: float = 1.0,
    contrast: str | None = None,
    rows: int = 8,
    cols: int = 8,
    omit_study: bool = False,
) -> None:
    sop = generate_uid()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SOPClassUID = MRImageStorage
    ds.SOPInstanceUID = sop
    if not omit_study:
        ds.StudyInstanceUID = study
    ds.SeriesInstanceUID = series
    ds.InstanceNumber = instance
    ds.Modality = modality
    ds.SeriesDescription = desc
    ds.ImageType = image_type or ["ORIGINAL", "PRIMARY", "M", "NORM"]
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = thickness
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.ImagePositionPatient = [0.0, 0.0, float(instance)]
    ds.EchoTime = echo_time
    if inversion_time is not None:
        ds.InversionTime = inversion_time
    if contrast:
        ds.ContrastBolusAgent = contrast
    ds.PixelData = np.zeros((rows, cols), dtype=np.uint16).tobytes()
    ds.save_as(str(path), write_like_original=False)


def _multi_series_dir(tmp: Path) -> tuple[Path, str, str, str]:
    study = generate_uid()
    t1 = generate_uid()
    flair = generate_uid()
    root = tmp / "study"
    root.mkdir()
    for i in range(1, 5):
        _write_dcm(
            root / f"t1_{i:03d}.dcm",
            study=study,
            series=t1,
            instance=i,
            echo_time=8.0,
            desc="",
        )
        _write_dcm(
            root / f"flair_{i:03d}.dcm",
            study=study,
            series=flair,
            instance=i,
            inversion_time=2500.0,
            echo_time=120.0,
            desc="",
        )
    return root, study, t1, flair


def test_multi_series_dir_groups_into_one_study(tmp_path):
    root, study, t1, flair = _multi_series_dir(tmp_path)
    result = group_dicom_dir(root)
    assert result.ok is True
    assert result.rejected is False
    assert result.study_uid == study
    assert result.ingest_path == "clinical"
    assert set(result.series_manifest) == {t1, flair}
    assert result.series_manifest[t1]["likely_seq"] == "T1"
    assert result.series_manifest[flair]["likely_seq"] == "FLAIR"
    assert result.engines["wmh_3d"] == flair
    assert result.engines["research.triage"] == t1
    assert "wmh_3d" in result.series_manifest[flair]["used_by_engines"]
    assert "research.triage" in result.series_manifest[t1]["used_by_engines"]
    assert result.n_instances == 8


def test_description_is_hint_only_image_type_wins(tmp_path):
    study = generate_uid()
    series = generate_uid()
    root = tmp_path / "loc"
    root.mkdir()
    for i in range(1, 4):
        _write_dcm(
            root / f"{i}.dcm",
            study=study,
            series=series,
            instance=i,
            image_type=["ORIGINAL", "PRIMARY", "LOCALIZER"],
            desc="T1 FLAIR AXIAL",
        )
    result = group_dicom_dir(root)
    assert result.ok
    sid = next(iter(result.series_manifest))
    assert result.series_manifest[sid]["likely_seq"] == "LOCALIZER"
    assert result.engines["wmh_3d"] is None


def test_wmh_requires_assembled_flair_volume_not_a_slice(tmp_path):
    study = generate_uid()
    flair = generate_uid()
    root = tmp_path / "thin"
    root.mkdir()
    _write_dcm(
        root / "one.dcm",
        study=study,
        series=flair,
        instance=1,
        inversion_time=2500.0,
        echo_time=120.0,
    )
    result = group_dicom_dir(root)
    assert result.ok
    assert result.ingest_path == "demo"
    assert result.engines["wmh_3d"] is None
    series = result.series[0]
    assert series.likely_seq == "FLAIR"
    assert can_assemble_volume(series.instances) is False
    assert assemble_series_volume(series.instances) is None


def test_non_mr_dir_is_rejected_never_clinical(tmp_path):
    study = generate_uid()
    series = generate_uid()
    root = tmp_path / "ct"
    root.mkdir()
    for i in range(1, 4):
        _write_dcm(root / f"{i}.dcm", study=study, series=series, instance=i, modality="CT")
    result = group_dicom_dir(root)
    assert result.rejected is True
    assert result.reason == "NOT_MR"
    assert result.ingest_path == "demo"


def test_ungroupable_two_studies_rejected(tmp_path):
    root = tmp_path / "mixed"
    root.mkdir()
    _write_dcm(root / "a.dcm", study=generate_uid(), series=generate_uid(), instance=1)
    _write_dcm(root / "b.dcm", study=generate_uid(), series=generate_uid(), instance=1)
    result = group_dicom_dir(root)
    assert result.rejected is True
    assert result.reason == "UNGROUPABLE"
    assert result.ingest_path == "demo"


def test_missing_study_uid_rejected(tmp_path):
    root = tmp_path / "bad"
    root.mkdir()
    _write_dcm(root / "x.dcm", study="will-omit", series=generate_uid(), instance=1, omit_study=True)
    result = group_dicom_dir(root)
    assert result.rejected is True
    assert result.reason in {"NO_DICOM", "UNGROUPABLE"}
    assert result.ingest_path == "demo"


def test_jpg_dir_never_silent_clinical(tmp_path):
    root = tmp_path / "jpgs"
    root.mkdir()
    from PIL import Image

    Image.fromarray(np.zeros((32, 32), dtype=np.uint8)).save(root / "slice.jpg")
    result = group_dicom_dir(root)
    assert result.rejected is True
    assert result.ingest_path == "demo"
    assert result.reason == "NO_DICOM"


def test_loose_nifti_never_silent_clinical(tmp_path):
    import nibabel as nib

    root = tmp_path / "nii"
    root.mkdir()
    img = nib.Nifti1Image(np.zeros((8, 8, 8), dtype=np.float32), np.eye(4))
    nib.save(img, str(root / "loose.nii.gz"))
    result = group_dicom_dir(root)
    assert result.rejected is True
    assert result.ingest_path == "demo"


def test_clinical_from_dir_distinguished_from_demo():
    clinical = {
        "ingest_path": "clinical",
        "ingest_source": "dicom_dir",
        "model_name": "dicom_dir_ingest",
        "filename": "study:1.2.3",
    }
    demo = {"ingest_path": "demo", "filename": "slice.jpg", "model_name": "custom_cnn"}
    assert resolve_ingest_path(clinical) == "clinical"
    assert resolve_ingest_path(demo) == "demo"
    assert classify_upload("scan.jpg", "image/jpeg") == "demo"


def test_classify_series_contrast_before_description():
    from src.ingest.dicom_dir import InstanceMeta

    inst = InstanceMeta(
        path="x",
        study_uid="s",
        series_uid="r",
        sop_uid="p",
        instance_number=1,
        modality="MR",
        image_type=["ORIGINAL", "PRIMARY"],
        series_description="T2 PROP",
        contrast_agent="GADOLINIUM",
        slice_thickness=1.0,
        pixel_spacing=[1.0, 1.0],
        orientation=[1, 0, 0, 0, 1, 0],
        position=[0, 0, 1],
        inversion_time=None,
        echo_time=12.0,
        b_value=None,
        rows=8,
        cols=8,
    )
    seq, _conf = classify_series([inst])
    assert seq == "T1C"


def test_drop_dir_batch_scan(tmp_path, monkeypatch):
    root, study, _t1, _flair = _multi_series_dir(tmp_path)
    drop = tmp_path / "drop"
    drop.mkdir()
    # move study under drop as a child folder
    dest = drop / "caseA"
    root.rename(dest)
    monkeypatch.setenv("DICOM_DROP_DIR", str(drop))
    assert study_drop_roots(drop) == [dest]
    results = scan_drop_dir()
    assert len(results) == 1
    assert results[0].ok
    assert results[0].study_uid == study
    assert results[0].ingest_path == "clinical"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.api.main import app

    with TestClient(app) as c:
        yield c


def test_from_dicom_dir_api_persists_audit_join(client, tmp_path):
    root, study, t1, flair = _multi_series_dir(tmp_path)
    r = client.post("/studies/from-dicom-dir", json={"path": str(root)}, headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["study_uid"] == study
    assert body["ingest_path"] == "clinical"
    assert body["audit_id"]
    assert len(body["audit_id"]) == 16
    assert body["series_manifest"][flair]["used_by_engines"] == ["wmh_3d"]
    assert body["series_manifest"][t1]["used_by_engines"] == ["research.triage"]


def test_from_dicom_dir_rejects_non_mr(client, tmp_path):
    study = generate_uid()
    series = generate_uid()
    root = tmp_path / "ct"
    root.mkdir()
    for i in range(1, 4):
        _write_dcm(root / f"{i}.dcm", study=study, series=series, instance=i, modality="CT")
    r = client.post("/studies/from-dicom-dir", json={"path": str(root)}, headers=HEADERS)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "NOT_MR"
    assert detail["ingest_path"] == "demo"


def test_jpg_predict_remains_demo(client, tmp_path):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.fromarray(np.zeros((80, 80), dtype=np.uint8)).convert("RGB").save(buf, format="JPEG")
    r = client.post(
        "/predict",
        files={"file": ("slice.jpg", buf.getvalue(), "image/jpeg")},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["ingest_path"] == "demo"


def test_demo_jpg_export_still_403(client):
    from src.api.attestation import attestation_text_for

    run = {
        "audit_id": "abcd1234efgh5678",
        "model_name": "unet_3d_wmh",
        "model_version": "v1",
        "confidence": 0.4,
        "wmh": {"volume_cc": 2.0},
        "ingest_path": "demo",
        "filename": "slice.jpg",
    }
    draft = client.post(
        "/report/draft",
        json={"case_id": "1.2.3.jpg.demo", "template_id": "brain_mri_wmh_svd", "model_run": run},
        headers=HEADERS,
    )
    assert draft.status_code == 200
    assert draft.json()["ingest_path"] == "demo"
    rid = draft.json()["report_id"]
    at = client.post(
        f"/report/{rid}/attest",
        json={"attested_by": "Dr. Test", "attestation_text": attestation_text_for(draft.json()["model_run_id"])},
        headers=HEADERS,
    )
    assert at.status_code == 200
    signed = client.post(
        f"/report/{rid}/sign",
        json={"signer_name": "Dr. Test", "signer_role": "neuroradiologist", "acknowledged_disclaimer": True},
        headers=HEADERS,
    )
    assert signed.status_code == 403
    pdf = client.get(f"/report/{rid}/pdf", headers=HEADERS)
    assert pdf.status_code == 403
