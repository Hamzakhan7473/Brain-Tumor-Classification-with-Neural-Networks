"""Group a filesystem DICOM drop into one study. No PACS, no C-STORE."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingest.path import CLINICAL, DEMO

_MR = frozenset({"MR", "MRI"})
_DICOM_SUFFIXES = {".dcm", ".dicom", ".ima"}
_RASTER_SUFFIXES = {".jpg", ".jpeg", ".png"}
_MIN_VOLUME_SLICES = 3


@dataclass
class InstanceMeta:
    path: str
    study_uid: str
    series_uid: str
    sop_uid: str
    instance_number: int | None
    modality: str
    image_type: list[str]
    series_description: str
    contrast_agent: str
    slice_thickness: float | None
    pixel_spacing: list[float]
    orientation: list[float]
    position: list[float]
    inversion_time: float | None
    echo_time: float | None
    b_value: float | None
    rows: int | None
    cols: int | None


@dataclass
class SeriesInfo:
    series_id: str
    instances: list[InstanceMeta]
    likely_seq: str
    confidence: float
    used_by_engines: list[str] = field(default_factory=list)

    @property
    def n_instances(self) -> int:
        return len(self.instances)


@dataclass
class StudyIngestResult:
    ok: bool
    rejected: bool
    reason: str | None
    study_uid: str | None
    ingest_path: str
    series_manifest: dict[str, dict[str, Any]]
    engines: dict[str, str | None]
    n_instances: int
    errors: list[str] = field(default_factory=list)
    series: list[SeriesInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rejected": self.rejected,
            "reason": self.reason,
            "study_uid": self.study_uid,
            "ingest_path": self.ingest_path,
            "series_manifest": self.series_manifest,
            "engines": self.engines,
            "n_instances": self.n_instances,
            "errors": list(self.errors),
        }


def _is_dicom_name(path: Path) -> bool:
    low = path.name.lower()
    if low.startswith("."):
        return False
    suf = path.suffix.lower()
    if suf in _DICOM_SUFFIXES:
        return True
    if suf in _RASTER_SUFFIXES or low.endswith(".nii") or low.endswith(".nii.gz"):
        return False
    return suf == "" or path.suffix == ""


def iter_candidate_files(root: Path) -> list[Path]:
    root = Path(root)
    out: list[Path] = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and _is_dicom_name(p):
            out.append(p)
    return out


def dir_has_loose_demo_files(root: Path) -> bool:
    root = Path(root)
    if not root.is_dir():
        return False
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        low = p.name.lower()
        if any(low.endswith(s) for s in _RASTER_SUFFIXES):
            return True
        if low.endswith(".nii") or low.endswith(".nii.gz"):
            return True
    return False


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes)):
            raw = list(raw)[0]
        return float(raw)
    except (TypeError, ValueError, IndexError):
        return None


def _as_float_list(raw: Any, n: int) -> list[float]:
    if raw is None:
        return []
    try:
        vals = [float(x) for x in list(raw)]
    except (TypeError, ValueError):
        return []
    return vals[:n]


def _image_type(ds: Any) -> list[str]:
    raw = getattr(ds, "ImageType", None)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.upper()]
    try:
        return [str(x).upper() for x in list(raw)]
    except TypeError:
        return [str(raw).upper()]


def read_instance_meta(path: Path) -> InstanceMeta | None:
    try:
        import pydicom
        from pydicom.errors import InvalidDicomError
    except ImportError:
        return None
    try:
        ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=False)
    except (InvalidDicomError, Exception):
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
        except Exception:
            return None
    study = str(getattr(ds, "StudyInstanceUID", "") or "").strip()
    series = str(getattr(ds, "SeriesInstanceUID", "") or "").strip()
    if not study or not series:
        return None
    inst_raw = getattr(ds, "InstanceNumber", None)
    try:
        inst_n = int(inst_raw) if inst_raw not in (None, "") else None
    except (TypeError, ValueError):
        inst_n = None
    b_val = _as_float(getattr(ds, "DiffusionBValue", None))
    if b_val is None:
        b_val = _as_float(ds.get((0x0018, 0x9087), None))
    return InstanceMeta(
        path=str(path),
        study_uid=study,
        series_uid=series,
        sop_uid=str(getattr(ds, "SOPInstanceUID", "") or ""),
        instance_number=inst_n,
        modality=str(getattr(ds, "Modality", "") or "").upper().strip(),
        image_type=_image_type(ds),
        series_description=str(getattr(ds, "SeriesDescription", "") or ""),
        contrast_agent=str(getattr(ds, "ContrastBolusAgent", "") or "").strip(),
        slice_thickness=_as_float(getattr(ds, "SliceThickness", None)),
        pixel_spacing=_as_float_list(getattr(ds, "PixelSpacing", None), 2),
        orientation=_as_float_list(getattr(ds, "ImageOrientationPatient", None), 6),
        position=_as_float_list(getattr(ds, "ImagePositionPatient", None), 3),
        inversion_time=_as_float(getattr(ds, "InversionTime", None)),
        echo_time=_as_float(getattr(ds, "EchoTime", None)),
        b_value=b_val,
        rows=int(ds.Rows) if getattr(ds, "Rows", None) is not None else None,
        cols=int(ds.Columns) if getattr(ds, "Columns", None) is not None else None,
    )


def _sort_instances(items: list[InstanceMeta]) -> list[InstanceMeta]:
    def key(i: InstanceMeta) -> tuple:
        z = i.position[2] if len(i.position) >= 3 else 0.0
        n = i.instance_number if i.instance_number is not None else 10**9
        return (n, z, i.sop_uid, i.path)

    return sorted(items, key=key)


def classify_series(instances: list[InstanceMeta]) -> tuple[str, float]:
    """Modality → ImageType → contrast → spacing/orientation → description hint only."""
    if not instances:
        return "UNKNOWN", 0.0
    n = len(instances)
    rep = instances[n // 2]
    it = [str(x).upper() for x in rep.image_type]
    if any("LOCALIZER" in x or "SCOUT" in x for x in it):
        return "LOCALIZER", 0.92
    if any("DIFFUSION" in x or x == "DIFF" for x in it) or rep.b_value is not None:
        return "DWI", 0.86

    seq = "UNKNOWN"
    conf = 0.25
    if any("FLAIR" in x for x in it):
        seq, conf = "FLAIR", 0.78
    elif any("T1" in x for x in it):
        seq, conf = "T1", 0.72
    elif any("T2" in x for x in it):
        seq, conf = "T2", 0.72

    if seq == "UNKNOWN" and rep.inversion_time is not None and rep.inversion_time >= 1500:
        seq, conf = "FLAIR", 0.70
    elif seq == "UNKNOWN" and rep.echo_time is not None:
        if rep.echo_time >= 80:
            seq, conf = "T2", 0.55
        elif rep.echo_time <= 20:
            seq, conf = "T1", 0.50

    if rep.contrast_agent and seq in {"T1", "UNKNOWN"}:
        seq = "T1C"
        conf = max(conf, 0.60)

    thick = rep.slice_thickness or 0.0
    if n < _MIN_VOLUME_SLICES and thick > 5.0 and seq != "LOCALIZER":
        conf = min(conf, 0.40)

    desc = (rep.series_description or "").upper()
    hint = None
    if "FLAIR" in desc:
        hint = "FLAIR"
    elif "DWI" in desc or "DIFF" in desc:
        hint = "DWI"
    elif "T1" in desc:
        hint = "T1"
    elif "T2" in desc:
        hint = "T2"
    if hint:
        if seq == "UNKNOWN":
            seq, conf = hint, 0.34
        elif hint == seq or (hint == "T1" and seq == "T1C"):
            conf = min(0.95, conf + 0.08)
    return seq, round(float(conf), 3)


def can_assemble_volume(instances: list[InstanceMeta]) -> bool:
    if len(instances) < _MIN_VOLUME_SLICES:
        return False
    rows = {i.rows for i in instances if i.rows}
    cols = {i.cols for i in instances if i.cols}
    if len(rows) > 1 or len(cols) > 1:
        return False
    orients = [tuple(round(x, 4) for x in i.orientation) for i in instances if len(i.orientation) == 6]
    if orients and len(set(orients)) > 1:
        return False
    return True


def assign_engines(series: list[SeriesInfo]) -> dict[str, str | None]:
    engines: dict[str, str | None] = {"research.triage": None, "wmh_3d": None}
    flair = [
        s
        for s in series
        if s.likely_seq == "FLAIR" and can_assemble_volume(s.instances)
    ]
    flair.sort(key=lambda s: (-s.confidence, -s.n_instances))
    if flair:
        flair[0].used_by_engines.append("wmh_3d")
        engines["wmh_3d"] = flair[0].series_id

    t1 = [s for s in series if s.likely_seq in {"T1", "T1C"} and s.likely_seq != "LOCALIZER"]
    t1.sort(key=lambda s: (-s.confidence, -s.n_instances))
    pick = t1[0] if t1 else None
    if pick is None:
        others = [s for s in series if s.likely_seq not in {"LOCALIZER", "DWI"}]
        others.sort(key=lambda s: (-s.n_instances, -s.confidence))
        pick = others[0] if others else None
    if pick is not None:
        pick.used_by_engines.append("research.triage")
        engines["research.triage"] = pick.series_id
    return engines


def _reject(reason: str, errors: list[str], n: int = 0) -> StudyIngestResult:
    return StudyIngestResult(
        ok=False,
        rejected=True,
        reason=reason,
        study_uid=None,
        ingest_path=DEMO,
        series_manifest={},
        engines={"research.triage": None, "wmh_3d": None},
        n_instances=n,
        errors=errors,
    )


def group_dicom_dir(root: str | Path) -> StudyIngestResult:
    """StudyInstanceUID → SeriesInstanceUID → InstanceNumber. One study only."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return _reject("NOT_A_DIRECTORY", [f"Not a directory: {root}"])

    files = iter_candidate_files(root)
    metas: list[InstanceMeta] = []
    unreadable = 0
    for p in files:
        meta = read_instance_meta(p)
        if meta is None:
            unreadable += 1
            continue
        metas.append(meta)

    if not metas:
        extra = " (directory has raster/NIfTI only)" if dir_has_loose_demo_files(root) else ""
        return _reject("NO_DICOM", [f"No groupable DICOM instances under {root}{extra}"], n=0)

    studies = {m.study_uid for m in metas}
    if len(studies) != 1:
        return _reject(
            "UNGROUPABLE",
            [f"Expected one StudyInstanceUID, found {len(studies)}"],
            n=len(metas),
        )

    mods = {m.modality for m in metas}
    non_mr = sorted(m for m in mods if m and m not in _MR)
    missing_mod = any(not m.modality for m in metas)
    if non_mr or missing_mod:
        shown = ", ".join(non_mr) if non_mr else "missing"
        return _reject("NOT_MR", [f"Modality must be MR; got {shown}"], n=len(metas))

    by_series: dict[str, list[InstanceMeta]] = {}
    for m in metas:
        by_series.setdefault(m.series_uid, []).append(m)

    series_list: list[SeriesInfo] = []
    for sid, insts in sorted(by_series.items()):
        ordered = _sort_instances(insts)
        if not any(i.instance_number is not None for i in ordered) and not any(i.position for i in ordered):
            return _reject(
                "UNGROUPABLE",
                [f"Series {sid} has no InstanceNumber or ImagePositionPatient"],
                n=len(metas),
            )
        seq, conf = classify_series(ordered)
        series_list.append(SeriesInfo(series_id=sid, instances=ordered, likely_seq=seq, confidence=conf))

    engines = assign_engines(series_list)
    manifest = {
        s.series_id: {
            "likely_seq": s.likely_seq,
            "confidence": s.confidence,
            "used_by_engines": list(s.used_by_engines),
            "n_instances": s.n_instances,
            "can_assemble_volume": can_assemble_volume(s.instances),
        }
        for s in series_list
    }
    max_n = max((s.n_instances for s in series_list), default=0)
    path = CLINICAL if max_n >= 2 else DEMO
    reason = None if path == CLINICAL else "SINGLE_SLICE"
    return StudyIngestResult(
        ok=True,
        rejected=False,
        reason=reason,
        study_uid=next(iter(studies)),
        ingest_path=path,
        series_manifest=manifest,
        engines=engines,
        n_instances=len(metas),
        series=series_list,
    )


