"""Append-only JSONL stores for shadow-mode AI results and clinician feedback.

Not a full EMR; complements `src/app/audit.py` with study-oriented records.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.app.utils import project_root


def _ensure_logs() -> Path:
    logs = project_root() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def append_shadow_result(payload: Dict[str, Any]) -> None:
    """Record one AI inference in shadow / research context (append-only JSONL)."""
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "kind": "shadow_inference",
        **payload,
    }
    path = _ensure_logs() / "shadow_results.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def append_clinical_feedback(payload: Dict[str, Any]) -> None:
    """Record radiologist feedback (agree / wrong class / unclear, optional correction)."""
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "kind": "clinical_feedback",
        **payload,
    }
    path = _ensure_logs() / "clinical_feedback.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
