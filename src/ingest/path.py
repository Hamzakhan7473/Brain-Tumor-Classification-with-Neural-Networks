"""Clinical vs demo ingest path. JPG/PNG and 2D slice classifiers are never clinical."""

from __future__ import annotations

from typing import Any

DEMO = "demo"
CLINICAL = "clinical"

_RASTER_SUFFIXES = (".jpg", ".jpeg", ".png")
_TRIAGE_MODELS = frozenset({"custom_cnn", "xception", "transfer"})
_TRIAGE_CLASS_KEYS = frozenset({"glioma", "meningioma", "pituitary", "notumor"})
TRUSTED_VOLUME_IDS = frozenset(
    {
        "wmh_volume_cc",
        "wmh_volume_periventricular_cc",
        "wmh_volume_deep_subcortical_cc",
        "wmh_volume_infratentorial_cc",
    }
)
TRIAGE_BANNER = "Research / protocol-check triage — not a signed finding"


def classify_upload(filename: str | None, content_type: str | None = None) -> str:
    """Raster uploads are demo. DICOM / NIfTI are not classified as JPG-as-MRI here."""
    fn = (filename or "").lower().strip()
    ct = (content_type or "").lower().strip()
    if fn.endswith(_RASTER_SUFFIXES) or ct in {"image/jpeg", "image/jpg", "image/png"}:
        return DEMO
    return CLINICAL


def resolve_ingest_path(model_run: dict[str, Any] | None) -> str:
    """Fail closed for 2D triage / rasters. Explicit ingest_path wins when valid."""
    run = model_run if isinstance(model_run, dict) else {}
    explicit = str(run.get("ingest_path") or "").strip().lower()
    if explicit in {DEMO, CLINICAL}:
        return explicit
    inferred = classify_upload(
        str(run.get("filename") or run.get("source_filename") or ""),
        str(run.get("content_type") or ""),
    )
    if inferred == DEMO:
        return DEMO
    model = str(run.get("model_name") or run.get("model") or "").strip().lower()
    if model in _TRIAGE_MODELS:
        return DEMO
    return CLINICAL


def report_is_demo(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    path = str(report.get("ingest_path") or "").strip().lower()
    if path == DEMO:
        return True
    if path == CLINICAL:
        return False
    return resolve_ingest_path(report.get("model_run_snapshot") or report) == DEMO


def is_triage_model(name: str | None) -> bool:
    return str(name or "").strip().lower() in _TRIAGE_MODELS


def _norm_class_key(raw: Any) -> str:
    return str(raw or "").strip().lower().replace(" ", "").replace("_", "")


def is_2d_triage_run(model_run: dict[str, Any] | None) -> bool:
    """True for the 4-class slice CNN (by model name or class histogram)."""
    run = model_run if isinstance(model_run, dict) else {}
    if is_triage_model(str(run.get("model_name") or run.get("model") or "")):
        return True
    probs = run.get("probabilities") or run.get("class_probabilities") or {}
    if isinstance(probs, dict) and probs:
        keys = {_norm_class_key(k) for k in probs}
        if keys & _TRIAGE_CLASS_KEYS:
            return True
    return False


def research_triage_from_run(model_run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not is_2d_triage_run(model_run):
        return None
    run = model_run if isinstance(model_run, dict) else {}
    probs = run.get("probabilities") or run.get("class_probabilities") or {}
    label = str(run.get("label") or run.get("prediction") or "").strip()
    if isinstance(probs, dict) and probs and not label:
        label = str(max(probs, key=lambda k: float(probs[k])))
    try:
        conf = float(run.get("confidence") or run.get("model_confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf <= 0 and isinstance(probs, dict) and probs:
        try:
            conf = float(max(float(v) for v in probs.values()))
        except (TypeError, ValueError):
            conf = 0.0
    if conf > 1.0:
        conf = conf / 100.0
    if not label:
        return None
    return {"class": label, "confidence": round(conf, 6)}


def triage_suggested_line(cls: str) -> str:
    return (
        f"Slice-wise research classifier suggested class {cls}; "
        "not used for measurement or signature."
    )


def wmh_volume_is_trusted(model_run: dict[str, Any] | None, qc: dict[str, Any] | None = None) -> bool:
    """WMH cc may enter the allowlist only from a trusted 3D engine run."""
    run = model_run if isinstance(model_run, dict) else {}
    if is_2d_triage_run(run) or is_triage_model(str(run.get("model_name") or run.get("model") or "")):
        return False
    wmh = run.get("wmh")
    if not isinstance(wmh, dict):
        return False
    if str(wmh.get("status") or "").lower() in {"omitted", "unreliable"}:
        return False
    q = qc if isinstance(qc, dict) else run.get("qc")
    q = q if isinstance(q, dict) else {}
    engines = q.get("engines") if isinstance(q.get("engines"), dict) else {}
    eng = engines.get("wmh_3d") if isinstance(engines.get("wmh_3d"), dict) else {}
    if eng.get("run") is False or eng.get("trusted") is False:
        return False
    if str(q.get("overall") or "") == "fail" and not eng.get("run"):
        return False
    return wmh.get("volume_cc") is not None


def has_trusted_volume(report: dict[str, Any] | None) -> bool:
    doc = report if isinstance(report, dict) else {}
    if is_triage_model(_model_name_of(doc)):
        return False
    qc = doc.get("qc") if isinstance(doc.get("qc"), dict) else None
    snap = doc.get("model_run_snapshot") if isinstance(doc.get("model_run_snapshot"), dict) else {}
    if qc is None and isinstance(snap.get("qc"), dict):
        qc = snap["qc"]
    if isinstance(qc, dict):
        engines = qc.get("engines") if isinstance(qc.get("engines"), dict) else {}
        eng = engines.get("wmh_3d") if isinstance(engines.get("wmh_3d"), dict) else {}
        if eng.get("run") is False or eng.get("trusted") is False:
            return False
        if str(qc.get("overall") or "") == "fail" and not eng.get("run"):
            return False
    if wmh_volume_is_trusted(doc, qc) or wmh_volume_is_trusted(snap, qc):
        return True
    for m in doc.get("measurements") or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("id") or "") not in TRUSTED_VOLUME_IDS:
            continue
        if str(m.get("status") or "").lower() in {"omitted", "unreliable"}:
            continue
        return True
    return False


def _model_name_of(report: dict[str, Any]) -> str:
    name = str(report.get("model_name") or "").strip()
    if name:
        return name
    snap = report.get("model_run_snapshot")
    if isinstance(snap, dict):
        return str(snap.get("model_name") or snap.get("model") or "").strip()
    return ""


def is_triage_only(report: dict[str, Any] | None) -> bool:
    """2D 4-class engine with no trusted 3D/WMH volume — not exportable."""
    doc = report if isinstance(report, dict) else {}
    return is_triage_model(_model_name_of(doc)) and not has_trusted_volume(doc)


def export_allowed_for(report: dict[str, Any] | None) -> bool:
    doc = report if isinstance(report, dict) else {}
    if report_is_demo(doc):
        return False
    if is_triage_only(doc):
        return False
    return True
