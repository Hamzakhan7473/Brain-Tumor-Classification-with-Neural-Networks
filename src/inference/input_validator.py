"""
Validate uploads against requested model assumptions (research guardrail).
Uses filename heuristics + signal statistics; rejects obvious mismatches.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class ValidationResult:
    accepted: bool
    sequence: str
    confidence: float
    warnings: list[str]
    errors: list[str]
    metadata: dict
    trusted: bool = False


def _skew_sample(arr: np.ndarray) -> float:
    flat = np.asarray(arr, dtype=np.float64).ravel()
    if flat.size < 32:
        return 0.0
    flat = flat[flat > np.percentile(flat, 1)]
    if flat.size < 32:
        return 0.0
    m = float(flat.mean())
    v = flat - m
    s2 = float(np.mean(v**2))
    if s2 < 1e-12:
        return 0.0
    s3 = float(np.mean(v**3))
    return s3 / (s2**1.5 + 1e-12)


def _detect_3d_sequence(file_bytes: bytes, filename: str) -> tuple[str, float, dict]:
    import os
    import tempfile

    import nibabel as nib

    fname = filename or "volume.nii.gz"
    suffix = ".nii.gz" if fname.lower().endswith(".gz") else ".nii"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(file_bytes)
        tmp = fh.name

    try:
        img = nib.load(tmp)
        vol = np.asarray(img.get_fdata(dtype=np.float32))
        affine = img.affine
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    if vol.ndim > 3:
        vol = vol[..., 0]
    if vol.ndim != 3:
        raise ValueError(f"NIfTI is not a 3D volume: shape {vol.shape}")

    voxel_dims = np.abs(np.asarray(np.diag(affine)[:3], dtype=np.float64))
    voxel_vol = float(np.prod(voxel_dims))

    metadata: dict[str, Any] = {
        "shape": list(vol.shape),
        "voxel_dims_mm": [float(v) for v in voxel_dims],
        "voxel_volume_mm3": voxel_vol,
        "affine": affine.tolist(),
        "intensity_range": [float(vol.min()), float(vol.max())],
    }

    name = filename.lower()
    name_signal = "unknown"
    if any(t in name for t in ("flair", "_fl_", "fluid")):
        name_signal = "FLAIR"
    elif any(t in name for t in ("_t1w", "_t1.", "_t1_", "mprage", "spgr", "t1w")):
        name_signal = "T1"
    elif any(t in name for t in ("_t2w", "_t2.", "_t2_")) and "flair" not in name:
        name_signal = "T2"
    elif any(t in name for t in ("dwi", "diffusion", "_dti_")):
        name_signal = "DWI"

    nz = vol[vol > np.mean(vol) * 0.1]
    if nz.size < 1000:
        return name_signal, 0.37 if name_signal != "unknown" else 0.0, metadata

    intensity_skew = _skew_sample(nz)
    intensity_p99 = float(np.percentile(nz, 99))
    intensity_p50 = float(np.percentile(nz, 50))
    bright_ratio = intensity_p99 / max(intensity_p50, 1e-3)

    metadata["intensity_skew"] = round(intensity_skew, 5)
    metadata["bright_ratio"] = round(bright_ratio, 5)

    intensity_signal = "unknown"
    if intensity_skew > 0.78 and bright_ratio > 2.0:
        intensity_signal = "FLAIR"
    elif -0.3 < intensity_skew < 0.52 and bright_ratio < 1.78:
        intensity_signal = "T1"
    elif intensity_skew > 0.4 and bright_ratio > 1.78:
        intensity_signal = "T2"

    if name_signal == intensity_signal and name_signal != "unknown":
        return name_signal, 0.93, metadata
    if name_signal != "unknown" and intensity_signal == "unknown":
        return name_signal, 0.68, metadata
    if intensity_signal != "unknown" and name_signal == "unknown":
        return intensity_signal, 0.58, metadata
    if name_signal != intensity_signal and name_signal != "unknown":
        # Conflict — defer to filename heuristic with lower certainty
        return name_signal, 0.41, metadata
    return "unknown", 0.0, metadata


def _validate_image_2d(file_bytes: bytes) -> tuple[bool, list[str]]:
    from PIL import Image, UnidentifiedImageError

    warnings: list[str] = []
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        img = Image.open(io.BytesIO(file_bytes)).convert("L")
    except (UnidentifiedImageError, OSError, ValueError):
        return False, ["Could not decode image file"]

    w, h = img.size
    if min(w, h) < 64:
        return False, ["Image too small (< 64px). Not a valid scan."]
    if max(w, h) > 4096:
        warnings.append("Unusually large image — will be downsized for inference")

    aspect = max(w, h) / min(w, h)
    if aspect > 1.85:
        warnings.append(
            f"Aspect ratio {aspect:.1f} unusual for brain slice — verify axial orientation.",
        )

    return True, warnings


def _validate_dicom_2d(file_bytes: bytes) -> tuple[str, float, dict]:
    import pydicom

    ds = pydicom.dcmread(io.BytesIO(file_bytes))

    desc = (getattr(ds, "SeriesDescription", "") or "").upper()
    raw_it = getattr(ds, "ImageType", None)
    if raw_it is None:
        image_type: list[str] = []
    elif isinstance(raw_it, str):
        image_type = [raw_it.upper()]
    else:
        try:
            image_type = [str(x).upper() for x in list(raw_it)]
        except TypeError:
            image_type = [str(raw_it).upper()]
    slice_th = None
    try:
        raw_th = getattr(ds, "SliceThickness", None)
        if raw_th is not None and str(raw_th).strip():
            slice_th = float(raw_th)
    except (TypeError, ValueError):
        slice_th = None
    metadata = {
        "modality": str(getattr(ds, "Modality", "") or ""),
        "manufacturer": str(getattr(ds, "Manufacturer", "")),
        "series_desc": desc,
        "image_type": image_type,
        "slice_thickness_mm": slice_th,
        "patient_age": str(getattr(ds, "PatientAge", "")),
        "patient_sex": str(getattr(ds, "PatientSex", "")),
    }

    seq = "unknown"
    conf = 0.32
    if "FLAIR" in desc:
        seq, conf = "FLAIR", 0.92
    elif "T1" in desc:
        seq, conf = "T1", 0.89
    elif "T2" in desc:
        seq, conf = "T2", 0.88
    elif "DIFF" in desc or "DWI" in desc:
        seq, conf = "DWI", 0.85
    return seq, float(conf), metadata


def validate_for_model(
    file_bytes: bytes,
    filename: str,
    expected_model: str,
) -> ValidationResult:
    warnings: list[str] = []
    errors: list[str] = []
    metadata: dict = {}

    fname = filename or "unknown"
    low = fname.lower()

    is_3d = expected_model == "unet_3d_wmh"

    if is_3d:
        if not (low.endswith(".nii") or low.endswith(".nii.gz")):
            errors.append(
                "3D WMH model requires NIfTI (.nii or .nii.gz). T1/T2 single raster slices not accepted.",
            )
            return ValidationResult(False, "unknown", 0.0, [], errors, {})

        try:
            seq, conf, vol_meta = _detect_3d_sequence(file_bytes, fname)
        except ValueError as exc:
            errors.append(str(exc))
            return ValidationResult(False, "unknown", 0.0, warnings, errors, {})
        metadata.update(vol_meta)

        if seq != "FLAIR":
            errors.append(
                f"WMH model expects FLAIR-weighted MRI. Detected: {seq} (confidence "
                f"{conf:.0%}). Refusing inference to avoid unreliable segmentation.",
            )
            return ValidationResult(False, seq, conf, warnings, errors, metadata)

        if conf < 0.65:
            warnings.append(
                f"Sequence detection modestly certain ({conf:.0%} FLAIR); verify modality before reliance.",
            )

        vv = float(vol_meta.get("voxel_volume_mm3", 1.0))
        # crude max edge length from diagonal of voxel dims
        mx = float(max(vol_meta.get("voxel_dims_mm") or [1.0]))
        if mx > 3.5 or vv > 18.0:
            warnings.append("Coarse voxel grid — volumetric summaries may underestimate fine lesion load.")

        return ValidationResult(True, seq, conf, warnings, errors, metadata, trusted=True)

    # 2D classifier path
    ext = Path(fname).suffix.lower()
    if low.endswith(".dcm") or ext in (".dcm", ".dicom"):
        seq, conf, meta = _validate_dicom_2d(file_bytes)
        metadata.update(meta)
        mod = str(metadata.get("modality") or "").upper().strip()
        if mod and mod not in {"MR", "MRI"}:
            errors.append(
                f"Series modality is {mod}, not MR. Limited exam; measurement not applied.",
            )
            return ValidationResult(False, seq, conf, warnings, errors, metadata, trusted=False)
        image_type = [str(x).upper() for x in (metadata.get("image_type") or [])]
        if any("LOCALIZER" in x for x in image_type):
            errors.append(
                "DICOM series check failed (ImageType LOCALIZER). "
                "Limited exam; measurement not applied.",
            )
            return ValidationResult(False, seq, conf, warnings, errors, metadata, trusted=False)
        if seq in {"T2", "DWI", "FLAIR"}:
            errors.append(
                f"2D triage classifier will not infer on {seq}. Required: structural T1-like series. "
                "Limited exam; measurement not applied.",
            )
            return ValidationResult(False, seq, conf, warnings, errors, metadata, trusted=False)
        if seq not in {"T1"}:
            warnings.append(
                f"DICOM sequence '{seq}' is not confirmed T1; 2D triage output is untrusted.",
            )
        return ValidationResult(True, seq, conf, warnings, errors, metadata, trusted=False)

    if ext in (".jpg", ".jpeg", ".png") or low.endswith((".jpg", ".jpeg", ".png")):
        ok, ims = _validate_image_2d(file_bytes)
        if not ok:
            return ValidationResult(False, "unknown", 0.0, [], ims, {}, trusted=False)
        warnings.extend(ims)
        warnings.append("MOTION_INDETERMINATE: motion cannot be assessed on a raster screenshot.")
        return ValidationResult(True, "image", 1.0, warnings, [], {"source": "raster"}, trusted=False)

    errors.append(f"Unsupported format for classifier: '{ext}'. Use JPG/PNG/DICOM.")
    return ValidationResult(False, "unknown", 0.0, [], errors, {})

