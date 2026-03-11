"""Lightweight JSONL audit logging for the demo app.

This is NOT a full HIPAA/FDA-compliant solution, but shows how an
audit trail could be wired into inference / LLM / export events.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.app.utils import project_root


def _audit_log_path() -> Path:
    root = project_root()
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "audit.log.jsonl"


def log_event(event_type: str, data: Dict[str, Any]) -> None:
    """Append a single JSON event to the audit log."""
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        **data,
    }
    path = _audit_log_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")

