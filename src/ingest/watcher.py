"""Batch-scan a configured DICOM drop directory. Filesystem only — not a C-STORE SCP."""

from __future__ import annotations

import os
from pathlib import Path

from src.ingest.dicom_dir import StudyIngestResult, group_dicom_dir, iter_candidate_files


def configured_drop_dir() -> Path | None:
    raw = (os.environ.get("DICOM_DROP_DIR") or os.environ.get("NEUROSIGHT_DICOM_DROP") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def study_drop_roots(root: str | Path) -> list[Path]:
    """Root is one study if DICOMs sit in it; otherwise each child dir that has DICOMs."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return []
    files = iter_candidate_files(root)
    if not files:
        return []
    if any(p.parent.resolve() == root for p in files):
        return [root]
    children = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    found = [p for p in children if iter_candidate_files(p)]
    return found or [root]


def scan_drop_dir(root: str | Path | None = None) -> list[StudyIngestResult]:
    """One-shot batch scan. Operators can poll this; no pynetdicom listener."""
    base = Path(root).expanduser().resolve() if root else configured_drop_dir()
    if base is None:
        return []
    return [group_dicom_dir(p) for p in study_drop_roots(base)]
