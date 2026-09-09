"""Rigid (+ optional affine) FLAIR-to-FLAIR registration.

This job is the only writer of ``registration.status=passed``.
Caller-supplied status and nibabel affine alignment are never treated as pass.
"""

from __future__ import annotations

from typing import Any

import numpy as np

JOB_SOURCE = "neurosight.registration.v1"
MASK_OVERLAP_MIN = 0.85
NCC_MIN = 0.50
COM_SHIFT_MM_MAX = 15.0
_FLAIR = frozenset({"FLAIR", "T2-FLAIR", "T2_FLAIR"})


def _sequence_family(raw: Any) -> str:
    s = str(raw or "FLAIR").strip().upper().replace(" ", "_")
    if s in _FLAIR or s == "FLAIR":
        return "FLAIR"
    return s


def same_sequence_family(a: Any, b: Any) -> bool:
    return _sequence_family(a) == "FLAIR" and _sequence_family(b) == "FLAIR"


def _as_volume(raw: Any) -> np.ndarray | None:
    if raw is None:
        return None
    if hasattr(raw, "get_fdata"):
        arr = np.asarray(raw.get_fdata(), dtype=np.float32)
    elif isinstance(raw, str):
        try:
            import nibabel as nib

            arr = np.asarray(nib.load(raw).get_fdata(), dtype=np.float32)
        except Exception:
            return None
    else:
        try:
            arr = np.asarray(raw, dtype=np.float32)
        except (TypeError, ValueError):
            return None
    if arr.ndim > 3:
        arr = arr[..., 0]
    if arr.ndim != 3 or arr.size == 0:
        return None
    return arr


def _spacing_zyx(raw: Any, vol: np.ndarray) -> tuple[float, float, float]:
    if raw is None:
        return (1.0, 1.0, 1.0)
    try:
        vals = [float(x) for x in list(raw)]
    except (TypeError, ValueError):
        return (1.0, 1.0, 1.0)
    if len(vals) >= 3:
        return (abs(vals[0]) or 1.0, abs(vals[1]) or 1.0, abs(vals[2]) or 1.0)
    return (1.0, 1.0, 1.0)


def _brain_mask(vol: np.ndarray) -> np.ndarray:
    mx = float(np.percentile(vol, 99)) if vol.size else 0.0
    if mx <= 1e-6:
        return vol > 0
    return vol >= (0.25 * mx)


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    a_b = a.astype(bool)
    b_b = b.astype(bool)
    inter = float(np.logical_and(a_b, b_b).sum())
    den = float(a_b.sum() + b_b.sum())
    if den <= 0:
        return 0.0
    return 2.0 * inter / den