def assemble_series_volume(instances: list[InstanceMeta]) -> tuple[Any, list[float]] | None:
    """Stack a series by InstanceNumber. WMH may use this only for a FLAIR series."""
    if not can_assemble_volume(instances):
        return None
    try:
        import numpy as np
        import pydicom
    except ImportError:
        return None
    ordered = _sort_instances(instances)
    slices = []
    for inst in ordered:
        try:
            ds = pydicom.dcmread(inst.path)
            pix = ds.pixel_array
        except Exception:
            return None
        arr = np.asarray(pix)
        if arr.ndim != 2:
            arr = arr.squeeze()
            if arr.ndim != 2:
                return None
        slices.append(arr.astype("float32"))
    try:
        vol = np.stack(slices, axis=0)
    except ValueError:
        return None
    rep = ordered[0]
    dx, dy = (rep.pixel_spacing + [1.0, 1.0])[:2]
    if len(ordered) >= 2 and len(ordered[0].position) == 3 and len(ordered[1].position) == 3:
        dz = abs(ordered[1].position[2] - ordered[0].position[2]) or (rep.slice_thickness or 1.0)
    else:
        dz = rep.slice_thickness or 1.0
    return vol, [float(dz), float(dx), float(dy)]


def flair_volume_nifti_bytes(result: StudyIngestResult) -> bytes | None:
    """WMH input: assembled FLAIR series volume only — never a random slice."""
    sid = result.engines.get("wmh_3d")
    if not sid:
        return None
    series = next((s for s in result.series if s.series_id == sid), None)
    if series is None or series.likely_seq != "FLAIR":
        return None
    assembled = assemble_series_volume(series.instances)
    if assembled is None:
        return None
    vol, spacing = assembled
    import os
    import tempfile

    import nibabel as nib
    import numpy as np

    affine = np.diag([spacing[2], spacing[1], spacing[0], 1.0])
    img = nib.Nifti1Image(np.asarray(vol, dtype=np.float32), affine)
    fd, tmp = tempfile.mkstemp(suffix=".nii.gz")
    os.close(fd)
    try:
        nib.save(img, tmp)
        return Path(tmp).read_bytes()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def canonical_study_bytes(result: StudyIngestResult) -> bytes:
    payload = {
        "study_uid": result.study_uid,
        "series": sorted(result.series_manifest.keys()),
        "n_instances": result.n_instances,
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")