def _ncc(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    if mask is not None:
        m = mask.astype(bool)
        if int(m.sum()) < 8:
            m = np.ones(a.shape, dtype=bool)
        aa = a[m].astype(np.float64)
        bb = b[m].astype(np.float64)
    else:
        aa = a.ravel().astype(np.float64)
        bb = b.ravel().astype(np.float64)
    aa = aa - aa.mean()
    bb = bb - bb.mean()
    da = float(aa.std())
    db = float(bb.std())
    if da < 1e-8 and db < 1e-8:
        return 1.0
    if da < 1e-8 or db < 1e-8:
        return 0.0
    return float(np.mean(aa * bb) / (da * db))


def _com_mm(mask: np.ndarray, spacing_zyx: tuple[float, float, float]) -> np.ndarray:
    coords = np.argwhere(mask)
    if coords.size == 0:
        return np.zeros(3, dtype=np.float64)
    com_vox = coords.mean(axis=0)
    return com_vox * np.array(spacing_zyx, dtype=np.float64)


def _to_sitk(vol: np.ndarray, spacing_zyx: tuple[float, float, float]):
    import SimpleITK as sitk

    img = sitk.GetImageFromArray(np.ascontiguousarray(vol, dtype=np.float32))
    # numpy (z,y,x) → SimpleITK spacing (x,y,z)
    img.SetSpacing((float(spacing_zyx[2]), float(spacing_zyx[1]), float(spacing_zyx[0])))
    return img


def _run_metric(fixed, moving, initial, *, learning_rate: float, iters: int):
    import SimpleITK as sitk

    R = sitk.ImageRegistrationMethod()
    R.SetMetricAsCorrelation()
    R.SetOptimizerAsRegularStepGradientDescent(
        learningRate=learning_rate,
        minStep=1e-4,
        numberOfIterations=iters,
        relaxationFactor=0.5,
    )
    R.SetInterpolator(sitk.sitkLinear)
    R.SetInitialTransform(initial, inPlace=False)
    try:
        R.SetOptimizerScalesFromPhysicalShift()
    except Exception:
        pass
    return R.Execute(fixed, moving)


def _com_translation(fixed, moving):
    import SimpleITK as sitk

    f = np.asarray(sitk.GetArrayFromImage(fixed), dtype=np.float32)
    m = np.asarray(sitk.GetArrayFromImage(moving), dtype=np.float32)
    sp = fixed.GetSpacing()
    spacing_zyx = (float(sp[2]), float(sp[1]), float(sp[0]))
    com_f = _com_mm(_brain_mask(f), spacing_zyx)
    com_m = _com_mm(_brain_mask(m), spacing_zyx)
    tx = sitk.TranslationTransform(3)
    # numpy (z,y,x) mm → SimpleITK (x,y,z)
    tx.SetOffset([float(com_f[2] - com_m[2]), float(com_f[1] - com_m[1]), float(com_f[0] - com_m[0])])
    return tx


def _resample(moving, fixed, tx):
    import SimpleITK as sitk

    return sitk.Resample(moving, fixed, tx, sitk.sitkLinear, 0.0, moving.GetPixelID())


def _register(fixed, moving, *, use_affine: bool):
    import SimpleITK as sitk

    fixed = sitk.Cast(fixed, sitk.sitkFloat32)
    moving = sitk.Cast(moving, sitk.sitkFloat32)
    trans = _run_metric(fixed, moving, _com_translation(fixed, moving), learning_rate=2.0, iters=40)
    aligned = _resample(moving, fixed, trans)
    size = fixed.GetSize()
    center_idx = [0.5 * (size[i] - 1) for i in range(3)]
    center = fixed.TransformContinuousIndexToPhysicalPoint(center_idx)
    euler = sitk.Euler3DTransform()
    euler.SetCenter(center)
    rigid = _run_metric(fixed, aligned, euler, learning_rate=0.4, iters=28)
    aligned = _resample(aligned, fixed, rigid)
    final: Any = sitk.CompositeTransform(3)
    final.AddTransform(trans)
    final.AddTransform(rigid)
    if use_affine:
        affine = sitk.AffineTransform(3)
        affine.SetCenter(center)
        affine = _run_metric(fixed, aligned, affine, learning_rate=0.3, iters=24)
        aligned = _resample(aligned, fixed, affine)
        final.AddTransform(affine)
    return final, aligned


def _transform_record(tx: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"type": type(tx).__name__, "source": JOB_SOURCE}
    try:
        rec["parameters"] = [float(x) for x in tx.GetParameters()]
    except Exception:
        rec["parameters"] = []
    return rec


def run_registration_job(
    *,
    current_volume: Any,
    prior_volume: Any,
    current_audit_id: str | None = None,
    prior_audit_id: str | None = None,
    current_study_uid: str | None = None,
    prior_study_uid: str | None = None,
    patient_key: str | None = None,
    prior_patient_key: str | None = None,
    current_sequence: Any = "FLAIR",
    prior_sequence: Any = "FLAIR",
    current_spacing_mm: Any = None,
    prior_spacing_mm: Any = None,
    use_affine: bool = False,
) -> dict[str, Any]:
    """Register current FLAIR onto prior FLAIR. Only this function may set status=passed."""
    base = {
        "source": JOB_SOURCE,
        "current_audit_id": current_audit_id,
        "prior_audit_id": prior_audit_id,
        "current_study_uid": current_study_uid,
        "prior_study_uid": prior_study_uid,
        "patient_key": patient_key,
    }
    if patient_key and prior_patient_key and str(patient_key) != str(prior_patient_key):
        return {**base, "status": "skipped", "reason_code": "INCOMPATIBLE_PATIENT"}
    if not same_sequence_family(current_sequence, prior_sequence):
        return {**base, "status": "skipped", "reason_code": "INCOMPATIBLE_SEQUENCE"}

    cur = _as_volume(current_volume)
    pri = _as_volume(prior_volume)
    if cur is None or pri is None:
        return {**base, "status": "not_run", "reason_code": "QC_NO_REGISTRATION"}

    try:
        import SimpleITK as sitk
    except ImportError:
        return {**base, "status": "not_run", "reason_code": "QC_NO_REGISTRATION"}

    spacing = _spacing_zyx(current_spacing_mm or prior_spacing_mm, cur)
    try:
        fixed = _to_sitk(pri, _spacing_zyx(prior_spacing_mm, pri) if prior_spacing_mm is not None else spacing)
        moving = _to_sitk(cur, spacing)
        tx, resampled = _register(fixed, moving, use_affine=use_affine)
        aligned = np.asarray(sitk.GetArrayFromImage(resampled), dtype=np.float32)
        prior_arr = np.asarray(sitk.GetArrayFromImage(fixed), dtype=np.float32)
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "reason_code": "QC_REGISTRATION",
            "mask_overlap": 0.0,
            "ncc": 0.0,
            "com_shift_mm": None,
            "error": str(exc),
        }

    m_pri = _brain_mask(prior_arr)
    m_cur = _brain_mask(aligned)
    overlap = _dice(m_pri, m_cur)
    ncc = _ncc(prior_arr, aligned, None)
    if ncc < NCC_MIN:
        ncc = max(ncc, _ncc(prior_arr, aligned, np.logical_or(m_pri, m_cur)))
    shift = float(np.linalg.norm(_com_mm(m_cur, spacing) - _com_mm(m_pri, spacing)))
    qc_pass = overlap >= MASK_OVERLAP_MIN and ncc >= NCC_MIN and shift < COM_SHIFT_MM_MAX
    return {
        **base,
        "status": "passed" if qc_pass else "failed",
        "reason_code": None if qc_pass else "QC_REGISTRATION",
        "mask_overlap": round(overlap, 4),
        "ncc": round(ncc, 4),
        "com_shift_mm": round(shift, 3),
        "transform": _transform_record(tx),
        "thresholds": {
            "mask_overlap_min": MASK_OVERLAP_MIN,
            "ncc_min": NCC_MIN,
            "com_shift_mm_max": COM_SHIFT_MM_MAX,
        },
    }


def job_wrote_passed(job: Any) -> bool:
    return (
        isinstance(job, dict)
        and job.get("status") == "passed"
        and job.get("source") == JOB_SOURCE
        and job.get("reason_code") in (None, "")
    )
